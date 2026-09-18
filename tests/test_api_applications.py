from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.main import app
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

# Stand-in for an Application ORM row with its Job eager-loaded (what
# applications_service.get_application() actually returns) — a plain
# namespace is enough since the route only reads attributes off it.
FAKE_JOB = SimpleNamespace(company="Acme", url="https://example.com/job/1")
FAKE_APPLICATION = SimpleNamespace(id=7, job_id=1, status="READY_FOR_REVIEW", job=FAKE_JOB)


def test_approve_requires_authentication():
    # Audit finding F1: /applications/* required no auth at all.
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/applications/7/approve")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_approve_returns_404_when_application_missing():
    with patch("app.api.routes.applications.applications_service.get_application", AsyncMock(return_value=None)):
        response = client.post("/applications/999/approve")

    assert response.status_code == 404


def test_approve_sets_approved_status():
    with patch("app.api.routes.applications.applications_service.get_application", AsyncMock(return_value=FAKE_APPLICATION)), \
         patch("app.api.routes.applications.applications_service.set_status", AsyncMock()) as mock_set_status:
        response = client.post("/applications/7/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    mock_set_status.assert_called_once_with(mock_set_status.call_args[0][0], FAKE_APPLICATION, "APPROVED")


def test_reject_sets_rejected_status():
    with patch("app.api.routes.applications.applications_service.get_application", AsyncMock(return_value=FAKE_APPLICATION)), \
         patch("app.api.routes.applications.applications_service.set_status", AsyncMock()) as mock_set_status:
        response = client.post("/applications/7/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    mock_set_status.assert_called_once_with(mock_set_status.call_args[0][0], FAKE_APPLICATION, "REJECTED")


def test_open_calls_open_job_url_with_the_jobs_url():
    with patch("app.api.routes.applications.applications_service.get_application", AsyncMock(return_value=FAKE_APPLICATION)), \
         patch("app.api.routes.applications.tracker.open_job_url") as mock_open:
        response = client.post("/applications/7/open")

    assert response.status_code == 200
    mock_open.assert_called_once_with("https://example.com/job/1")


def test_mark_applied_passes_confirmed_true_and_the_loaded_application():
    with patch("app.api.routes.applications.applications_service.get_application", AsyncMock(return_value=FAKE_APPLICATION)), \
         patch("app.api.routes.applications.tracker.mark_applied", AsyncMock()) as mock_mark:
        response = client.post("/applications/7/mark-applied")

    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"
    mock_mark.assert_called_once_with(
        mock_mark.call_args[0][0],
        application_id=7,
        job_id=1,
        company="Acme",
        confirmed=True,
        application=FAKE_APPLICATION,
    )
