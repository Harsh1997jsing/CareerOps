"""Job management and document query endpoints.

Provides read-heavy routes to list jobs with match analysis summaries, view
complete job descriptions with application state, and list generated documents.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from app.api.dependencies import get_db_engine
from app.api.schemas import (
    ApplicationOut,
    GeneratedDocumentOut,
    JobDetailOut,
    JobListItemOut,
)
from app.services import dashboard_data

router = APIRouter(tags=["jobs"])


def _application_out(application) -> ApplicationOut | None:
    """Format an internal ApplicationItem domain model into an ApplicationOut response schema.

    Args:
        application: ApplicationItem instance or None.

    Returns:
        ApplicationOut | None: Formatted response schema or None if no application exists.
    """
    if application is None:
        return None
    return ApplicationOut(
        application_id=application.application_id,
        status=application.status,
        applied_at=application.applied_at.isoformat() if application.applied_at else None,
    )


@router.get("/jobs", response_model=list[JobListItemOut])
def list_jobs(status: str | None = None, engine: Engine = Depends(get_db_engine)):
    """List jobs with their latest fit analysis, optionally filtered by status.

    Args:
        status: Optional status filter (e.g. 'READY_FOR_REVIEW', 'APPROVED', 'REJECT').
        engine: Database engine dependency.

    Returns:
        list[JobListItemOut]: Matching jobs with fit scores and qualification breakdown.
    """
    return [JobListItemOut(**vars(job)) for job in dashboard_data.list_jobs(engine, status)]


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
def get_job(job_id: int, engine: Engine = Depends(get_db_engine)):
    """Fetch complete details for a single job by ID.

    Args:
        job_id: Primary key of the requested job.
        engine: Database engine dependency.

    Returns:
        JobDetailOut: Full job posting details including full description and application record.

    Raises:
        HTTPException: If no job with `job_id` exists (404).
    """
    job = dashboard_data.get_job(engine, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    fields = vars(job).copy()
    fields["application"] = _application_out(fields["application"])
    return JobDetailOut(**fields)


@router.get("/jobs/{job_id}/documents", response_model=list[GeneratedDocumentOut])
def list_documents(job_id: int, engine: Engine = Depends(get_db_engine)):
    """List all generated documents (resumes, cover letters) for a specific job.

    Args:
        job_id: Identifier of the job whose documents to retrieve.
        engine: Database engine dependency.

    Returns:
        list[GeneratedDocumentOut]: List of generated document records with validation flags.
    """
    return [
        GeneratedDocumentOut(**vars(doc))
        for doc in dashboard_data.list_generated_documents(engine, job_id)
    ]
