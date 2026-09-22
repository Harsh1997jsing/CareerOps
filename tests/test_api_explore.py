from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.main import app
from app.core import get_db
from app.sources.common import description_hash
from app.sources.mcp.capabilities import build_capability_matrix
from mcp.types import Tool
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

RESULT = {
    "source": "jobo",
    "source_job_id": "j1",
    "company": "Acme",
    "title": "Backend Engineer",
    "location": "Bangalore",
    "url": "https://example.com/apply/j1",
    "description": "Build things",
    "description_hash": "a" * 64,
    "employment_type": "Full-time",
    "posted_at": None,
    "salary_min": 1000000,
    "salary_max": 1500000,
}


def test_search_requires_authentication():
    # Audit finding F1: /explore/* required no auth at all.
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/explore/search", json={"query": "backend engineer"})
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_search_returns_normalized_results():
    with patch("app.api.routes.explore.mcp_explore.search", AsyncMock(return_value=[RESULT])) as mock_search:
        response = client.post("/explore/search", json={"query": "backend engineer", "filters": {"location": "Bangalore"}})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["source"] == "jobo"
    assert body[0]["company"] == "Acme"
    mock_search.assert_called_once_with("backend engineer", {"location": "Bangalore"})


def test_search_defaults_filters_to_empty_dict():
    with patch("app.api.routes.explore.mcp_explore.search", AsyncMock(return_value=[])) as mock_search:
        client.post("/explore/search", json={"query": "backend engineer"})

    mock_search.assert_called_once_with("backend engineer", {})


def test_capabilities_returns_flags_per_source():
    matrix = build_capability_matrix([Tool(name="search_jobs", input_schema={"type": "object", "properties": {}})])
    with patch("app.api.routes.explore.mcp_explore.get_all_capabilities", AsyncMock(return_value={"jobo": matrix})):
        response = client.get("/explore/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["jobo"]["flags"]["search"] is True
    assert body["jobo"]["required_filters"] == []


def test_capabilities_surfaces_required_filters():
    matrix = build_capability_matrix(
        [
            Tool(
                name="search_jobs",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ]
    )
    with patch("app.api.routes.explore.mcp_explore.get_all_capabilities", AsyncMock(return_value={"hasdata": matrix})):
        response = client.get("/explore/capabilities")

    assert response.json()["hasdata"]["required_filters"] == ["location"]


def test_save_inserts_job_and_reports_inserted_true():
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=1)) as mock_insert:
        response = client.post("/explore/save", json=RESULT)

    assert response.status_code == 200
    assert response.json()["inserted"] is True
    job = mock_insert.call_args[0][1][0]
    assert job["source"] == "jobo"
    assert job["description_hash"] != RESULT["description_hash"]  # recomputed server-side, not trusted
    # Live bug (2026-09-19): salary_min/salary_max were silently dropped
    # here — HasData results have real salary data that never made it
    # into the jobs table on save.
    assert job["salary_min"] == 1000000
    assert job["salary_max"] == 1500000


def test_save_coerces_a_json_date_string_posted_at_into_a_real_datetime():
    # Live bug (2026-09-19): ExploreResultOut.posted_at used to be typed
    # `datetime | str | None` — pydantic's smart-union matching kept an
    # incoming JSON string as plain `str` rather than coercing it, so this
    # reached asyncpg as a raw string for a TIMESTAMP column and 500'd
    # (manifesting in a browser as a misleading CORS error, since a failed
    # response never gets CORS headers attached).
    result = {**RESULT, "posted_at": "2026-07-18T09:21:36.070313Z"}
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=1)) as mock_insert:
        response = client.post("/explore/save", json=result)

    assert response.status_code == 200
    job = mock_insert.call_args[0][1][0]
    assert isinstance(job["posted_at"], datetime)


def test_save_reports_inserted_false_for_a_duplicate():
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=0)):
        response = client.post("/explore/save", json=RESULT)

    assert response.json()["inserted"] is False


def test_save_passes_posted_at_through_to_insert_jobs():
    result = {**RESULT, "posted_at": "2026-09-10T00:00:00Z"}
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=1)) as mock_insert:
        response = client.post("/explore/save", json=result)

    assert response.status_code == 200
    job = mock_insert.call_args[0][1][0]
    assert job["posted_at"] is not None


def test_save_queues_auto_analyze_only_on_a_real_insert():
    # BackgroundTasks callbacks run after the response is sent but still
    # within TestClient's synchronous request — patching _auto_analyze
    # itself (rather than letting it run for real) keeps this test from
    # needing a live DB/LLM.
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=1)), \
         patch("app.api.routes.explore._auto_analyze", AsyncMock()) as mock_auto_analyze:
        response = client.post("/explore/save", json=RESULT)

    assert response.status_code == 200
    mock_auto_analyze.assert_called_once()
    # Recomputed server-side, same hash insert_jobs was called with.
    called_hash = mock_auto_analyze.call_args[0][0]
    assert called_hash == description_hash(RESULT["description"])


def test_save_does_not_queue_auto_analyze_for_a_duplicate():
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=0)), \
         patch("app.api.routes.explore._auto_analyze", AsyncMock()) as mock_auto_analyze:
        response = client.post("/explore/save", json=RESULT)

    assert response.status_code == 200
    mock_auto_analyze.assert_not_called()


async def test_auto_analyze_runs_the_pipeline_for_a_job_matching_the_hash(db_session):
    from app.api.routes.explore import _auto_analyze
    from tests.conftest import make_job

    job = await make_job(db_session, description_hash="a" * 64, status="DISCOVERED")

    with patch("app.api.routes.explore.get_session_factory", return_value=lambda: db_session), \
         patch("app.api.routes.explore.jobs_service.analyze_job", AsyncMock()) as mock_analyze:
        await _auto_analyze("a" * 64)

    mock_analyze.assert_called_once()
    assert mock_analyze.call_args[0][1].id == job.id


async def test_auto_analyze_is_a_noop_when_no_job_matches_the_hash(db_session):
    from app.api.routes.explore import _auto_analyze

    with patch("app.api.routes.explore.get_session_factory", return_value=lambda: db_session), \
         patch("app.api.routes.explore.jobs_service.analyze_job", AsyncMock()) as mock_analyze:
        await _auto_analyze("does-not-exist")

    mock_analyze.assert_not_called()


async def test_auto_analyze_swallows_an_analyze_job_failure(db_session):
    from app.api.routes.explore import _auto_analyze
    from tests.conftest import make_job

    await make_job(db_session, description_hash="b" * 64, status="DISCOVERED")

    with patch("app.api.routes.explore.get_session_factory", return_value=lambda: db_session), \
         patch("app.api.routes.explore.jobs_service.analyze_job", AsyncMock(side_effect=RuntimeError("boom"))):
        await _auto_analyze("b" * 64)  # must not raise
