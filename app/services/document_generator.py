"""Generates a tailored resume or cover letter for a job, writes it to a
.docx on disk, and runs it through document_review's claim/ATS validation
gate — the "prepare an application" step of the apply pipeline
(job_scorer's score/decide -> HERE -> document_review -> applications'
approve/open/mark-applied).

Generating a job's first document is also what starts that job's real
Application workflow: applications_service.create_application() is
get-or-create, called here rather than requiring a separate "start
application" click first (see its own docstring for why).

`persist_document()` below is the shared "write .docx, create the row,
validate" tail — app/services/document_editor.py's apply_*_edit()
functions call it too, so an accepted edit goes through the exact same
write/validate path a from-scratch generation does, just with
already-decided content instead of a fresh Claude call.
"""

import asyncio
import json
import os
from typing import Literal

import yaml
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.llm.schemas import GeneratedResumeSection
from app.models import GeneratedDocument, Job
from app.services import applications as applications_service
from app.services import cover_letter as cover_letter_service
from app.services import document_review
from app.services import resume_generator as resume_generator_service
from app.services.ats_validator import cover_letter_required_snippets, resume_required_snippets
from app.services.claim_validator import resume_document_text
from app.services.docx_writer import write_cover_letter_docx, write_resume_docx

DocumentType = Literal["resume", "cover_letter"]

# A concurrent persist_document() for the same (job, type) racing on
# _next_version() gets at most this many attempts to recompute a fresh
# version number and retry, after uq_generated_documents_job_type_version
# rejects the collision — see persist_document()'s docstring.
_MAX_VERSION_ATTEMPTS = 3


async def _next_version(session: AsyncSession, job_id: int, doc_type: str) -> int:
    """Compute the next version number for a job's documents of one type.

    Args:
        session: Database session.
        job_id: Job the document belongs to.
        doc_type: "resume" or "cover_letter".

    Returns:
        int: 1 for this job's first document of this type, incrementing
            from there — matches GeneratedDocument.version's role as a
            per-(job, type) counter, not a global one.
    """
    count = await session.scalar(
        select(func.count())
        .select_from(GeneratedDocument)
        .where(GeneratedDocument.job_id == job_id, GeneratedDocument.type == doc_type)
    )
    return (count or 0) + 1


def load_document_content(document: GeneratedDocument) -> list[GeneratedResumeSection] | str:
    """Read a GeneratedDocument's current content back from its content_json.

    Args:
        document: A persisted GeneratedDocument row (from generate_document()
            or apply_*_edit(), both of which always set content_json).

    Returns:
        list[GeneratedResumeSection] for a "resume" document, str for a
        "cover_letter" one — matches persist_document()'s `sections`/
        `content` parameters, so the result can be fed straight into a
        suggest-edit call.

    Raises:
        ValueError: If content_json is empty — a document from before
            this column existed, or one that failed before persisting it.
    """
    if not document.content_json:
        raise ValueError(f"document {document.id} has no stored content to edit")
    parsed = json.loads(document.content_json)
    if document.type == "resume":
        return [GeneratedResumeSection(**item) for item in parsed]
    return parsed


def load_profile(profile_path: str) -> dict:
    """Load the candidate profile YAML every .docx write needs.

    Args:
        profile_path: Path to profile YAML (settings.profile_path).

    Returns:
        dict: Parsed profile.
    """
    with open(profile_path) as f:
        return yaml.safe_load(f)


async def persist_document(
    session: AsyncSession,
    job: Job,
    doc_type: DocumentType,
    profile: dict,
    sections: list[GeneratedResumeSection] | None = None,
    content: str | None = None,
) -> GeneratedDocument:
    """Write a resume/cover letter's already-decided content to .docx and validate it.

    Shared by generate_document() (fresh content from a Claude call) and
    document_editor.py's apply_*_edit() (already-accepted content from a
    suggest-edit round trip) — same version bump, same get-or-create
    Application, same claim/ATS validation gate either way. Exactly one
    of `sections` (resume) / `content` (cover letter) must be given,
    matching `doc_type`.

    `uq_generated_documents_job_type_version` (job_id, type, version)
    means two concurrent calls for the same job/type that both compute
    the same next version from `_next_version()` can't both insert — the
    loser's `commit()` raises `IntegrityError`, caught below, and retries
    with a freshly recomputed (now-higher) version and a correspondingly
    different `output_path`, so it never silently clobbers the winner's
    file on disk with new content under the same name. Bounded by
    `_MAX_VERSION_ATTEMPTS` rather than retried forever.

    Args:
        session: Database session.
        job: Already-loaded Job ORM row.
        doc_type: "resume" or "cover_letter".
        profile: Parsed candidate profile (see load_profile()).
        sections: Full resume section list, required when doc_type == "resume".
        content: Full cover letter text, required when doc_type == "cover_letter".

    Returns:
        GeneratedDocument: The persisted row, with claim_check_passed and
            ats_check_passed already set by document_review.

    Raises:
        IntegrityError: If every retry in `_MAX_VERSION_ATTEMPTS` still
            collides — pathological, not expected in real traffic.
    """
    settings = get_settings()
    os.makedirs(settings.documents_dir, exist_ok=True)
    # Captured once, up front: a retry's rollback() (below) expires every
    # object in the session's identity map, not just the failed insert —
    # re-touching `job.id` after that inside the loop would attempt a
    # sync lazy-refresh outside the async greenlet context and crash.
    job_id = job.id

    await applications_service.create_application(session, job_id)

    for attempt in range(_MAX_VERSION_ATTEMPTS):
        version = await _next_version(session, job_id, doc_type)
        output_path = os.path.join(settings.documents_dir, f"job_{job_id}_{doc_type}_v{version}.docx")

        if doc_type == "resume":
            assert sections is not None
            write_resume_docx(profile, sections, output_path)
            document_text = resume_document_text(sections)
            required_snippets = resume_required_snippets(profile, sections)
            content_json = json.dumps([s.model_dump() for s in sections])
        else:
            assert content is not None
            write_cover_letter_docx(profile, content, output_path)
            document_text = content
            required_snippets = cover_letter_required_snippets(profile)
            content_json = json.dumps(content)

        document = GeneratedDocument(
            job_id=job_id, type=doc_type, file_path=output_path, version=version, content_json=content_json
        )
        session.add(document)
        try:
            await session.commit()
            break
        except IntegrityError:
            # rollback() already detaches `document` (the failed pending
            # insert) from the session on its own — an explicit
            # session.expunge(document) here raises InvalidRequestError
            # ("not present in this Session") since it's already gone.
            await session.rollback()
            if attempt == _MAX_VERSION_ATTEMPTS - 1:
                raise
    await session.refresh(document)

    # review_generated_document() is itself async, but its own docstring
    # is explicit that only its DB write is truly non-blocking — the
    # Anthropic call (validate_claims) and the LibreOffice subprocess
    # (validate_ats) inside it still run synchronously on this thread.
    # That's an existing, documented scope boundary (see that module's
    # docstring), not something introduced here. Passing `session` through
    # (rather than letting it default to a second, separate session) keeps
    # this whole persist-and-validate sequence on one connection/transaction.
    await document_review.review_generated_document(
        document.id, document_text, output_path, settings.evidence_path, required_snippets, settings.documents_dir,
        session=session,
    )
    await session.refresh(document)
    return document


async def generate_document(session: AsyncSession, job: Job, doc_type: DocumentType) -> GeneratedDocument:
    """Generate, write, and validate a resume or cover letter for a job from scratch.

    Args:
        session: Database session.
        job: Already-loaded Job ORM row (its `description` is what the
            document is tailored against).
        doc_type: "resume" or "cover_letter".

    Returns:
        GeneratedDocument: The persisted row, with claim_check_passed and
            ats_check_passed already set by document_review.

    Raises:
        OSError: If a candidate data file (skills/evidence/profile YAML)
            can't be read.
    """
    settings = get_settings()
    profile = load_profile(settings.profile_path)

    if doc_type == "resume":
        result = await asyncio.to_thread(
            resume_generator_service.generate_resume, job.description, settings.skills_path, settings.evidence_path
        )
        return await persist_document(session, job, doc_type, profile, sections=result.sections)

    result = await asyncio.to_thread(
        cover_letter_service.generate_cover_letter,
        job.description, settings.evidence_path, settings.profile_path, settings.voice_samples_dir,
    )
    return await persist_document(session, job, doc_type, profile, content=result.content)
