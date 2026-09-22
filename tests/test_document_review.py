from unittest.mock import AsyncMock, patch

from app.models import GeneratedDocument, Job
from app.services.ats_validator import AtsValidationResult
from app.services.claim_validator import ClaimValidationOutcome
from app.services.document_review import (
    DocumentReviewResult,
    record_validation_result,
    review_generated_document,
)
from app.llm.schemas import ClaimCheckResult


async def test_record_validation_result_updates_the_document_row(db_session):
    db_session.add(Job(
        id=1, source="greenhouse", company="Acme", title="Engineer",
        url="https://example.com", description="desc",
    ))
    db_session.add(GeneratedDocument(id=42, job_id=1, type="resume", version=1))
    await db_session.commit()

    await record_validation_result(document_id=42, claim_check_passed=True, ats_check_passed=False, session=db_session)

    document = await db_session.get(GeneratedDocument, 42)
    assert document.claim_check_passed is True
    assert document.ats_check_passed is False


async def test_record_validation_result_no_ops_when_document_missing(db_session):
    # Mirrors the old raw-SQL UPDATE's silent no-op on zero matched rows.
    await record_validation_result(document_id=999, claim_check_passed=True, ats_check_passed=True, session=db_session)


def test_document_review_result_ready_only_when_both_pass():
    claim_check = ClaimValidationOutcome(
        passed=True,
        result=ClaimCheckResult(all_verified=True, items=[], blocking_claims=[]),
    )
    ats_check_pass = AtsValidationResult(passed=True, reasons=[])
    ats_check_fail = AtsValidationResult(passed=False, reasons=["contains a table"])

    assert DocumentReviewResult(claim_check=claim_check, ats_check=ats_check_pass).ready_for_review
    assert not DocumentReviewResult(claim_check=claim_check, ats_check=ats_check_fail).ready_for_review


async def test_review_generated_document_runs_both_checks_and_records_result(tmp_path):
    claim_outcome = ClaimValidationOutcome(
        passed=True,
        result=ClaimCheckResult(all_verified=True, items=[], blocking_claims=[]),
    )
    ats_outcome = AtsValidationResult(passed=True, reasons=[])

    with patch("app.services.document_review.validate_claims", return_value=claim_outcome) as mock_claims, \
         patch("app.services.document_review.validate_ats", return_value=ats_outcome) as mock_ats, \
         patch("app.services.document_review.record_validation_result", AsyncMock()) as mock_record:
        result = await review_generated_document(
            document_id=1,
            document_text="some text",
            docx_path="resume.docx",
            evidence_path="data/evidence.yaml",
            required_snippets=["Test Candidate"],
            workdir=str(tmp_path),
        )

    mock_claims.assert_called_once_with("some text", "data/evidence.yaml")
    mock_ats.assert_called_once_with("resume.docx", "some text", ["Test Candidate"], str(tmp_path))
    mock_record.assert_called_once_with(1, True, True, session=None)
    assert result.ready_for_review


async def test_review_generated_document_threads_the_caller_session_through(tmp_path, db_session):
    claim_outcome = ClaimValidationOutcome(
        passed=True,
        result=ClaimCheckResult(all_verified=True, items=[], blocking_claims=[]),
    )
    ats_outcome = AtsValidationResult(passed=True, reasons=[])

    with patch("app.services.document_review.validate_claims", return_value=claim_outcome), \
         patch("app.services.document_review.validate_ats", return_value=ats_outcome), \
         patch("app.services.document_review.record_validation_result", AsyncMock()) as mock_record:
        await review_generated_document(
            document_id=1, document_text="some text", docx_path="resume.docx",
            evidence_path="data/evidence.yaml", required_snippets=[], workdir=str(tmp_path),
            session=db_session,
        )

    mock_record.assert_called_once_with(1, True, True, session=db_session)


async def test_review_generated_document_records_ats_as_none_when_libreoffice_missing(tmp_path):
    # RuntimeError is ats_validator.convert_docx_to_pdf()'s documented
    # failure mode when LibreOffice isn't installed — the request must
    # still succeed, with ats_check_passed recorded as None ("didn't
    # run"), not as a false pass or a false fail, and never let the
    # RuntimeError itself propagate out of this function.
    claim_outcome = ClaimValidationOutcome(
        passed=True,
        result=ClaimCheckResult(all_verified=True, items=[], blocking_claims=[]),
    )

    with patch("app.services.document_review.validate_claims", return_value=claim_outcome), \
         patch("app.services.document_review.validate_ats", side_effect=RuntimeError("soffice not found")), \
         patch("app.services.document_review.record_validation_result", AsyncMock()) as mock_record:
        result = await review_generated_document(
            document_id=1, document_text="some text", docx_path="resume.docx",
            evidence_path="data/evidence.yaml", required_snippets=[], workdir=str(tmp_path),
        )

    mock_record.assert_called_once_with(1, True, None, session=None)
    assert not result.ats_check.passed
    assert not result.ready_for_review
