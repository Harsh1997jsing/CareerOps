from unittest.mock import AsyncMock, patch

from app.llm.schemas import GeneratedResumeSection
from app.services.applications import get_application_for_job
from app.services.cover_letter import CoverLetterResult
from app.services.document_generator import generate_document
from app.services.resume_generator import ResumeGenerationResult
from tests.conftest import make_job


class _FakeSettings:
    def __init__(self, tmp_path):
        self.profile_path = str(tmp_path / "profile.yaml")
        self.skills_path = str(tmp_path / "skills.yaml")
        self.evidence_path = str(tmp_path / "evidence.yaml")
        self.voice_samples_dir = str(tmp_path / "voice_samples")
        self.documents_dir = str(tmp_path / "generated_documents")


def _fake_settings(tmp_path):
    (tmp_path / "profile.yaml").write_text("name: Test Candidate\n")
    return _FakeSettings(tmp_path)


_FAKE_RESUME_RESULT = ResumeGenerationResult(
    sections=[GeneratedResumeSection(section="summary", content="Built things.", evidence_ids_used=["EXP001"])]
)
_FAKE_COVER_LETTER_RESULT = CoverLetterResult(
    content="Dear hiring team, ...", word_count=250, evidence_ids_used=["EXP001"]
)


async def test_generate_document_resume_creates_document_and_application(db_session, tmp_path):
    job = await make_job(db_session)
    settings = _fake_settings(tmp_path)

    with patch("app.services.document_generator.get_settings", return_value=settings), \
         patch(
             "app.services.document_generator.resume_generator_service.generate_resume",
             return_value=_FAKE_RESUME_RESULT,
         ) as mock_generate, \
         patch("app.services.document_generator.write_resume_docx") as mock_write, \
         patch(
             "app.services.document_generator.document_review.review_generated_document", AsyncMock()
         ) as mock_review:
        document = await generate_document(db_session, job, "resume")

    assert document.job_id == job.id
    assert document.type == "resume"
    assert document.version == 1
    mock_generate.assert_called_once_with(job.description, settings.skills_path, settings.evidence_path)
    mock_write.assert_called_once()
    mock_review.assert_called_once()

    application = await get_application_for_job(db_session, job.id)
    assert application is not None
    assert application.status == "READY_FOR_REVIEW"


async def test_generate_document_cover_letter_creates_document(db_session, tmp_path):
    job = await make_job(db_session)
    settings = _fake_settings(tmp_path)

    with patch("app.services.document_generator.get_settings", return_value=settings), \
         patch(
             "app.services.document_generator.cover_letter_service.generate_cover_letter",
             return_value=_FAKE_COVER_LETTER_RESULT,
         ), \
         patch("app.services.document_generator.write_cover_letter_docx") as mock_write, \
         patch("app.services.document_generator.document_review.review_generated_document", AsyncMock()):
        document = await generate_document(db_session, job, "cover_letter")

    assert document.type == "cover_letter"
    assert document.version == 1
    mock_write.assert_called_once()


async def test_generate_document_increments_version_per_job_and_type(db_session, tmp_path):
    job = await make_job(db_session)
    settings = _fake_settings(tmp_path)

    with patch("app.services.document_generator.get_settings", return_value=settings), \
         patch(
             "app.services.document_generator.resume_generator_service.generate_resume",
             return_value=_FAKE_RESUME_RESULT,
         ), \
         patch("app.services.document_generator.write_resume_docx"), \
         patch("app.services.document_generator.document_review.review_generated_document", AsyncMock()):
        first = await generate_document(db_session, job, "resume")
        second = await generate_document(db_session, job, "resume")

    assert first.version == 1
    assert second.version == 2


async def test_generate_document_reuses_existing_application(db_session, tmp_path):
    job = await make_job(db_session)
    settings = _fake_settings(tmp_path)

    with patch("app.services.document_generator.get_settings", return_value=settings), \
         patch(
             "app.services.document_generator.resume_generator_service.generate_resume",
             return_value=_FAKE_RESUME_RESULT,
         ), \
         patch("app.services.document_generator.write_resume_docx"), \
         patch("app.services.document_generator.document_review.review_generated_document", AsyncMock()):
        await generate_document(db_session, job, "resume")
        await generate_document(db_session, job, "resume")

    # Two documents, but still exactly one Application row for the job —
    # get_application_for_job() itself assumes at most one (.first()), so
    # a second row would silently hide behind the first.
    from sqlalchemy import select

    from app.models import Application

    applications = (await db_session.scalars(select(Application).where(Application.job_id == job.id))).all()
    assert len(applications) == 1
