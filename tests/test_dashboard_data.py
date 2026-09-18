from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.dashboard_data import (
    APPROVED_STATUS,
    REJECTED_STATUS,
    _row_to_application_item,
    _row_to_generated_document_item,
    _row_to_job_list_item,
    approve_application,
    check_cooldown_for_company,
    get_application_context,
    get_application_for_job,
    get_job,
    list_generated_documents,
    list_jobs,
    reject_application,
    set_application_status,
)


def _make_connect_mock_engine(mappings_all_return=None, mappings_first_return=None):
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    execute_result = mock_conn.execute.return_value
    execute_result.mappings.return_value.all.return_value = mappings_all_return or []
    execute_result.mappings.return_value.first.return_value = mappings_first_return
    return mock_engine, mock_conn


def _make_begin_mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    return mock_engine, mock_conn


JOB_ROW = {
    "id": 1, "company": "Acme", "title": "Backend Engineer", "location": "Remote",
    "url": "https://example.com/job/1", "status": "READY_FOR_REVIEW",
    "fit_score": 82, "confidence": "high",
    "strong_matches": ["Python", "FastAPI"], "missing_skills": ["Kubernetes"], "risks": [],
}


def test_row_to_job_list_item_maps_all_fields():
    item = _row_to_job_list_item(JOB_ROW)

    assert item.job_id == 1
    assert item.company == "Acme"
    assert item.fit_score == 82
    assert item.strong_matches == ["Python", "FastAPI"]
    assert item.missing_skills == ["Kubernetes"]


def test_row_to_job_list_item_defaults_null_json_fields_to_empty_list():
    row = {**JOB_ROW, "strong_matches": None, "missing_skills": None, "risks": None}
    item = _row_to_job_list_item(row)

    assert item.strong_matches == []
    assert item.missing_skills == []
    assert item.risks == []


def test_list_jobs_returns_mapped_items():
    mock_engine, mock_conn = _make_connect_mock_engine(mappings_all_return=[JOB_ROW])

    jobs = list_jobs(mock_engine)

    assert len(jobs) == 1
    assert jobs[0].company == "Acme"
    assert mock_conn.execute.called


def test_list_jobs_passes_status_filter_param():
    mock_engine, mock_conn = _make_connect_mock_engine(mappings_all_return=[])

    list_jobs(mock_engine, status="REVIEW_REQUIRED")

    _, params = mock_conn.execute.call_args[0]
    assert params == {"status": "REVIEW_REQUIRED"}


def test_row_to_application_item_maps_fields():
    row = {"id": 5, "job_id": 1, "status": "READY_FOR_REVIEW", "applied_at": None}
    item = _row_to_application_item(row)

    assert item.application_id == 5
    assert item.job_id == 1
    assert item.applied_at is None


def test_get_application_for_job_returns_none_when_missing():
    mock_engine, _ = _make_connect_mock_engine(mappings_first_return=None)

    assert get_application_for_job(mock_engine, job_id=1) is None


def test_get_application_for_job_returns_item_when_found():
    row = {"id": 5, "job_id": 1, "status": "READY_FOR_REVIEW", "applied_at": None}
    mock_engine, _ = _make_connect_mock_engine(mappings_first_return=row)

    application = get_application_for_job(mock_engine, job_id=1)

    assert application.application_id == 5


def test_row_to_generated_document_item_maps_fields():
    row = {
        "id": 9, "type": "resume", "file_path": "generated/resume_v1.docx", "version": 1,
        "claim_check_passed": True, "ats_check_passed": False,
    }
    item = _row_to_generated_document_item(row)

    assert item.id == 9
    assert item.claim_check_passed is True
    assert item.ats_check_passed is False


def test_list_generated_documents_returns_mapped_items():
    row = {
        "id": 9, "type": "resume", "file_path": "generated/resume_v1.docx", "version": 1,
        "claim_check_passed": True, "ats_check_passed": True,
    }
    mock_engine, mock_conn = _make_connect_mock_engine(mappings_all_return=[row])

    docs = list_generated_documents(mock_engine, job_id=1)

    assert len(docs) == 1
    assert docs[0].type == "resume"
    _, params = mock_conn.execute.call_args[0]
    assert params == {"job_id": 1}


def test_check_cooldown_for_company_blocks_recent_application():
    mock_engine = MagicMock()
    recent_date = datetime.now() - timedelta(days=5)

    with patch("app.services.dashboard_data.get_company_applied_dates", return_value=[recent_date]):
        result = check_cooldown_for_company(mock_engine, "Acme", cooldown_days=30)

    assert not result.passed


def test_check_cooldown_for_company_allows_no_history():
    mock_engine = MagicMock()

    with patch("app.services.dashboard_data.get_company_applied_dates", return_value=[]):
        result = check_cooldown_for_company(mock_engine, "Acme", cooldown_days=30)

    assert result.passed


def test_set_application_status_executes_update_with_params():
    mock_engine, mock_conn = _make_begin_mock_engine()

    set_application_status(mock_engine, application_id=7, status="APPROVED")

    _, params = mock_conn.execute.call_args[0]
    assert params == {"status": "APPROVED", "application_id": 7}


def test_approve_application_uses_approved_status():
    mock_engine, mock_conn = _make_begin_mock_engine()

    approve_application(mock_engine, application_id=7)

    _, params = mock_conn.execute.call_args[0]
    assert params["status"] == APPROVED_STATUS


def test_reject_application_uses_rejected_status():
    mock_engine, mock_conn = _make_begin_mock_engine()

    reject_application(mock_engine, application_id=7)

    _, params = mock_conn.execute.call_args[0]
    assert params["status"] == REJECTED_STATUS


JOB_DETAIL_ROW = {**JOB_ROW, "description": "Build things with Python."}


def test_get_job_returns_none_when_missing():
    mock_engine, _ = _make_connect_mock_engine(mappings_first_return=None)

    assert get_job(mock_engine, job_id=1) is None


def test_get_job_maps_fields_and_includes_application():
    mock_engine, mock_conn = _make_connect_mock_engine(mappings_first_return=JOB_DETAIL_ROW)
    application = _row_to_application_item({"id": 5, "job_id": 1, "status": "READY_FOR_REVIEW", "applied_at": None})

    with patch("app.services.dashboard_data.get_application_for_job", return_value=application):
        job = get_job(mock_engine, job_id=1)

    assert job.job_id == 1
    assert job.description == "Build things with Python."
    assert job.strong_matches == ["Python", "FastAPI"]
    assert job.application is application
    _, params = mock_conn.execute.call_args[0]
    assert params == {"job_id": 1}


def test_get_job_defaults_null_json_fields_to_empty_list():
    row = {**JOB_DETAIL_ROW, "strong_matches": None, "missing_skills": None, "risks": None}
    mock_engine, _ = _make_connect_mock_engine(mappings_first_return=row)

    with patch("app.services.dashboard_data.get_application_for_job", return_value=None):
        job = get_job(mock_engine, job_id=1)

    assert job.strong_matches == []
    assert job.missing_skills == []
    assert job.risks == []


def test_get_application_context_returns_none_when_missing():
    mock_engine, _ = _make_connect_mock_engine(mappings_first_return=None)

    assert get_application_context(mock_engine, application_id=7) is None


def test_get_application_context_maps_fields():
    row = {"application_id": 7, "job_id": 1, "company": "Acme", "url": "https://example.com/job/1"}
    mock_engine, mock_conn = _make_connect_mock_engine(mappings_first_return=row)

    context = get_application_context(mock_engine, application_id=7)

    assert context.application_id == 7
    assert context.job_id == 1
    assert context.company == "Acme"
    assert context.url == "https://example.com/job/1"
    _, params = mock_conn.execute.call_args[0]
    assert params == {"application_id": 7}
