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
    """Outcome of verifying document claims against candidate evidence.

    Attributes:
        passed: True if every factual claim was verified and no blocking claims exist.
        result: Detailed breakdown of verified and unverified claims from Claude.
    """
    passed: bool
    result: ClaimCheckResult


def validate_claims(generated_text: str, evidence_path: str) -> ClaimValidationOutcome:
    """Fact-check every claim in generated document text against candidate evidence.

    Calls Claude to compare every statement (dates, roles, metrics, tools) against
    the evidence YAML. An unverified claim blocks the document outright (CLAUDE.md rule 3).

    Args:
        generated_text: The complete text content of the generated resume or cover letter.
        evidence_path: Path to the evidence YAML file (e.g., `data/evidence.yaml`).

    Returns:
        ClaimValidationOutcome: Result containing boolean pass flag and parsed claim details.

    Raises:
        OSError: If the evidence YAML file cannot be read.
    """
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
    """Flatten generated resume sections into a single text blob for fact-checking.

    Args:
        sections: List of generated resume sections with section names and text.

    Returns:
        str: Flattened document text with uppercase section headers separated by newlines.
    """
    return "\n\n".join(f"{section.section.upper()}:\n{section.content}" for section in sections)
