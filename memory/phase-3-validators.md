# Phase 3: Claim + ATS validators

## What's there

- `app/services/claim_validator.py` — `validate_claims()` reuses the
  Phase 0-1 `CLAIM_CHECK_PROMPT`/`ClaimCheckResult` to fact-check a text
  blob against `data/evidence.yaml`. Blocks if `all_verified` is false
  **or** `blocking_claims` is non-empty — checked defensively rather than
  trusting either flag alone.
- `app/services/ats_validator.py`:
  - `check_docx_structure()` — pure, no external tools. Flags tables,
    inline images, text boxes (found via raw XML — python-docx doesn't
    model text boxes at all), and multi-column sections (via the
    `w:cols/@w:num` XML attribute — python-docx has no public API for
    column count; a fresh document already has an empty `<w:cols/>`
    element by default, so column count is read/set on that existing
    element, not a second one).
  - `convert_docx_to_pdf()` shells out to LibreOffice headless (`soffice`
    on PATH); `extract_pdf_text()` uses PyMuPDF (`import pymupdf`, not the
    deprecated `import fitz`).
  - `check_text_roundtrip()` flags >10% source-word loss or a missing
    required snippet (name, email, section headings) after the DOCX → PDF
    → text round-trip.
- `app/db.py` (new) — a 10-line cached SQLAlchemy engine wrapper reading
  `DATABASE_URL`. Added here because this phase was the first thing that
  needed real DB writes.
- `app/services/document_review.py` (new, not explicitly requested but
  needed for "wire into generated_documents") — `review_generated_document()`
  runs both validators and calls `record_validation_result()`, the **only**
  code path that writes `generated_documents.claim_check_passed`/
  `ats_check_passed`. Kept separate from the validators themselves so each
  validator stays a pure/testable function and the DB write is isolated to
  one place.

## Decisions worth knowing

- LibreOffice was **not installed** in the environment this was built in
  (`soffice` not on PATH). `convert_docx_to_pdf()`/`extract_pdf_text()`
  have never actually executed against a real document — only tested via
  `pytest.mark.skipif` (currently skipping) plus a `RuntimeError` test for
  the missing-LibreOffice path. `check_docx_structure()` and
  `check_text_roundtrip()` are fully tested with fixture data since they
  don't need the external tool.
- No live Postgres was available either — `document_review.py`'s DB write
  is tested against a mocked SQLAlchemy engine/connection, asserting the
  SQL and params, never against real Postgres.

## Testing

34 tests across `test_claim_validator.py`, `test_ats_validator.py`,
`test_docx_writer.py`, `test_document_review.py` at the time this phase was
finished — see `memory/known-gaps.md` for what's still unverified against
real infrastructure.
