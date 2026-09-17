from pathlib import Path
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from app.services.dashboard_data import ApplicationItem, GeneratedDocumentItem, JobListItem
from app.services.hard_filters import FilterResult

DASHBOARD_PATH = str(Path(__file__).resolve().parent.parent / "app" / "dashboard.py")

FAKE_JOB = JobListItem(
    job_id=1, company="Acme", title="Backend Engineer", location="Remote",
    url="https://example.com/job/1", status="READY_FOR_REVIEW",
    fit_score=82, confidence="high",
    strong_matches=["Python", "FastAPI"], missing_skills=["Kubernetes"], risks=[],
)

PASSING_COOLDOWN = FilterResult(passed=True, reasons=[])
BLOCKED_COOLDOWN = FilterResult(passed=False, reasons=["applied to Acme 5 days ago; 25 days left in cooldown"])


def _patched_engine():
    return patch("app.db.get_engine", return_value=MagicMock())


def _load_app() -> AppTest:
    # Generous timeout: the first script run in a test session pays Streamlit's
    # module cold-start cost, well past the 3s default.
    return AppTest.from_file(DASHBOARD_PATH, default_timeout=15)


def test_dashboard_renders_job_with_no_application_yet():
    with _patched_engine(), \
         patch("app.services.dashboard_data.list_jobs", return_value=[FAKE_JOB]), \
         patch("app.services.dashboard_data.list_generated_documents", return_value=[]), \
         patch("app.services.dashboard_data.get_application_for_job", return_value=None), \
         patch("app.services.dashboard_data.check_cooldown_for_company", return_value=PASSING_COOLDOWN):
        at = _load_app()
        at.run()

    assert not at.exception
    expander_labels = [e.label for e in at.expander]
    assert any("Acme" in label and "Backend Engineer" in label for label in expander_labels)


def test_dashboard_shows_empty_state_when_no_jobs():
    with _patched_engine(), \
         patch("app.services.dashboard_data.list_jobs", return_value=[]):
        at = _load_app()
        at.run()

    assert not at.exception
    assert any("No jobs found" in info.value for info in at.info)


def test_dashboard_shows_cooldown_warning():
    with _patched_engine(), \
         patch("app.services.dashboard_data.list_jobs", return_value=[FAKE_JOB]), \
         patch("app.services.dashboard_data.list_generated_documents", return_value=[]), \
         patch("app.services.dashboard_data.get_application_for_job", return_value=None), \
         patch("app.services.dashboard_data.check_cooldown_for_company", return_value=BLOCKED_COOLDOWN):
        at = _load_app()
        at.run()

    assert not at.exception
    assert any("cooldown" in w.value.lower() for w in at.warning)


def test_dashboard_approve_button_calls_approve_application():
    application = ApplicationItem(application_id=42, job_id=1, status="READY_FOR_REVIEW", applied_at=None)

    with _patched_engine(), \
         patch("app.services.dashboard_data.list_jobs", return_value=[FAKE_JOB]), \
         patch("app.services.dashboard_data.list_generated_documents", return_value=[]), \
         patch("app.services.dashboard_data.get_application_for_job", return_value=application), \
         patch("app.services.dashboard_data.check_cooldown_for_company", return_value=PASSING_COOLDOWN), \
         patch("app.services.dashboard_data.approve_application") as mock_approve:
        at = _load_app()
        at.run()
        at.expander[0].expanded = True
        at.run()
        at.button(key="approve_42").click().run()

    assert not at.exception
    mock_approve.assert_called_once()


def test_dashboard_lists_generated_documents():
    doc = GeneratedDocumentItem(
        id=9, type="resume", file_path="generated/does_not_exist.docx", version=1,
        claim_check_passed=True, ats_check_passed=False,
    )

    with _patched_engine(), \
         patch("app.services.dashboard_data.list_jobs", return_value=[FAKE_JOB]), \
         patch("app.services.dashboard_data.list_generated_documents", return_value=[doc]), \
         patch("app.services.dashboard_data.get_application_for_job", return_value=None), \
         patch("app.services.dashboard_data.check_cooldown_for_company", return_value=PASSING_COOLDOWN):
        at = _load_app()
        at.run()

    assert not at.exception
