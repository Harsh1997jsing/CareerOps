from unittest.mock import AsyncMock, patch

from app.llm.schemas import CoverLetterEditSuggestion, GeneratedResumeSection, ResumeEditSuggestion
from app.services.document_editor import (
    apply_cover_letter_edit,
    apply_resume_edit,
    suggest_cover_letter_edit,
    suggest_resume_edit,
)
from tests.conftest import make_job

CURRENT_SECTIONS = [
    GeneratedResumeSection(section="summary", content="Built things.", evidence_ids_used=["EXP001"]),
]


def test_suggest_resume_edit_calls_structured_call_with_current_sections_and_feedback(tmp_path):
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")
    fake_response = ResumeEditSuggestion(
        sections=[GeneratedResumeSection(section="summary", content="Built great things.", evidence_ids_used=["EXP001"])],
        change_summary="Made the summary punchier.",
    )

    with patch("app.services.document_editor.structured_call", return_value=fake_response) as mock_call:
        suggestion = suggest_resume_edit("Backend role", CURRENT_SECTIONS, "make it punchier", str(evidence_path))

    assert suggestion.change_summary == "Made the summary punchier."
    prompt = mock_call.call_args.args[0]
    assert "make it punchier" in prompt
    assert "Built things." in prompt


def test_suggest_cover_letter_edit_calls_structured_call_with_current_content_and_feedback(tmp_path):
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")
    fake_response = CoverLetterEditSuggestion(content="Dear team, revised...", change_summary="Shortened the opener.")

    with patch("app.services.document_editor.structured_call", return_value=fake_response) as mock_call:
        suggestion = suggest_cover_letter_edit(
            "Backend role", "Dear team, original...", "shorten the opener", str(evidence_path)
        )

    assert suggestion.change_summary == "Shortened the opener."
    prompt = mock_call.call_args.args[0]
    assert "shorten the opener" in prompt
    assert "Dear team, original..." in prompt


async def test_apply_resume_edit_persists_without_calling_the_model(db_session, tmp_path):
    job = await make_job(db_session)
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: Test Candidate\n")
    new_sections = [
        GeneratedResumeSection(section="summary", content="Built great things.", evidence_ids_used=["EXP001"]),
    ]

    with patch("app.services.document_generator.write_resume_docx") as mock_write, \
         patch("app.services.document_generator.document_review.review_generated_document", AsyncMock()):
        document = await apply_resume_edit(db_session, job, new_sections, str(profile_path))

    assert document.type == "resume"
    assert document.version == 1
    mock_write.assert_called_once()


async def test_apply_cover_letter_edit_persists_without_calling_the_model(db_session, tmp_path):
    job = await make_job(db_session)
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: Test Candidate\n")

    with patch("app.services.document_generator.write_cover_letter_docx") as mock_write, \
         patch("app.services.document_generator.document_review.review_generated_document", AsyncMock()):
        document = await apply_cover_letter_edit(db_session, job, "Dear team, revised...", str(profile_path))

    assert document.type == "cover_letter"
    assert document.version == 1
    mock_write.assert_called_once()


async def test_apply_resume_edit_increments_version_for_existing_document(db_session, tmp_path):
    job = await make_job(db_session)
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: Test Candidate\n")

    with patch("app.services.document_generator.write_resume_docx"), \
         patch("app.services.document_generator.document_review.review_generated_document", AsyncMock()):
        first = await apply_resume_edit(db_session, job, CURRENT_SECTIONS, str(profile_path))
        second = await apply_resume_edit(db_session, job, CURRENT_SECTIONS, str(profile_path))

    assert first.version == 1
    assert second.version == 2
