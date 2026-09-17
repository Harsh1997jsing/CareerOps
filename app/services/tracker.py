"""
Marks an application as actually submitted — but only after you, the
human, explicitly confirm you clicked submit yourself in your own browser.
Nothing in this module, or anywhere else in this codebase, fills in or
submits an application on any external site.
"""

import webbrowser
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

APPLIED_STATUS = "APPLIED"


class ApplicationNotConfirmedError(RuntimeError):
    """Raised when mark_applied() is called without explicit human confirmation."""


def open_job_url(url: str) -> None:
    """Opens the job posting in your default browser so you can apply yourself."""
    webbrowser.open(url)


def mark_applied(engine: Engine, application_id: int, job_id: int, company: str,
                  confirmed: bool, applied_at: datetime | None = None) -> None:
    """
    Records that an application was submitted: sets applications.status to
    APPLIED and upserts company_application_history in one transaction, so
    the cooldown tracker is never out of sync with an application's status.

    `confirmed` has no default — the caller must pass True explicitly, and
    only after the human has actually clicked submit themselves. Anything
    else raises rather than silently proceeding.
    """
    if not confirmed:
        raise ApplicationNotConfirmedError(
            "Refusing to mark this APPLIED without explicit confirmation. Pass "
            "confirmed=True only after you've manually submitted this application "
            "yourself, in your own browser."
        )

    applied_at = applied_at or datetime.now()

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE applications SET status = :status, applied_at = :applied_at "
                "WHERE id = :application_id"
            ),
            {"status": APPLIED_STATUS, "applied_at": applied_at, "application_id": application_id},
        )
        conn.execute(
            text(
                "INSERT INTO company_application_history (company, job_id, applied_at) "
                "VALUES (:company, :job_id, :applied_at) "
                "ON CONFLICT (company, job_id) DO UPDATE SET applied_at = EXCLUDED.applied_at"
            ),
            {"company": company, "job_id": job_id, "applied_at": applied_at},
        )
