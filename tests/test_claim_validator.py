from unittest.mock import patch

from app.llm.schemas import ClaimCheckItem, ClaimCheckResult, GeneratedResumeSection
from app.services.claim_validator import resume_document_text, validate_claims


def _result(all_verified: bool, blocking_claims: list[str]) -> ClaimCheckResult:
    return ClaimCheckResult(
        all_verified=all_verified,
        items=[ClaimCheckItem(claim="Built a thing", evidence_id="EXP001", verified=all_verified)],
        blocking_claims=blocking_claims,
    )


def test_validate_claims_passes_when_all_verified(tmp_path):
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")

    with patch("app.services.claim_validator.structured_call") as mock_call:
        mock_call.return_value = _result(all_verified=True, blocking_claims=[])
        outcome = validate_claims("I built things.", str(evidence_path))

    assert outcome.passed


def test_validate_claims_blocks_on_unverified_claim(tmp_path):
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")

    with patch("app.services.claim_validator.structured_call") as mock_call:
        mock_call.return_value = _result(all_verified=False, blocking_claims=["Led a team of 50"])
        outcome = validate_claims("I led a team of 50.", str(evidence_path))

    assert not outcome.passed
    assert "Led a team of 50" in outcome.result.blocking_claims


def test_validate_claims_blocks_if_blocking_claims_present_even_when_flagged_verified(tmp_path):
    # Defensive: don't trust all_verified alone if blocking_claims is non-empty.
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")

    with patch("app.services.claim_validator.structured_call") as mock_call:
        mock_call.return_value = _result(all_verified=True, blocking_claims=["Something unverified"])
        outcome = validate_claims("Some text.", str(evidence_path))

    assert not outcome.passed


def test_resume_document_text_joins_sections():
    sections = [
        GeneratedResumeSection(section="summary", content="A summary.", evidence_ids_used=["EXP001"]),
        GeneratedResumeSection(section="skills", content="Python.", evidence_ids_used=["EXP001"]),
    ]
    text = resume_document_text(sections)

    assert "SUMMARY:\nA summary." in text
    assert "SKILLS:\nPython." in text
