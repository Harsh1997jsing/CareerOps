"""
Verifies app/api/main.py's global exception handlers — added by a full
code audit pass after finding that anything not already wrapped in an
HTTPException (an LLM failure, a raw DB error, ...) fell through to
Starlette's default handler, which returns plain text, not JSON, for any
unhandled exception (confirmed against the installed Starlette source).
Every response from this app must be `{"detail": "..."}` JSON, matching
CONTRACT.md, regardless of what actually failed.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.main import app
from app.core import get_db
from app.core.exceptions import LLMServiceError
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

# Starlette's ServerErrorMiddleware special-cases a bare Exception/500
# handler (see starlette/applications.py:build_middleware_stack — a
# handler registered under the literal `Exception` key is diverted there,
# not into the regular per-exception-type dispatch every other handler in
# this app uses) and, even after successfully calling that handler and
# sending its response, *always* re-raises afterward "to allow test
# clients to optionally raise the error within the test case" (its own
# comment) — that's what TestClient's default raise_server_exceptions=True
# surfaces. In real production (uvicorn) the client still gets the
# handler's response; the re-raise is server-side-only. A second client
# with that flag off is the only way to assert on the response itself.
no_raise_client = TestClient(app, raise_server_exceptions=False)


def test_llm_service_error_returns_503_json_detail():
    with patch(
        "app.api.routes.jobs.jobs_service.get_job_by_id",
        side_effect=LLMServiceError("Claude API call failed: timed out"),
    ):
        response = client.post("/jobs/1/analyze")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Claude API call failed: timed out"}


def test_unexpected_exception_returns_json_not_plain_text():
    # Before this fix, anything that wasn't already an HTTPException or a
    # registered CareerOpsError subclass fell through to Starlette's
    # default handler — plain text, not JSON — for the single most likely
    # real-world failure mode (any unexpected error deep in a service call).
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", side_effect=ValueError("unexpected")):
        response = no_raise_client.post("/jobs/1/analyze")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Internal server error"}


def test_unexpected_exception_does_not_leak_internal_details():
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", side_effect=ValueError("db password is hunter2")):
        response = no_raise_client.post("/jobs/1/analyze")

    assert "hunter2" not in response.text


def test_careerops_error_returns_detail_shape_not_the_old_error_key():
    # main.py's handlers used to return {"error": ..., "detail": ...} —
    # normalized to just {"detail": ...} to match CONTRACT.md and every
    # HTTPException-based response's shape.
    from app.core.exceptions import ConfigurationError

    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", side_effect=ConfigurationError("API key missing")):
        response = client.post("/jobs/1/analyze")

    assert response.status_code == 500
    assert response.json() == {"detail": "API key missing"}
