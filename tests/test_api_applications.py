from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_engine
from app.api.main import app
from app.services.dashboard_data import ApplicationContext

client = TestClient(app)
app.dependency_overrides[get_db_engine] = lambda: MagicMock()

CONTEXT = ApplicationContext(application_id=7, job_id=1, company="Acme", url="https://example.com/job/1")


def test_approve_returns_404_when_application_missing():
    with patch("app.api.routes.applications.dashboard_data.get_application_context", return_value=None):
        response = client.post("/applications/999/approve")

    assert response.status_code == 404


def test_approve_sets_approved_status():
    with patch("app.api.routes.applications.dashboard_data.get_application_context", return_value=CONTEXT), \
         patch("app.api.routes.applications.dashboard_data.approve_application") as mock_approve:
        response = client.post("/applications/7/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    mock_approve.assert_called_once()


def test_reject_sets_rejected_status():
    with patch("app.api.routes.applications.dashboard_data.get_application_context", return_value=CONTEXT), \
         patch("app.api.routes.applications.dashboard_data.reject_application") as mock_reject:
        response = client.post("/applications/7/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    mock_reject.assert_called_once()


def test_open_calls_open_job_url_with_the_jobs_url():
    with patch("app.api.routes.applications.dashboard_data.get_application_context", return_value=CONTEXT), \
         patch("app.api.routes.applications.tracker.open_job_url") as mock_open:
        response = client.post("/applications/7/open")

    assert response.status_code == 200
    mock_open.assert_called_once_with("https://example.com/job/1")


def test_mark_applied_passes_confirmed_true_and_job_context():
    with patch("app.api.routes.applications.dashboard_data.get_application_context", return_value=CONTEXT), \
         patch("app.api.routes.applications.tracker.mark_applied") as mock_mark:
        response = client.post("/applications/7/mark-applied")

    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"
    mock_mark.assert_called_once_with(
        mock_mark.call_args[0][0],
        application_id=7,
        job_id=1,
        company="Acme",
        confirmed=True,
    )
