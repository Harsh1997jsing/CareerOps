"""Generates a tailored resume or cover letter for a job, writes it to a
.docx on disk, and runs it through document_review's claim/ATS validation
gate — the "prepare an application" step of the apply pipeline
(job_scorer's score/decide -> HERE -> document_review -> applications'
approve/open/mark-applied).

Generating a job's first document is also what starts that job's real
Application workflow: applications_service.create_application() is
get-or-create, called here rather than requiring a separate "start
application" click first (see its own docstring for why).
"""

import os
from typing import Literal

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import GeneratedDocument, Job
from app.services import applications as applications_service
from app.services import cover_letter as cover_letter_service
from app.services import document_review
from app.services import resume_generator as resume_generator_service
from app.services.ats_validator import cover_letter_required_snippets, resume_required_snippets
from app.services.claim_validator import resume_document_text
from app.services.docx_writer import write_cover_letter_docx, write_resume_docx

DocumentType = Literal["resume", "cover_letter"]


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


async def generate_document(session: AsyncSession, job: Job, doc_type: DocumentType) -> GeneratedDocument:
    """Generate, write, and validate a resume or cover letter for a job.

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
    with open(settings.profile_path) as f:
        profile = yaml.safe_load(f)

    os.makedirs(settings.documents_dir, exist_ok=True)
    version = await _next_version(session, job.id, doc_type)
    output_path = os.path.join(settings.documents_dir, f"job_{job.id}_{doc_type}_v{version}.docx")

    if doc_type == "resume":
        result = resume_generator_service.generate_resume(
            job.description, settings.skills_path, settings.evidence_path
        )
        write_resume_docx(profile, result.sections, output_path)
        document_text = resume_document_text(result.sections)
        required_snippets = resume_required_snippets(profile, result.sections)
    else:
        result = cover_letter_service.generate_cover_letter(
            job.description, settings.evidence_path, settings.profile_path, settings.voice_samples_dir
        )
        write_cover_letter_docx(profile, result.content, output_path)
        document_text = result.content
        required_snippets = cover_letter_required_snippets(profile)

    await applications_service.create_application(session, job.id)

    document = GeneratedDocument(job_id=job.id, type=doc_type, file_path=output_path, version=version)
    session.add(document)
    await session.commit()
    await session.refresh(document)

    await document_review.review_generated_document(
        document.id, document_text, output_path, settings.evidence_path, required_snippets, settings.documents_dir
    )
    await session.refresh(document)
    return document
