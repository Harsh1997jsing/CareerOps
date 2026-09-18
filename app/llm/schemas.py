"""
Structured output schemas for every LLM call in the system.
Passed directly to client.messages.parse(output_format=...) so Claude's
response is guaranteed to match this shape — no manual JSON parsing.
"""

from pydantic import BaseModel, Field
from typing import Literal


class JobFitAnalysis(BaseModel):
    """Structured assessment of how well a candidate matches a job posting.

    Attributes:
        eligible: Whether candidate satisfies the baseline job requirements.
        fit_score: Numerical score (0-100) reflecting depth and relevance of match.
        confidence: Model confidence in this assessment ("high", "medium", or "low").
        strong_matches: Skills and qualifications explicitly backed by candidate evidence.
        missing_requirements: Requirements from the job description lacking candidate evidence.
        risks: Potential red flags, ambiguities, or experience discrepancies identified.
        summary: High-level qualitative summary of fit and application recommendation.
    """
    eligible: bool
    fit_score: int = Field(ge=0, le=100)
    confidence: Literal["high", "medium", "low"]
    strong_matches: list[str]
    missing_requirements: list[str]
    risks: list[str]
    summary: str


class ScreeningAnswer(BaseModel):
    """Answer generated for an employer screening question grounded in candidate evidence.

    Attributes:
        answer: Drafted response to the screening question.
        evidence_ids: List of evidence IDs from data/evidence.yaml supporting the answer.
        confidence: Confidence level of the answer ("high", "medium", or "low").
    """
    answer: str
    evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class ClaimCheckItem(BaseModel):
    """Verification outcome for an individual factual claim in generated text.

    Attributes:
        claim: The extracted factual statement or bullet claim.
        evidence_id: Matching ID from candidate evidence, or None if unsupported.
        verified: True if the claim is directly supported by candidate evidence.
    """
    claim: str
    evidence_id: str | None
    verified: bool


class ClaimCheckResult(BaseModel):
    """Overall verification results of a generated document against candidate evidence.

    Attributes:
        all_verified: True only if every factual claim was successfully verified.
        items: Detailed breakdown of each extracted claim and verification status.
        blocking_claims: List of claims with no matching evidence ID that block document approval.
    """
    all_verified: bool
    items: list[ClaimCheckItem]
    blocking_claims: list[str]  # claims with no matching evidence_id


class GeneratedResumeSection(BaseModel):
    """Generated section content for a tailored resume.

    Attributes:
        section: Section name ("summary", "skills", "experience", "projects", or "education").
        content: Section text formatted with paragraphs and bullet points.
        evidence_ids_used: Evidence identifiers referenced to construct this section.
    """
    section: Literal["summary", "skills", "experience", "projects", "education"]
    content: str
    evidence_ids_used: list[str]


class GeneratedCoverLetter(BaseModel):
    """Generated cover letter tailored to a job and styled after candidate voice samples.

    Attributes:
        content: Complete body text of the cover letter.
        evidence_ids_used: List of evidence identifiers cited in the letter.
    """
    content: str
    evidence_ids_used: list[str]
