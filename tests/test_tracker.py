from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models import Application, CompanyApplicationHistory, Job
from app.services.tracker import (
    APPLIED_STATUS,
    ApplicationNotConfirmedError,
    mark_applied,
    open_job_url,
)


def test_open_job_url_calls_webbrowser_open():
    with patch("app.services.tracker.webbrowser.open") as mock_open:
        open_job_url("https://example.com/job/1")

    mock_open.assert_called_once_with("https://example.com/job/1")


async def _make_job_and_application(session, job_id=2, application_id=1):
    job = Job(
        id=job_id, source="greenhouse", company="Acme", title="Engineer",
        url="https://example.com", description="desc", status="READY_FOR_REVIEW",
    )
    application = Application(id=application_id, job_id=job_id, status="READY_FOR_REVIEW")
    session.add_all([job, application])
    await session.commit()
    return job, application


async def _history_rows(session, company, job_id):
    stmt = select(CompanyApplicationHistory).filter_by(company=company, job_id=job_id)
    return (await session.scalars(stmt)).all()


async def test_mark_applied_refuses_without_confirmation(db_session):
    with pytest.raises(ApplicationNotConfirmedError):
        await mark_applied(db_session, application_id=1, job_id=1, company="Acme", confirmed=False)

    assert (await db_session.scalars(select(Application))).first() is None


async def test_mark_applied_updates_status_and_history_when_confirmed(db_session):
    await _make_job_and_application(db_session, job_id=2, application_id=1)
    applied_at = datetime(2026, 1, 15, 9, 0, 0)

    await mark_applied(
        db_session, application_id=1, job_id=2, company="Acme",
        confirmed=True, applied_at=applied_at,
    )

    application = await db_session.get(Application, 1)
    assert application.status == APPLIED_STATUS
    assert application.applied_at == applied_at

    rows = await _history_rows(db_session, "Acme", 2)
    assert len(rows) == 1
    assert rows[0].applied_at == applied_at


async def test_mark_applied_updates_existing_history_row_instead_of_duplicating(db_session):
    await _make_job_and_application(db_session, job_id=2, application_id=1)
    first = datetime(2026, 1, 1, 9, 0, 0)
    second = datetime(2026, 1, 15, 9, 0, 0)

    await mark_applied(db_session, application_id=1, job_id=2, company="Acme", confirmed=True, applied_at=first)
    await mark_applied(db_session, application_id=1, job_id=2, company="Acme", confirmed=True, applied_at=second)

    rows = await _history_rows(db_session, "Acme", 2)
    assert len(rows) == 1
    assert rows[0].applied_at == second


async def test_mark_applied_defaults_applied_at_to_now(db_session):
    await _make_job_and_application(db_session, job_id=2, application_id=1)
    before = datetime.now()

    await mark_applied(db_session, application_id=1, job_id=2, company="Acme", confirmed=True)

    after = datetime.now()
    application = await db_session.get(Application, 1)
    assert before <= application.applied_at <= after


async def test_mark_applied_does_not_fail_when_application_missing(db_session):
    # No Application row for id=1 — mirrors the old raw-SQL UPDATE's silent
    # no-op on zero matched rows; history is still recorded.
    await mark_applied(db_session, application_id=1, job_id=2, company="Acme", confirmed=True)

    rows = await _history_rows(db_session, "Acme", 2)
    assert len(rows) == 1
