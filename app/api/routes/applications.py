"""Application workflow endpoints.

Provides endpoints to approve, reject, open the external posting URL for manual
review, and record human-confirmed submissions. Enforces strict human-in-the-loop
guarantees (CLAUDE.md rule 1 and rule 5).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from app.api.dependencies import get_db_engine
from app.api.schemas import ApplicationActionOut
from app.services import dashboard_data, tracker

router = APIRouter(prefix="/applications", tags=["applications"])


def _require_context(engine: Engine, application_id: int) -> dashboard_data.ApplicationContext:
    """Retrieve application and job context, raising 404 if not found.

    Args:
        engine: Database engine instance.
        application_id: Application primary key.

    Returns:
        ApplicationContext: Application metadata and linked job details.

    Raises:
        HTTPException: If no application matching `application_id` exists.
    """
    context = dashboard_data.get_application_context(engine, application_id)
    if context is None:
        raise HTTPException(status_code=404, detail="application not found")
    return context


@router.post("/{application_id}/approve", response_model=ApplicationActionOut)
def approve(application_id: int, engine: Engine = Depends(get_db_engine)):
    """Mark an application package as human-approved for submission.

    Args:
        application_id: Identifier of the application to approve.
        engine: Database engine dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'APPROVED'.
    """
    _require_context(engine, application_id)
    dashboard_data.approve_application(engine, application_id)
    return ApplicationActionOut(application_id=application_id, status=dashboard_data.APPROVED_STATUS)


@router.post("/{application_id}/reject", response_model=ApplicationActionOut)
def reject(application_id: int, engine: Engine = Depends(get_db_engine)):
    """Mark an application package as rejected.

    Args:
        application_id: Identifier of the application to reject.
        engine: Database engine dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'REJECTED'.
    """
    _require_context(engine, application_id)
    dashboard_data.reject_application(engine, application_id)
    return ApplicationActionOut(application_id=application_id, status=dashboard_data.REJECTED_STATUS)


@router.post("/{application_id}/open", response_model=ApplicationActionOut)
def open_application(application_id: int, engine: Engine = Depends(get_db_engine)):
    """Open the external job posting in the user's local browser tab.

    Opens the job posting in a browser tab on the machine running this API
    process — never fills in or submits anything. Only makes sense when
    the API and the human reviewing it are on the same machine, same as
    the rest of this local-first tool; see CLAUDE.md rule 1.

    Args:
        application_id: Identifier of the application whose posting to open.
        engine: Database engine dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'OPENED'.
    """
    context = _require_context(engine, application_id)
    tracker.open_job_url(context.url)
    return ApplicationActionOut(application_id=application_id, status="OPENED")


@router.post("/{application_id}/mark-applied", response_model=ApplicationActionOut)
def mark_applied(application_id: int, engine: Engine = Depends(get_db_engine)):
    """Record that the user has manually submitted an application in their browser.

    The only route that can set an application to APPLIED. `confirmed=True`
    here reflects the human clicking a distinct, explicit confirmation
    control in the frontend (see frontend/README.md rule 2) — this route
    itself is the confirmation, there is no earlier implicit path to it.

    Args:
        application_id: Identifier of the submitted application.
        engine: Database engine dependency.

    Returns:
        ApplicationActionOut: Action confirmation with status 'APPLIED'.
    """
    context = _require_context(engine, application_id)
    tracker.mark_applied(
        engine,
        application_id=application_id,
        job_id=context.job_id,
        company=context.company,
        confirmed=True,
    )
    return ApplicationActionOut(application_id=application_id, status=tracker.APPLIED_STATUS)
