"""
Runs both Phase 3 validators against a generated document and records the
outcome on its generated_documents row. This is the single place that
flips claim_check_passed / ats_check_passed, so no other code path can mark
a document ready for review without actually running both checks.
"""

from dataclasses import dataclass

from sqlalchemy import text

from app.db import get_engine
from app.services.ats_validator import AtsValidationResult, validate_ats
from app.services.claim_validator import ClaimValidationOutcome, validate_claims


@dataclass
class DocumentReviewResult:
    claim_check: ClaimValidationOutcome
    ats_check: AtsValidationResult

    @property
    def ready_for_review(self) -> bool:
        return self.claim_check.passed and self.ats_check.passed


def record_validation_result(document_id: int, claim_check_passed: bool, ats_check_passed: bool) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE generated_documents "
                "SET claim_check_passed = :claim_check_passed, "
                "    ats_check_passed = :ats_check_passed "
                "WHERE id = :document_id"
            ),
            {
                "claim_check_passed": claim_check_passed,
                "ats_check_passed": ats_check_passed,
                "document_id": document_id,
            },
        )


def review_generated_document(document_id: int, document_text: str, docx_path: str,
                               evidence_path: str, required_snippets: list[str],
                               workdir: str) -> DocumentReviewResult:
    claim_check = validate_claims(document_text, evidence_path)
    ats_check = validate_ats(docx_path, document_text, required_snippets, workdir)

    record_validation_result(document_id, claim_check.passed, ats_check.passed)

    return DocumentReviewResult(claim_check=claim_check, ats_check=ats_check)
