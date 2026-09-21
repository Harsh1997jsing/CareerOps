"""Suggest-then-confirm editing for an already-generated resume or cover letter.

Two-step, matching the human-approval philosophy the rest of this app
uses (CLAUDE.md rule 1): suggest_*_edit() makes one Claude call and
writes nothing — it's pure preview. Only when the caller sends the exact
previewed content back to apply_*_edit() does anything get written,
through document_generator.persist_document() (the same write/validate
path a from-scratch generation uses). No second Claude call happens in
apply — what was previewed is exactly what gets saved, not a re-roll.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.anthropic_client import structured_call
from app.llm.prompts import COVER_LETTER_EDIT_PROMPT, RESUME_EDIT_PROMPT
from app.llm.schemas import CoverLetterEditSuggestion, GeneratedResumeSection, ResumeEditSuggestion
from app.models import GeneratedDocument, Job
from app.services.document_generator import load_profile, persist_document


def suggest_resume_edit(
    job_description: str,
    current_sections: list[GeneratedResumeSection],
    feedback: str,
    evidence_path: str,
) -> ResumeEditSuggestion:
    """Propose a revised resume section list from user feedback — read-only.

    Args:
        job_description: The job's full description (same grounding the
            original generation used).
        current_sections: The document's current section list.
        feedback: The user's free-text edit request.
        evidence_path: Path to candidate evidence YAML — the only source
            of truth the revision is allowed to draw new claims from.

    Returns:
        ResumeEditSuggestion: Proposed full section list plus a one-sentence
            summary of what changed.
    """
    with open(evidence_path) as f:
        evidence_yaml = f.read()

    current_sections_text = "\n\n".join(
        f"{section.section.upper()}:\n{section.content}" for section in current_sections
    )
    prompt = RESUME_EDIT_PROMPT.format(
        job_description=job_description,
        evidence_yaml=evidence_yaml,
        current_sections=current_sections_text,
        feedback=feedback,
    )
    return structured_call(prompt, ResumeEditSuggestion)  # type: ignore[return-value]


def suggest_cover_letter_edit(
    job_description: str, current_content: str, feedback: str, evidence_path: str
) -> CoverLetterEditSuggestion:
    """Propose a revised cover letter from user feedback — read-only.

    Args:
        job_description: The job's full description.
        current_content: The document's current full text.
        feedback: The user's free-text edit request.
        evidence_path: Path to candidate evidence YAML.

    Returns:
        CoverLetterEditSuggestion: Proposed full text plus a one-sentence
            summary of what changed.
    """
    with open(evidence_path) as f:
        evidence_yaml = f.read()

    prompt = COVER_LETTER_EDIT_PROMPT.format(
        job_description=job_description,
        evidence_yaml=evidence_yaml,
        current_content=current_content,
        feedback=feedback,
    )
    return structured_call(prompt, CoverLetterEditSuggestion)  # type: ignore[return-value]


async def apply_resume_edit(
    session: AsyncSession, job: Job, sections: list[GeneratedResumeSection], profile_path: str
) -> GeneratedDocument:
    """Persist an accepted resume edit as a new version — no Claude call.

    Args:
        session: Database session.
        job: Already-loaded Job ORM row the document belongs to.
        sections: The exact section list the user accepted (as returned
            by suggest_resume_edit(), unmodified — not re-generated).
        profile_path: Path to candidate profile YAML (settings.profile_path).

    Returns:
        GeneratedDocument: The newly persisted version, validated the same
            way a from-scratch generation is.
    """
    profile = load_profile(profile_path)
    return await persist_document(session, job, "resume", profile, sections=sections)


async def apply_cover_letter_edit(
    session: AsyncSession, job: Job, content: str, profile_path: str
) -> GeneratedDocument:
    """Persist an accepted cover letter edit as a new version — no Claude call.

    Args:
        session: Database session.
        job: Already-loaded Job ORM row the document belongs to.
        content: The exact text the user accepted (as returned by
            suggest_cover_letter_edit(), unmodified).
        profile_path: Path to candidate profile YAML.

    Returns:
        GeneratedDocument: The newly persisted version, validated the same
            way a from-scratch generation is.
    """
    profile = load_profile(profile_path)
    return await persist_document(session, job, "cover_letter", profile, content=content)
