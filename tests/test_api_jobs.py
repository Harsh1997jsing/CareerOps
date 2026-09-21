from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.main import app
from app.core import get_db
from app.llm.schemas import JobFitAnalysis
from app.models import GeneratedDocument
from app.schemas import ApplicationItem, FilterResult, GeneratedDocumentItem, JobDetail, JobListItem
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

    assert mock_list.call_args.kwargs == {"limit": 50, "offset": 0, "q": None, "posted_within_days": None}


def test_list_jobs_passes_custom_limit_and_offset():
    with patch("app.api.routes.jobs.jobs_service.list_jobs", AsyncMock(return_value=[])) as mock_list:
        client.get("/jobs?limit=10&offset=20")

    assert mock_list.call_args.kwargs == {"limit": 10, "offset": 20, "q": None, "posted_within_days": None}


def test_list_jobs_passes_q_and_posted_within_days_query_params():
    with patch("app.api.routes.jobs.jobs_service.list_jobs", AsyncMock(return_value=[])) as mock_list:
        client.get("/jobs?q=python&posted_within_days=3")

    assert mock_list.call_args.kwargs == {"limit": 50, "offset": 0, "q": "python", "posted_within_days": 3}


def test_list_jobs_rejects_posted_within_days_below_1():
    response = client.get("/jobs?posted_within_days=0")
    assert response.status_code == 422


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


def test_reject_job_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/jobs/1/reject")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_reject_job_sets_status_and_returns_action():
    job = MagicMock()
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=job)), \
         patch("app.api.routes.jobs.jobs_service.set_job_status", AsyncMock()) as mock_set:
        response = client.post("/jobs/1/reject")

    assert response.status_code == 200
    assert response.json() == {"job_id": 1, "status": "REJECTED"}
    mock_set.assert_called_once_with(mock_set.call_args[0][0], job, "REJECTED")


def test_reject_job_returns_404_when_missing():
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=None)):
        response = client.post("/jobs/999/reject")

    assert response.status_code == 404


def test_restore_job_sets_status_and_returns_action():
    job = MagicMock()
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=job)), \
         patch("app.api.routes.jobs.jobs_service.set_job_status", AsyncMock()) as mock_set:
        response = client.post("/jobs/1/restore")

    assert response.status_code == 200
    assert response.json() == {"job_id": 1, "status": "DISCOVERED"}
    mock_set.assert_called_once_with(mock_set.call_args[0][0], job, "DISCOVERED")


def test_restore_job_returns_404_when_missing():
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=None)):
        response = client.post("/jobs/999/restore")

    assert response.status_code == 404


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


def test_analyze_job_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/jobs/1/analyze")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_analyze_job_returns_404_when_missing():
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=None)):
        response = client.post("/jobs/999/analyze")

    assert response.status_code == 404


def test_analyze_job_scores_records_and_returns_updated_detail():
    job = MagicMock(description="Build things with Python.")
    analysis = JobFitAnalysis(
        eligible=True, fit_score=90, confidence="high",
        strong_matches=["Python"], missing_requirements=[], risks=[], summary="Great fit.",
    )
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=job)), \
         patch("app.api.routes.jobs.jobs_service.hard_filter_job", return_value=FilterResult(passed=True)), \
         patch("app.api.routes.jobs.job_scorer.score_job", return_value=analysis) as mock_score, \
         patch("app.api.routes.jobs.job_scorer.decide", return_value="READY_FOR_REVIEW") as mock_decide, \
         patch("app.api.routes.jobs.jobs_service.record_analysis", AsyncMock()) as mock_record, \
         patch("app.api.routes.jobs.jobs_service.set_job_status", AsyncMock()) as mock_set, \
         patch("app.api.routes.jobs.jobs_service.get_job", AsyncMock(return_value=JOB_DETAIL)):
        response = client.post("/jobs/1/analyze")

    assert response.status_code == 200
    assert response.json()["job_id"] == 1
    mock_score.assert_called_once()
    mock_record.assert_called_once_with(mock_record.call_args[0][0], job, analysis)
    mock_decide.assert_called_once_with(analysis)
    mock_set.assert_called_once_with(mock_set.call_args[0][0], job, "READY_FOR_REVIEW")


def test_analyze_job_short_circuits_on_failed_hard_filter():
    # CLAUDE.md: only jobs that pass hard_filters should ever reach the
    # LLM scorer — a failing job is rejected without spending a Claude call.
    job = MagicMock(description="Unpaid internship, Mumbai.")
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=job)), \
         patch(
             "app.api.routes.jobs.jobs_service.hard_filter_job",
             return_value=FilterResult(passed=False, reasons=["location 'Mumbai' not in allowed_locations"]),
         ), \
         patch("app.api.routes.jobs.job_scorer.score_job") as mock_score, \
         patch("app.api.routes.jobs.jobs_service.record_analysis", AsyncMock()) as mock_record, \
         patch("app.api.routes.jobs.jobs_service.set_job_status", AsyncMock()) as mock_set, \
         patch("app.api.routes.jobs.jobs_service.get_job", AsyncMock(return_value=JOB_DETAIL)):
        response = client.post("/jobs/1/analyze")

    assert response.status_code == 200
    mock_score.assert_not_called()
    mock_record.assert_not_called()
    mock_set.assert_called_once_with(mock_set.call_args[0][0], job, "REJECT")


def test_generate_document_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/jobs/1/documents", json={"type": "resume"})
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_generate_document_returns_404_when_job_missing():
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=None)):
        response = client.post("/jobs/999/documents", json={"type": "resume"})

    assert response.status_code == 404


def test_generate_document_rejects_invalid_type():
    job = MagicMock()
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=job)):
        response = client.post("/jobs/1/documents", json={"type": "portfolio"})

    assert response.status_code == 422


def test_generate_document_returns_generated_document():
    job = MagicMock()
    document = GeneratedDocument(
        id=9, job_id=1, type="resume", file_path="data/generated_documents/job_1_resume_v1.docx",
        version=1, claim_check_passed=True, ats_check_passed=True,
    )
    with patch("app.api.routes.jobs.jobs_service.get_job_by_id", AsyncMock(return_value=job)), \
         patch("app.api.routes.jobs.document_generator.generate_document", AsyncMock(return_value=document)) as mock_gen:
        response = client.post("/jobs/1/documents", json={"type": "resume"})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 9
    assert body["claim_check_passed"] is True
    mock_gen.assert_called_once_with(mock_gen.call_args[0][0], job, "resume")
