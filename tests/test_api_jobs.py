from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.main import app
from app.schemas import ApplicationItem, GeneratedDocumentItem, JobDetail, JobListItem
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

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


def test_list_jobs_requires_authentication():
    # Audit finding F1: /jobs required no auth at all. This asserts the fix
    # actually holds, by removing this module's own override and confirming
    # the route falls through to the real get_current_user dependency.
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.get("/jobs")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_list_jobs_returns_mapped_items():
    with patch("app.api.routes.jobs.jobs_service.list_jobs", AsyncMock(return_value=[JOB_LIST_ITEM])):
        response = client.get("/jobs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["company"] == "Acme"


def test_list_jobs_passes_status_query_param():
    with patch("app.api.routes.jobs.jobs_service.list_jobs", AsyncMock(return_value=[])) as mock_list:
        client.get("/jobs?status=REVIEW_REQUIRED")

    mock_list.assert_called_once()
    assert mock_list.call_args[0][1] == "REVIEW_REQUIRED"


def test_list_jobs_defaults_to_limit_50_offset_0():
    # Audit finding F8: /jobs was previously unbounded.
    with patch("app.api.routes.jobs.jobs_service.list_jobs", AsyncMock(return_value=[])) as mock_list:
        client.get("/jobs")

    assert mock_list.call_args.kwargs == {"limit": 50, "offset": 0}


def test_list_jobs_passes_custom_limit_and_offset():
    with patch("app.api.routes.jobs.jobs_service.list_jobs", AsyncMock(return_value=[])) as mock_list:
        client.get("/jobs?limit=10&offset=20")

    assert mock_list.call_args.kwargs == {"limit": 10, "offset": 20}


def test_list_jobs_rejects_limit_over_200():
    response = client.get("/jobs?limit=500")
    assert response.status_code == 422


def test_list_jobs_rejects_negative_offset():
    response = client.get("/jobs?offset=-1")
    assert response.status_code == 422


def test_get_job_returns_404_when_missing():
    with patch("app.api.routes.jobs.jobs_service.get_job", AsyncMock(return_value=None)):
        response = client.get("/jobs/999")

    assert response.status_code == 404


def test_get_job_returns_detail_with_application():
    with patch("app.api.routes.jobs.jobs_service.get_job", AsyncMock(return_value=JOB_DETAIL)):
        response = client.get("/jobs/1")

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Build things."
    assert body["application"]["application_id"] == 5


def test_get_job_returns_null_application_when_none():
    detail = JobDetail(**{**vars(JOB_DETAIL), "application": None})
    with patch("app.api.routes.jobs.jobs_service.get_job", AsyncMock(return_value=detail)):
        response = client.get("/jobs/1")

    assert response.json()["application"] is None


def test_list_documents_returns_mapped_items():
    doc = GeneratedDocumentItem(
        id=9, type="resume", file_path="generated/resume_v1.docx", version=1,
        claim_check_passed=True, ats_check_passed=False,
    )
    with patch("app.api.routes.jobs.jobs_service.list_generated_documents", AsyncMock(return_value=[doc])):
        response = client.get("/jobs/1/documents")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["claim_check_passed"] is True
    assert body[0]["ats_check_passed"] is False
