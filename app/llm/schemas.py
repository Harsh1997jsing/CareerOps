"""
Structured output schemas for every LLM call in the system.
Passed directly to client.messages.parse(output_format=...) so Claude's
response is guaranteed to match this shape — no manual JSON parsing.
"""

from pydantic import BaseModel, Field
from typing import Literal


class JobFitAnalysis(BaseModel):
    eligible: bool
    fit_score: int = Field(ge=0, le=100)
    confidence: Literal["high", "medium", "low"]
    strong_matches: list[str]
    missing_requirements: list[str]
    risks: list[str]
    summary: str


class ScreeningAnswer(BaseModel):
    answer: str
    evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class ClaimCheckItem(BaseModel):
    claim: str
    evidence_id: str | None
    verified: bool


class ClaimCheckResult(BaseModel):
    all_verified: bool
    items: list[ClaimCheckItem]
    blocking_claims: list[str]  # claims with no matching evidence_id


class GeneratedResumeSection(BaseModel):
    section: Literal["summary", "skills", "experience", "projects", "education"]
    content: str
    evidence_ids_used: list[str]
