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


class ChatSearchIntent(BaseModel):
    """Search filters extracted from a free-text chat message.

    Attributes:
        query: Job title/role/keywords to search for — "" if the message
            doesn't contain enough to search on yet.
        location: Location filter, or None if not mentioned.
        experience: Experience-level filter (e.g. "senior", "3-5 years"),
            or None if not mentioned.
        posted_within_days: Recency filter in days, or None if not mentioned.
        company: A specific company the user named, or None.
        sources: Which of the app's three search sources to run this
            query against — "explore" (broad MCP search, the default),
            "scrape" (direct multi-site JobSpy scrape — pick this when
            the user names a specific site like Indeed/Naukri/Glassdoor,
            or explicitly asks to "scrape"), "targets" (the user's
            configured company target list — pick this when `company`
            names one of the user's own tracked companies, or the
            message is about "my target companies"). Pick more than one
            when the message implies it; default to ["explore"] alone
            when nothing suggests otherwise.
        ready_to_search: True once `query` alone is usable — location,
            experience, company, and posted_within_days are optional
            narrowing filters, never required to run a search.
        clarification_question: A single short question to ask when
            `query` itself is still missing or too vague to search on;
            None once ready_to_search is true.
    """
    query: str
    location: str | None = None
    experience: str | None = None
    posted_within_days: int | None = None
    company: str | None = None
    sources: list[Literal["explore", "scrape", "targets"]] = ["explore"]
    ready_to_search: bool
    clarification_question: str | None = None


class JobSummaryItem(BaseModel):
    """One staged result's one-line AI summary.

    Attributes:
        index: Position of this job in the list that was summarized
            (0-based) — maps the summary back onto its result without
            needing a database id yet (summarization runs before staging).
        summary: A single short sentence capturing the role, level, and
            any standout requirement — not a restatement of the title.
    """
    index: int
    summary: str


class ChatResultSummaries(BaseModel):
    """Batch of one-line summaries for a set of staged search results.

    Attributes:
        summaries: One JobSummaryItem per input job, same count and order
            as the jobs that were summarized.
    """
    summaries: list[JobSummaryItem]


class GeneratedCoverLetter(BaseModel):
    """Generated cover letter tailored to a job and styled after candidate voice samples.

    Attributes:
        content: Complete body text of the cover letter.
        evidence_ids_used: List of evidence identifiers cited in the letter.
    """
    content: str
    evidence_ids_used: list[str]


class ResumeEditSuggestion(BaseModel):
    """A proposed revision to an already-generated resume, from user feedback.

    Attributes:
        sections: The full revised section list — every section, not just
            the ones feedback touched (write_resume_docx needs the whole
            set either way, and this keeps the shape identical to
            ResumeGenerationResult.sections).
        change_summary: One short sentence describing what changed and
            why, shown to the user before they accept it.
    """
    sections: list[GeneratedResumeSection]
    change_summary: str


class CoverLetterEditSuggestion(BaseModel):
    """A proposed revision to an already-generated cover letter, from user feedback.

    Attributes:
        content: The full revised cover letter body.
        change_summary: One short sentence describing what changed and why.
    """
    content: str
    change_summary: str
