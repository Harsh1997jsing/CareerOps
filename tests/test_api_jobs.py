from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_engine
from app.api.main import app
from app.services.dashboard_data import ApplicationItem, JobDetail, JobListItem

client = TestClient(app)
app.dependency_overrides[get_db_engine] = lambda: MagicMock()

JOB_LIST_ITEM = JobListItem(
    job_id=1, company="Acme", title="Backend Engineer", location="Remote",
    url="https://example.com/job/1", status="READY_FOR_REVIEW",
    fit_score=82, confidence="high", strong_matches=["Python"], missing_skills=[], risks=[],
)

JOB_DETAIL = JobDetail(
    job_id=1, company="Acme", title="Backend Engineer", location="Remote",
    url="https://example.com/job/1", description="Build things.", status="READY_FOR_REVIEW",
    fit_score=82, confidence="high", strong_matches=["Python"], missing_skills=[], risks=[],
    application=ApplicationItem(application_id=5, job_id=1, status="READY_FOR_REVIEW", applied_at=None),
)


def test_list_jobs_returns_mapped_items():
    with patch("app.api.routes.jobs.dashboard_data.list_jobs", return_value=[JOB_LIST_ITEM]):
        response = client.get("/jobs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["company"] == "Acme"


def test_list_jobs_passes_status_query_param():
    with patch("app.api.routes.jobs.dashboard_data.list_jobs", return_value=[]) as mock_list:
        client.get("/jobs?status=REVIEW_REQUIRED")

    mock_list.assert_called_once()
    _, kwargs = mock_list.call_args
    assert mock_list.call_args[0][1] == "REVIEW_REQUIRED"


def test_get_job_returns_404_when_missing():
    with patch("app.api.routes.jobs.dashboard_data.get_job", return_value=None):
        response = client.get("/jobs/999")

    assert response.status_code == 404


def test_get_job_returns_detail_with_application():
    with patch("app.api.routes.jobs.dashboard_data.get_job", return_value=JOB_DETAIL):
        response = client.get("/jobs/1")

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Build things."
    assert body["application"]["application_id"] == 5


def test_get_job_returns_null_application_when_none():
    detail = JobDetail(**{**vars(JOB_DETAIL), "application": None})
    with patch("app.api.routes.jobs.dashboard_data.get_job", return_value=detail):
        response = client.get("/jobs/1")

    assert response.json()["application"] is None


def test_list_documents_returns_mapped_items():
    from app.services.dashboard_data import GeneratedDocumentItem

    doc = GeneratedDocumentItem(
        id=9, type="resume", file_path="generated/resume_v1.docx", version=1,
        claim_check_passed=True, ats_check_passed=False,
    )
    with patch("app.api.routes.jobs.dashboard_data.list_generated_documents", return_value=[doc]):
        response = client.get("/jobs/1/documents")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["claim_check_passed"] is True
    assert body[0]["ats_check_passed"] is False
