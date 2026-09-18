"""
Job read queries for the API (app/api/routes/jobs.py). Split out of the
old dashboard_data.py — which mixed jobs, applications, and documents
under a name left over from the now-deleted Streamlit dashboard — into
one module per resource, matching the route split.

Queries through app/models/'s ORM classes on an async Session.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import GeneratedDocument, Job
from app.schemas import GeneratedDocumentItem, JobDetail, JobListItem
from app.services.applications import _application_to_item

__all__ = ["list_jobs", "get_job", "list_generated_documents"]


def _job_to_list_item(job: Job) -> JobListItem:
    """Map a Job ORM instance (with `analyses` eager-loaded) onto a JobListItem.

    `job.analyses` is ordered newest-first (see app/models/job.py), so
    `[0]` is always the latest analysis without a separate query.
    """
    latest = job.analyses[0] if job.analyses else None
    return JobListItem(
        job_id=job.id,
        company=job.company,
        title=job.title,
        location=job.location or "",
        url=job.url,
        status=job.status,
        fit_score=latest.fit_score if latest else None,
        confidence=latest.confidence if latest else None,
        strong_matches=(latest.strong_matches if latest else None) or [],
        missing_skills=(latest.missing_skills if latest else None) or [],
        risks=(latest.risks if latest else None) or [],
    )


async def list_jobs(
    session: AsyncSession, status: str | None = None, limit: int = 50, offset: int = 0
) -> list[JobListItem]:
    """List jobs with their latest analysis results, optionally filtered by status.

    `limit`/`offset` bound the result set (audit finding F8 — this query
    used to be unbounded). The route clamps `limit` to 1-200; this
    function trusts its caller rather than re-validating, since the only
    caller is that route.
    """
    stmt = (
        select(Job)
        .options(selectinload(Job.analyses))
        .order_by(Job.collected_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(Job.status == status)
    jobs = (await session.scalars(stmt)).all()
    return [_job_to_list_item(job) for job in jobs]


async def get_job(session: AsyncSession, job_id: int) -> JobDetail | None:
    """Single-job detail for GET /jobs/{id} — includes `description`, which
    list_jobs() intentionally omits to keep the list query light.

    Eager-loads both `analyses` and `applications` in this one query
    rather than issuing a second round-trip for the application record —
    the old dashboard_data.get_job() called get_application_for_job()
    separately after fetching the job.
    """
    job = await session.get(
        Job, job_id, options=[selectinload(Job.analyses), selectinload(Job.applications)]
    )
    if job is None:
        return None

    latest = job.analyses[0] if job.analyses else None
    application = job.applications[0] if job.applications else None

    return JobDetail(
        job_id=job.id,
        company=job.company,
        title=job.title,
        location=job.location or "",
        url=job.url,
        description=job.description,
        status=job.status,
        fit_score=latest.fit_score if latest else None,
        confidence=latest.confidence if latest else None,
        strong_matches=(latest.strong_matches if latest else None) or [],
        missing_skills=(latest.missing_skills if latest else None) or [],
        risks=(latest.risks if latest else None) or [],
        application=_application_to_item(application) if application else None,
    )


async def list_generated_documents(session: AsyncSession, job_id: int) -> list[GeneratedDocumentItem]:
    """List all generated documents for a job, ordered by type then newest version first."""
    stmt = (
        select(GeneratedDocument)
        .where(GeneratedDocument.job_id == job_id)
        .order_by(GeneratedDocument.type, GeneratedDocument.version.desc())
    )
    docs = (await session.scalars(stmt)).all()
    return [
        GeneratedDocumentItem(
            id=doc.id,
            type=doc.type,
            file_path=doc.file_path,
            version=doc.version,
            claim_check_passed=doc.claim_check_passed,
            ats_check_passed=doc.ats_check_passed,
        )
        for doc in docs
    ]
