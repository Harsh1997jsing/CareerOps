"""
Checks every factual claim in a generated document against
data/evidence.yaml. An unverified claim blocks the document outright — it
never gets softened, reworded around, or waved through.
"""

from dataclasses import dataclass

from app.llm.anthropic_client import structured_call
from app.llm.prompts import CLAIM_CHECK_PROMPT
from app.llm.schemas import ClaimCheckResult, GeneratedResumeSection


@dataclass
class ClaimValidationOutcome:
    passed: bool
    result: ClaimCheckResult


def validate_claims(generated_text: str, evidence_path: str) -> ClaimValidationOutcome:
    with open(evidence_path) as f:
        evidence_yaml = f.read()

    prompt = CLAIM_CHECK_PROMPT.format(
        generated_text=generated_text,
        evidence_yaml=evidence_yaml,
    )
    result = structured_call(prompt, ClaimCheckResult, max_tokens=2048)

    passed = result.all_verified and len(result.blocking_claims) == 0
    return ClaimValidationOutcome(passed=passed, result=result)


def resume_document_text(sections: list[GeneratedResumeSection]) -> str:
    """Flattens generated resume sections into one text blob to fact-check."""
    return "\n\n".join(f"{section.section.upper()}:\n{section.content}" for section in sections)
