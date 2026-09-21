"""
Job read queries for the API (app/api/routes/jobs.py). Split out of the
old dashboard_data.py — which mixed jobs, applications, and documents
under a name left over from the now-deleted Streamlit dashboard — into
one module per resource, matching the route split.

Queries through app/models/'s ORM classes on an async Session.
"""

from datetime import datetime, timedelta, timezone

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm.schemas import JobFitAnalysis
from app.models import GeneratedDocument, Job, JobAnalysis
from app.schemas import FilterResult, GeneratedDocumentItem, JobDetail, JobListItem
from app.services.applications import _application_to_item
from app.services.hard_filters import check_hard_filters

# Job.status values a job can be set to directly from the Dashboard, kept
# entirely separate from Application.status (APPROVED/REJECTED/APPLIED/
# READY_FOR_REVIEW — see app/services/applications.py). Originally this
# was the *only* status mechanism at all — no scoring pipeline wrote
# Job.status and no code path ever created an Application row (see
# app/services/document_generator.py, which now does both: job_scorer's
# decide() writes Job.status via record_analysis()+set_job_status(), and
# generating a job's first document get-or-creates its Application via
# applications_service.create_application()). REJECTED/DISCOVERED here
# remain a distinct, honest mechanism for hiding/unhiding a job on the
# Dashboard before it's ever gone through scoring or document generation.
REJECTED_JOB_STATUS = "REJECTED"
DEFAULT_JOB_STATUS = "DISCOVERED"

__all__ = [
    "list_jobs",
    "get_job",
    "list_generated_documents",
    "get_job_by_id",
    "set_job_status",
    "hard_filter_job",
    "record_analysis",
    "REJECTED_JOB_STATUS",
    "DEFAULT_JOB_STATUS",
]


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
        # Same fallback as the posted_within_days filter below: show the
        # employer's actual posting date when known, otherwise when this
        # app collected it — never leave the Dashboard with no date at all.
        posted_at=job.posted_at or job.collected_at,
        fit_score=latest.fit_score if latest else None,
        confidence=latest.confidence if latest else None,
        strong_matches=(latest.strong_matches if latest else None) or [],
        missing_skills=(latest.missing_skills if latest else None) or [],
        risks=(latest.risks if latest else None) or [],
    )


async def list_jobs(
    session: AsyncSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    posted_within_days: int | None = None,
) -> list[JobListItem]:
    """List jobs with their latest analysis results, optionally filtered.

    `limit`/`offset` bound the result set (audit finding F8 — this query
    used to be unbounded). The route clamps `limit` to 1-200; this
    function trusts its caller rather than re-validating, since the only
    caller is that route.

    Args:
        q: Case-insensitive substring match against the job description —
            works identically on Postgres and the SQLite test DB
            (`.ilike()` compiles to `lower(x) LIKE lower(y)` where the
            dialect has no native ILIKE).
        posted_within_days: Keeps only jobs posted/collected within this
            many days. Many sources never populate `posted_at` (only
            HasData/jobspy currently do, and only sometimes) — falls back
            to `collected_at` (always set, server-side, at insert time)
            for a job with no known posting date, rather than dropping it
            just because the *employer's* posting date is unknown.
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
    if q:
        stmt = stmt.where(Job.description.ilike(f"%{q}%"))
    if posted_within_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=posted_within_days)
        stmt = stmt.where(func.coalesce(Job.posted_at, Job.collected_at) >= cutoff.replace(tzinfo=None))
    jobs = (await session.scalars(stmt)).all()
    return [_job_to_list_item(job) for job in jobs]


async def get_job_by_id(session: AsyncSession, job_id: int) -> Job | None:
    """Fetch the Job ORM row by id, for a route that needs to mutate it
    directly (reject/restore) rather than read its mapped JobDetail shape."""
    return await session.get(Job, job_id)


async def set_job_status(session: AsyncSession, job: Job, status: str) -> None:
    """Mutate and commit an already-loaded Job's status directly.

    See REJECTED_JOB_STATUS's module-level comment for why this bypasses
    the Application entity entirely rather than reusing
    applications_service.set_status().
    """
    job.status = status
    await session.commit()


def hard_filter_job(job: Job, constraints_path: str) -> FilterResult:
    """Run the deterministic, non-LLM checks a job must pass before scoring.

    CLAUDE.md's pipeline order is explicit that "only jobs that pass these
    should ever reach the scorer" — a job outside allowed_locations, an
    excluded employment_type, or matching an exclude_keyword shouldn't
    cost an LLM call to reject. `years_required` isn't a Job column
    (nothing populates it at ingestion today), so that one check in
    hard_filters.check_hard_filters() never fires here; every other check
    does.

    Args:
        job: Already-loaded Job ORM row.
        constraints_path: Path to constraints YAML (allowed_locations,
            employment_types, minimum_experience_years,
            acceptable_experience_gap_years, exclude_keywords).

    Returns:
        FilterResult: Whether the job passes, and why not if it doesn't.
    """
    with open(constraints_path) as f:
        constraints = yaml.safe_load(f)
    job_dict = {
        "location": job.location,
        "employment_type": job.employment_type,
        "description": job.description,
    }
    return check_hard_filters(job_dict, constraints)


async def record_analysis(session: AsyncSession, job: Job, analysis: JobFitAnalysis) -> JobAnalysis:
    """Persist a job_scorer.score_job() result as a new JobAnalysis row.

    Additive, not a replace — list_jobs()/get_job() already read only the
    newest row via `job.analyses[0]` (ordered newest-first, see
    app/models/job.py), so re-analyzing a job keeps its scoring history
    rather than destroying it.

    Args:
        session: Database session.
        job: Already-loaded Job ORM row.
        analysis: Structured fit analysis from job_scorer.score_job().

    Returns:
        JobAnalysis: The newly created analysis row.
    """
    row = JobAnalysis(
        job_id=job.id,
        fit_score=analysis.fit_score,
        confidence=analysis.confidence,
        eligible=analysis.eligible,
        strong_matches=analysis.strong_matches,
        # JobFitAnalysis calls this "missing_requirements"; JobAnalysis's
        # own column (and JobListItem/JobDetail's field) is "missing_skills"
        # — same data, different name at the LLM-output layer vs. the DB/API layer.
        missing_skills=analysis.missing_requirements,
        risks=analysis.risks,
    )
    session.add(row)
    await session.commit()
    return row


async def get_job(session: AsyncSession, job_id: int) -> JobDetail | None:
    """Single-job detail for GET /jobs/{id} — includes `description`, which
    list_jobs() intentionally omits to keep the list query light.

    Eager-loads both `analyses` and `applications` in this one query
    rather than issuing a second round-trip for the application record —
    the old dashboard_data.get_job() called get_application_for_job()
    separately after fetching the job.

    Uses `select()`, not `session.get()`, deliberately: `session.get()`
    returns an already-identity-mapped object straight from the session
    without emitting SQL at all when it's already present and not
    expired — silently skipping the `options=` eager loads on this call
    and leaving `analyses`/`applications` unloaded (confirmed live: a
    caller that loads a bare Job first, e.g. /jobs/{id}/analyze's
    get_job_by_id() before mutating it, then hit a MissingGreenlet crash
    right here on the implicit lazy-load `select()` triggers instead).
    `select()` always executes and applies eager-load options, refreshing
    the cached object's relationships even when it was already tracked.
    """
    job = await session.scalar(
        select(Job)
        .options(selectinload(Job.analyses), selectinload(Job.applications))
        .where(Job.id == job_id)
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
