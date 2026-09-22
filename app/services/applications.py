"""
Application read/write queries for the API (app/api/routes/applications.py).
Split out of the old dashboard_data.py — see app/services/jobs.py's
docstring for why.

Queries through app/models/'s ORM classes on an async Session.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Application, CompanyApplicationHistory
from app.schemas import ApplicationContext, ApplicationItem, FilterResult
from app.services.hard_filters import check_company_cooldown

APPROVED_STATUS = "APPROVED"
REJECTED_STATUS = "REJECTED"

__all__ = [
    "APPROVED_STATUS",
    "REJECTED_STATUS",
    "get_application",
    "get_application_for_job",
    "create_application",
    "get_application_context",
    "get_company_applied_dates",
    "check_cooldown_for_company",
    "set_status",
    "set_application_status",
]


def _application_to_item(application: Application) -> ApplicationItem:
    return ApplicationItem(
        application_id=application.id,
        job_id=application.job_id,
        status=application.status,
        applied_at=application.applied_at,
    )


async def get_application(session: AsyncSession, application_id: int) -> Application | None:
    """Loads the Application ORM row with its Job eager-loaded, for callers
    that need to both read context (job url/company) and mutate the row
    itself in the same request. Keep the returned object alive (don't let
    it go out of scope) and reuse it — SQLAlchemy's identity map holds only
    weak references, so once this object is garbage-collected a later
    `session.get(Application, id)` re-queries instead of reusing it.
    That's exactly what get_application_context() below used to cause when
    called right before approve/reject/mark-applied (audit finding F4,
    confirmed via query instrumentation: 4 SQL statements where 2-3 suffice).
    Routes should call this once and pass the object on, not call
    get_application_context() and then a second by-id lookup.
    """
    return await session.get(Application, application_id, options=[selectinload(Application.job)])


async def get_application_for_job(session: AsyncSession, job_id: int) -> ApplicationItem | None:
    """Retrieve the application record linked to a given job, if one exists."""
    application = (await session.scalars(select(Application).where(Application.job_id == job_id))).first()
    if application is None:
        return None
    return _application_to_item(application)


async def create_application(session: AsyncSession, job_id: int) -> Application:
    """Get-or-create the Application row for a job.

    Until app/services/document_generator.py started calling this, no
    code path ever created an Application row at all (see
    app/services/jobs.py's REJECTED_JOB_STATUS docstring) — Dashboard
    reject/restore mutated Job.status directly instead, as a documented
    stand-in for the real workflow. Generating a job's first document is
    what starts that real workflow now, rather than a separate explicit
    "start application" action — nothing else needs to happen first.
    Idempotent: a job has at most one Application (get_application_for_job()
    already assumes this via `.first()`), so a second document for the
    same job reuses the existing row instead of creating a duplicate.

    A `uq_applications_job_id` unique constraint (added by a later
    migration than this docstring's original claim of no DB-level
    backing) makes that idempotency real under concurrency too: two
    requests racing past the `existing is None` check together will both
    try to insert, but only one commit can win — the loser catches
    `IntegrityError` here and re-queries for the row the winner just
    created, rather than 500ing or creating a second row for one job.

    Args:
        session: Database session.
        job_id: Job to create or find the application for.

    Returns:
        Application: The existing or newly created row, in its default
            READY_FOR_REVIEW status if newly created.
    """
    existing = (await session.scalars(select(Application).where(Application.job_id == job_id))).first()
    if existing is not None:
        return existing
    application = Application(job_id=job_id)
    session.add(application)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (await session.scalars(select(Application).where(Application.job_id == job_id))).first()
        if existing is not None:
            return existing
        raise
    await session.refresh(application)
    return application


async def get_application_context(session: AsyncSession, application_id: int) -> ApplicationContext | None:
    """
    Looks up the job (company, url) behind an application_id — approve()/
    reject() only need the id itself, but open()/mark-applied() need the
    job's url/company too, and the API is keyed by application_id (unlike
    get_application_for_job(), which is keyed by job_id).
    """
    application = await session.get(Application, application_id, options=[selectinload(Application.job)])
    if application is None:
        return None

    return ApplicationContext(
        application_id=application.id,
        job_id=application.job_id,
        company=application.job.company,
        url=application.job.url,
    )


async def get_company_applied_dates(session: AsyncSession, company: str) -> list[datetime]:
    """Retrieve historical application submission dates for a given company."""
    stmt = select(CompanyApplicationHistory.applied_at).where(
        CompanyApplicationHistory.company == company,
        CompanyApplicationHistory.applied_at.is_not(None),
    )
    return list((await session.scalars(stmt)).all())


async def check_cooldown_for_company(session: AsyncSession, company: str, cooldown_days: int) -> FilterResult:
    """Reuses hard_filters.check_company_cooldown so a dashboard/frontend cooldown
    warning and the pre-scoring hard filter can never disagree about what's in cooldown."""
    applied_dates = await get_company_applied_dates(session, company)
    return check_company_cooldown(company, applied_dates, cooldown_days)


async def set_status(session: AsyncSession, application: Application, status: str) -> None:
    """Mutate and commit an already-loaded Application object directly — no
    query. Routes that already called get_application() should use this,
    not set_application_status() (which re-fetches by id)."""
    application.status = status
    await session.commit()


async def set_application_status(session: AsyncSession, application_id: int, status: str) -> None:
    """Update the status of an application by id, if it exists. Standalone
    convenience for callers that don't already have the ORM object loaded
    (a script, a REPL) — prefer set_status() when you already have one,
    to avoid a redundant fetch (audit finding F4)."""
    application = await session.get(Application, application_id)
    if application is not None:
        await set_status(session, application, status)
