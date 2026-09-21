from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.models import Application
from app.services.applications import (
    APPROVED_STATUS,
    REJECTED_STATUS,
    approve_application,
    check_cooldown_for_company,
    create_application,
    get_application_context,
    get_application_for_job,
    reject_application,
    set_application_status,
)
from tests.conftest import make_job


async def test_get_application_for_job_returns_none_when_missing(db_session):
    assert await get_application_for_job(db_session, job_id=1) is None


async def test_create_application_creates_a_new_row(db_session):
    await make_job(db_session)

    application = await create_application(db_session, job_id=1)

    assert application.job_id == 1
    assert application.status == "READY_FOR_REVIEW"


async def test_create_application_is_idempotent(db_session):
    await make_job(db_session)

    first = await create_application(db_session, job_id=1)
    second = await create_application(db_session, job_id=1)

    assert first.id == second.id


async def test_get_application_for_job_returns_item_when_found(db_session):
    await make_job(db_session)
    db_session.add(Application(id=5, job_id=1, status="READY_FOR_REVIEW"))
    await db_session.commit()

    application = await get_application_for_job(db_session, job_id=1)

    assert application.application_id == 5
    assert application.job_id == 1


async def test_check_cooldown_for_company_blocks_recent_application(db_session):
    recent_date = datetime.now() - timedelta(days=5)

    with patch("app.services.applications.get_company_applied_dates", AsyncMock(return_value=[recent_date])):
        result = await check_cooldown_for_company(db_session, "Acme", cooldown_days=30)

    assert not result.passed


async def test_check_cooldown_for_company_allows_no_history(db_session):
    with patch("app.services.applications.get_company_applied_dates", AsyncMock(return_value=[])):
        result = await check_cooldown_for_company(db_session, "Acme", cooldown_days=30)

    assert result.passed


async def test_set_application_status_updates_existing_row(db_session):
    await make_job(db_session)
    db_session.add(Application(id=7, job_id=1, status="READY_FOR_REVIEW"))
    await db_session.commit()

    await set_application_status(db_session, application_id=7, status="APPROVED")

    assert (await db_session.get(Application, 7)).status == "APPROVED"


async def test_set_application_status_no_ops_when_missing(db_session):
    # Mirrors the old raw-SQL UPDATE's silent no-op on zero matched rows.
    await set_application_status(db_session, application_id=999, status="APPROVED")


async def test_approve_application_uses_approved_status(db_session):
    await make_job(db_session)
    db_session.add(Application(id=7, job_id=1, status="READY_FOR_REVIEW"))
    await db_session.commit()

    await approve_application(db_session, application_id=7)

    assert (await db_session.get(Application, 7)).status == APPROVED_STATUS


async def test_reject_application_uses_rejected_status(db_session):
    await make_job(db_session)
    db_session.add(Application(id=7, job_id=1, status="READY_FOR_REVIEW"))
    await db_session.commit()

    await reject_application(db_session, application_id=7)

    assert (await db_session.get(Application, 7)).status == REJECTED_STATUS


async def test_get_application_context_returns_none_when_missing(db_session):
    assert await get_application_context(db_session, application_id=7) is None


async def test_get_application_context_maps_fields(db_session):
    await make_job(db_session)
    db_session.add(Application(id=7, job_id=1, status="READY_FOR_REVIEW"))
    await db_session.commit()

    context = await get_application_context(db_session, application_id=7)

    assert context.application_id == 7
    assert context.job_id == 1
    assert context.company == "Acme"
    assert context.url == "https://example.com/job/1"
