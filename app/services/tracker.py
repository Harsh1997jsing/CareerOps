"""
Marks an application as actually submitted — but only after you, the
human, explicitly confirm you clicked submit yourself in your own browser.
Nothing in this module, or anywhere else in this codebase, fills in or
submits an application on any external site.
"""

import webbrowser
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationNotConfirmedError
from app.models import Application, CompanyApplicationHistory

APPLIED_STATUS = "APPLIED"


def open_job_url(url: str) -> None:
    """Open the job posting in the user's default browser for manual review and submission.

    Strictly obeys CLAUDE.md rule 1 by only opening the posting in a browser tab.
    Does not automate form-filling or submission.

    Args:
        url: External application or posting URL.
    """
    webbrowser.open(url)


async def mark_applied(session: AsyncSession, application_id: int, job_id: int, company: str,
                        confirmed: bool, applied_at: datetime | None = None,
                        application: Application | None = None) -> None:
    """Record that an application was manually submitted by the human user.

    Sets applications.status to APPLIED and upserts company_application_history
    in one transaction, so the cooldown tracker is never out of sync with an
    application's status. The upsert is a portable check-then-write (not a
    dialect-specific ON CONFLICT) — fine for this single-local-user tool with
    no concurrent writers; would need a real atomic upsert if that ever changes.

    `confirmed` has no default — the caller must pass True explicitly, and
    only after the human has actually clicked submit themselves. Anything
    else raises rather than silently proceeding (CLAUDE.md rule 5).

    Args:
        session: Database session.
        application_id: Application primary key.
        job_id: Corresponding job primary key.
        company: Company name for cooldown logging.
        confirmed: Mandatory explicit confirmation that human submitted the application.
        applied_at: Optional submission timestamp (defaults to current time).
        application: Optional already-loaded Application row — pass this
            when the caller already fetched it (e.g. the API route, via
            applications_service.get_application()) to avoid re-querying by
            id (audit finding F4). Callers that only have the id can omit
            this; it's fetched here in that case.

    Raises:
        ApplicationNotConfirmedError: If `confirmed` is False.
    """
    if not confirmed:
        raise ApplicationNotConfirmedError(
            "Refusing to mark this APPLIED without explicit confirmation. Pass "
            "confirmed=True only after you've manually submitted this application "
            "yourself, in your own browser."
        )

    applied_at = applied_at or datetime.now()

    if application is None:
        application = await session.get(Application, application_id)
    if application is not None:
        application.status = APPLIED_STATUS
        application.applied_at = applied_at

    history = (
        await session.scalars(
            select(CompanyApplicationHistory).where(
                CompanyApplicationHistory.company == company,
                CompanyApplicationHistory.job_id == job_id,
            )
        )
    ).first()
    if history is None:
        session.add(CompanyApplicationHistory(company=company, job_id=job_id, applied_at=applied_at))
    else:
        history.applied_at = applied_at

    await session.commit()
