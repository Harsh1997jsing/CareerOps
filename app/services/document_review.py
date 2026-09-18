"""
Runs both Phase 3 validators against a generated document and records the
outcome on its generated_documents row. This is the single place that
flips claim_check_passed / ats_check_passed, so no other code path can mark
a document ready for review without actually running both checks.

Only the DB write is async here — validate_claims()/validate_ats() (the
Anthropic call and the LibreOffice subprocess) stay synchronous; this
session's async conversion is scoped to the ORM/session layer, not every
blocking call in the codebase.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.models import GeneratedDocument
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


async def record_validation_result(
    document_id: int,
    claim_check_passed: bool,
    ats_check_passed: bool,
    session: AsyncSession | None = None,
) -> None:
    """Persist claim and ATS validation flags onto a GeneratedDocument row.

    Args:
        document_id: Primary key of the generated document record.
        claim_check_passed: Boolean indicating whether all factual claims were verified.
        ats_check_passed: Boolean indicating whether ATS checks passed.
        session: Optional async SQLAlchemy Session (defaults to a session from
            the singleton engine's session factory, committed and closed here).
    """
    owns_session = session is None
    db_session = session if session is not None else get_session_factory()()
    try:
        document = await db_session.get(GeneratedDocument, document_id)
        if document is not None:
            document.claim_check_passed = claim_check_passed
            document.ats_check_passed = ats_check_passed
            await db_session.commit()
    finally:
        if owns_session:
            await db_session.close()


async def review_generated_document(document_id: int, document_text: str, docx_path: str,
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

    await record_validation_result(document_id, claim_check.passed, ats_check.passed)

    return DocumentReviewResult(claim_check=claim_check, ats_check=ats_check)
