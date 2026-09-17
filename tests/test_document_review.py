from unittest.mock import MagicMock, patch

from app.services.ats_validator import AtsValidationResult
from app.services.claim_validator import ClaimValidationOutcome
from app.services.document_review import (
    DocumentReviewResult,
    record_validation_result,
    review_generated_document,
)
from app.llm.schemas import ClaimCheckResult


def _make_mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    return mock_engine, mock_conn


def test_record_validation_result_executes_update_with_expected_params():
    mock_engine, mock_conn = _make_mock_engine()

    with patch("app.services.document_review.get_engine", return_value=mock_engine):
        record_validation_result(document_id=42, claim_check_passed=True, ats_check_passed=False)

    assert mock_conn.execute.called
    _, params = mock_conn.execute.call_args[0]
    assert params == {"claim_check_passed": True, "ats_check_passed": False, "document_id": 42}


def test_document_review_result_ready_only_when_both_pass():
    claim_check = ClaimValidationOutcome(
        passed=True,
        result=ClaimCheckResult(all_verified=True, items=[], blocking_claims=[]),
    )
    ats_check_pass = AtsValidationResult(passed=True, reasons=[])
    ats_check_fail = AtsValidationResult(passed=False, reasons=["contains a table"])

    assert DocumentReviewResult(claim_check=claim_check, ats_check=ats_check_pass).ready_for_review
    assert not DocumentReviewResult(claim_check=claim_check, ats_check=ats_check_fail).ready_for_review


def test_review_generated_document_runs_both_checks_and_records_result(tmp_path):
    claim_outcome = ClaimValidationOutcome(
        passed=True,
        result=ClaimCheckResult(all_verified=True, items=[], blocking_claims=[]),
    )
    ats_outcome = AtsValidationResult(passed=True, reasons=[])

    with patch("app.services.document_review.validate_claims", return_value=claim_outcome) as mock_claims, \
         patch("app.services.document_review.validate_ats", return_value=ats_outcome) as mock_ats, \
         patch("app.services.document_review.record_validation_result") as mock_record:
        result = review_generated_document(
            document_id=1,
            document_text="some text",
            docx_path="resume.docx",
            evidence_path="data/evidence.yaml",
            required_snippets=["Test Candidate"],
            workdir=str(tmp_path),
        )

    mock_claims.assert_called_once_with("some text", "data/evidence.yaml")
    mock_ats.assert_called_once_with("resume.docx", "some text", ["Test Candidate"], str(tmp_path))
    mock_record.assert_called_once_with(1, True, True)
    assert result.ready_for_review
