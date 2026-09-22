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

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.models import GeneratedDocument
from app.services.ats_validator import AtsValidationResult, validate_ats
from app.services.claim_validator import ClaimValidationOutcome, validate_claims

logger = logging.getLogger(__name__)


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
    ats_check_passed: bool | None,
    session: AsyncSession | None = None,
) -> None:
    """Persist claim and ATS validation flags onto a GeneratedDocument row.

    Args:
        document_id: Primary key of the generated document record.
        claim_check_passed: Boolean indicating whether all factual claims were verified.
        ats_check_passed: Whether ATS checks passed — None means the check
            itself didn't run (e.g. LibreOffice missing, see
            review_generated_document()), distinct from a real pass/fail.
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
                                     workdir: str, session: AsyncSession | None = None) -> DocumentReviewResult:
    """Perform full claim-checking and ATS validation, recording results to the database.

    Runs `validate_claims` to check facts against evidence and `validate_ats` to ensure
    formatting is ATS-friendly. Updates the database row for `document_id`.

    `validate_ats()` raises `RuntimeError` when LibreOffice isn't installed
    (see ats_validator.convert_docx_to_pdf()) — caught here rather than
    left to propagate, so a missing local dependency doesn't fail the
    whole document-generation request even though the .docx/
    GeneratedDocument/Application rows are already committed by the time
    this runs. Recorded as `ats_check_passed = None` ("didn't run"), never
    silently recorded as a false pass or a false fail.

    Args:
        document_id: Database ID of the generated document.
        document_text: Plain text content of the document.
        docx_path: Filesystem path to the generated DOCX file.
        evidence_path: Path to candidate evidence YAML file.
        required_snippets: Crucial text snippets required to survive PDF round-trip.
        workdir: Scratch/temporary directory for intermediate PDF conversion files.
        session: Optional async SQLAlchemy session — pass the caller's own
            request-scoped session (as document_generator.py's
            persist_document() does) rather than defaulting to a second,
            separate one via record_validation_result()'s own fallback.

    Returns:
        DocumentReviewResult: Combined review outcome containing claim and ATS results.
    """
    claim_check = validate_claims(document_text, evidence_path)

    try:
        ats_check = validate_ats(docx_path, document_text, required_snippets, workdir)
        ats_check_passed: bool | None = ats_check.passed
    except RuntimeError as exc:
        logger.warning("ATS validation could not run for document %s: %s", document_id, exc)
        ats_check = AtsValidationResult(passed=False, reasons=[f"ATS check did not run: {exc}"])
        ats_check_passed = None

    await record_validation_result(document_id, claim_check.passed, ats_check_passed, session=session)

    return DocumentReviewResult(claim_check=claim_check, ats_check=ats_check)
