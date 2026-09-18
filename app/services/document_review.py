"""
Runs both Phase 3 validators against a generated document and records the
outcome on its generated_documents row. This is the single place that
flips claim_check_passed / ats_check_passed, so no other code path can mark
a document ready for review without actually running both checks.
"""

from dataclasses import dataclass

from sqlalchemy import text

from sqlalchemy.engine import Engine

from app.db import get_engine
from app.services.ats_validator import AtsValidationResult, validate_ats
from app.services.claim_validator import ClaimValidationOutcome, validate_claims


@dataclass
class DocumentReviewResult:
    """Aggregated outcome of claim verification and ATS compatibility review.

    Attributes:
        claim_check: Result of fact-checking document claims against candidate evidence.
        ats_check: Result of ATS structural format and text fidelity validation.
    """
    claim_check: ClaimValidationOutcome
    ats_check: AtsValidationResult

    @property
    def ready_for_review(self) -> bool:
        """Indicate whether the document passed both claim verification and ATS checks."""
        return self.claim_check.passed and self.ats_check.passed


def record_validation_result(
    document_id: int,
    claim_check_passed: bool,
    ats_check_passed: bool,
    engine: Engine | None = None,
) -> None:
    """Persist claim and ATS validation flags into the `generated_documents` table.

    Args:
        document_id: Primary key of the generated document record.
        claim_check_passed: Boolean indicating whether all factual claims were verified.
        ats_check_passed: Boolean indicating whether ATS checks passed.
        engine: Optional SQLAlchemy Engine dependency (defaults to singleton get_engine()).
    """
    db_engine = engine if engine is not None else get_engine()
    with db_engine.begin() as conn:
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
    """Perform full claim-checking and ATS validation, recording results to the database.

    Runs `validate_claims` to check facts against evidence and `validate_ats` to ensure
    formatting is ATS-friendly. Updates the database row for `document_id`.

    Args:
        document_id: Database ID of the generated document.
        document_text: Plain text content of the document.
        docx_path: Filesystem path to the generated DOCX file.
        evidence_path: Path to candidate evidence YAML file.
        required_snippets: Crucial text snippets required to survive PDF round-trip.
        workdir: Scratch/temporary directory for intermediate PDF conversion files.

    Returns:
        DocumentReviewResult: Combined review outcome containing claim and ATS results.
    """
    claim_check = validate_claims(document_text, evidence_path)
    ats_check = validate_ats(docx_path, document_text, required_snippets, workdir)

    record_validation_result(document_id, claim_check.passed, ats_check.passed)

    return DocumentReviewResult(claim_check=claim_check, ats_check=ats_check)
