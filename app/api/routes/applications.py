"""Application workflow endpoints.

Provides endpoints to approve, reject, open the external posting URL for manual
review, and record human-confirmed submissions. Enforces strict human-in-the-loop
guarantees (CLAUDE.md rule 1 and rule 5).

Every route requires a valid bearer token (`Depends(get_current_user)` at
the router level, audit finding F1) — no tenant scoping yet on the
underlying data (audit finding F2), see jobs.py's module docstring.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.api.schemas import ApplicationActionOut
from app.models import Application
from app.services import applications as applications_service
from app.services import tracker

router = APIRouter(prefix="/applications", tags=["applications"], dependencies=[Depends(get_current_user)])


async def _get_application_or_404(session: AsyncSession, application_id: int) -> Application:
    """Fetch the Application ORM row once (job eager-loaded); every route
    below reuses this same object for both reading context and mutating
    it, instead of fetching by id a second time (audit finding F4 — see
    applications_service.get_application()'s docstring for why the
    re-fetch happened in the first place).

    Raises:
        HTTPException: If no application matching `application_id` exists.
    """
    application = await applications_service.get_application(session, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    return application


@router.post("/{application_id}/approve", response_model=ApplicationActionOut)
async def approve(application_id: int, session: AsyncSession = Depends(get_db)):
    """Mark an application package as human-approved for submission.

    Args:
        application_id: Identifier of the application to approve.
        session: Database session dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'APPROVED'.
    """
    application = await _get_application_or_404(session, application_id)
    await applications_service.set_status(session, application, applications_service.APPROVED_STATUS)
    return ApplicationActionOut(application_id=application_id, status=applications_service.APPROVED_STATUS)


@router.post("/{application_id}/reject", response_model=ApplicationActionOut)
async def reject(application_id: int, session: AsyncSession = Depends(get_db)):
    """Mark an application package as rejected.

    Args:
        application_id: Identifier of the application to reject.
        session: Database session dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'REJECTED'.
    """
    application = await _get_application_or_404(session, application_id)
    await applications_service.set_status(session, application, applications_service.REJECTED_STATUS)
    return ApplicationActionOut(application_id=application_id, status=applications_service.REJECTED_STATUS)


@router.post("/{application_id}/open", response_model=ApplicationActionOut)
async def open_application(application_id: int, session: AsyncSession = Depends(get_db)):
    """Open the external job posting in the user's local browser tab.

    Opens the job posting in a browser tab on the machine running this API
    process — never fills in or submits anything. Only makes sense when
    the API and the human reviewing it are on the same machine, same as
    the rest of this local-first tool; see CLAUDE.md rule 1.

    Args:
        application_id: Identifier of the application whose posting to open.
        session: Database session dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'OPENED'.
    """
    application = await _get_application_or_404(session, application_id)
    tracker.open_job_url(application.job.url)
    return ApplicationActionOut(application_id=application_id, status="OPENED")


@router.post("/{application_id}/mark-applied", response_model=ApplicationActionOut)
async def mark_applied(application_id: int, session: AsyncSession = Depends(get_db)):
    """Record that the user has manually submitted an application in their browser.

    The only route that can set an application to APPLIED. `confirmed=True`
    here reflects the human clicking a distinct, explicit confirmation
    control in the frontend (see frontend/README.md rule 2) — this route
    itself is the confirmation, there is no earlier implicit path to it.

    Args:
        application_id: Identifier of the submitted application.
        session: Database session dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'APPLIED'.
    """
    application = await _get_application_or_404(session, application_id)
    await tracker.mark_applied(
        session,
        application_id=application_id,
        job_id=application.job_id,
        company=application.job.company,
        confirmed=True,
        application=application,
    )
    return ApplicationActionOut(application_id=application_id, status=tracker.APPLIED_STATUS)
