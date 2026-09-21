"""Job management and document query endpoints.

Provides read-heavy routes to list jobs with match analysis summaries, view
complete job descriptions with application state, and list generated documents.

Every route requires a valid bearer token (`Depends(get_current_user)` at
the router level, audit finding F1) — but note this only checks *who*
you are, not *which tenant's* data you can see: `Job`/`Application`/
`GeneratedDocument` carry no `tenant_id` (audit finding F2), so any
authenticated user of any tenant can read/act on any job today. That's a
deliberate, documented scope boundary for this pass, not an oversight —
see backend.md and memory/known-gaps.md.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.schemas import (
    GenerateDocumentRequest,
    GeneratedDocumentOut,
    JobDetailOut,
    JobListItemOut,
    JobStatusActionOut,
)
from app.core import get_db
from app.core.config import get_settings
from app.services import document_generator
from app.services import job_scorer
from app.services import jobs as jobs_service

router = APIRouter(tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.get("/jobs", response_model=list[JobListItemOut])
async def list_jobs(
    status: str | None = None,
    q: str | None = None,
    posted_within_days: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """List jobs with their latest fit analysis, optionally filtered by status.

    Args:
        status: Optional status filter (e.g. 'READY_FOR_REVIEW', 'APPROVED', 'REJECT').
        q: Optional case-insensitive substring match against the job description.
        posted_within_days: Optional recency filter — keeps only jobs
            posted (or, lacking that, collected) within this many days.
        limit: Maximum rows to return (1-200, default 50). Audit finding F8 —
            previously unbounded.
        offset: Rows to skip, for paging past `limit`.
        session: Database session dependency.

    Returns:
        list[JobListItemOut]: Matching jobs with fit scores and qualification breakdown.
    """
    items = await jobs_service.list_jobs(
        session, status, limit=limit, offset=offset, q=q, posted_within_days=posted_within_days
    )
    return [JobListItemOut.model_validate(item, from_attributes=True) for item in items]


async def _get_job_or_404(session: AsyncSession, job_id: int):
    job = await jobs_service.get_job_by_id(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/jobs/{job_id}/reject", response_model=JobStatusActionOut)
async def reject_job(job_id: int, session: AsyncSession = Depends(get_db)):
    """Hide a job from the default Dashboard view by setting its status to REJECTED.

    Sets `Job.status` directly rather than going through
    /applications/{id}/reject — this predates a job having an Application
    row at all (one now exists once /jobs/{job_id}/documents has been
    called at least once) and stays a distinct mechanism: hiding a job
    from the Dashboard is not an application-workflow decision. Reversible
    via POST /jobs/{job_id}/restore.

    Args:
        job_id: Identifier of the job to reject.
        session: Database session dependency.

    Returns:
        JobStatusActionOut: The job's id and its new status.
    """
    job = await _get_job_or_404(session, job_id)
    await jobs_service.set_job_status(session, job, jobs_service.REJECTED_JOB_STATUS)
    return JobStatusActionOut(job_id=job_id, status=jobs_service.REJECTED_JOB_STATUS)


@router.post("/jobs/{job_id}/restore", response_model=JobStatusActionOut)
async def restore_job(job_id: int, session: AsyncSession = Depends(get_db)):
    """Undo a reject — sets a job's status back to DISCOVERED.

    Args:
        job_id: Identifier of the job to restore.
        session: Database session dependency.

    Returns:
        JobStatusActionOut: The job's id and its new status.
    """
    job = await _get_job_or_404(session, job_id)
    await jobs_service.set_job_status(session, job, jobs_service.DEFAULT_JOB_STATUS)
    return JobStatusActionOut(job_id=job_id, status=jobs_service.DEFAULT_JOB_STATUS)


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
async def get_job(job_id: int, session: AsyncSession = Depends(get_db)):
    """Fetch complete details for a single job by ID.

    Args:
        job_id: Primary key of the requested job.
        session: Database session dependency.

    Returns:
        JobDetailOut: Full job posting details including full description and application record.

    Raises:
        HTTPException: If no job with `job_id` exists (404).
    """
    job = await jobs_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    return JobDetailOut.model_validate(job, from_attributes=True)


@router.get("/jobs/{job_id}/documents", response_model=list[GeneratedDocumentOut])
async def list_documents(job_id: int, session: AsyncSession = Depends(get_db)):
    """List all generated documents (resumes, cover letters) for a specific job.

    Args:
        job_id: Identifier of the job whose documents to retrieve.
        session: Database session dependency.

    Returns:
        list[GeneratedDocumentOut]: List of generated document records with validation flags.
    """
    docs = await jobs_service.list_generated_documents(session, job_id)
    return [GeneratedDocumentOut.model_validate(doc, from_attributes=True) for doc in docs]


@router.post("/jobs/{job_id}/analyze", response_model=JobDetailOut)
async def analyze_job(job_id: int, session: AsyncSession = Depends(get_db)):
    """Score a job's fit against candidate skills/evidence/constraints and record it.

    Runs job_scorer.score_job() against the job's description, persists
    the result as a new JobAnalysis row (job_scorer.decide()'s REJECT/
    READY_FOR_REVIEW/REVIEW_REQUIRED outcome also becomes the job's new
    Job.status), and returns the job's refreshed detail view. Re-running
    this on an already-analyzed job adds a new analysis row rather than
    replacing the old one — see jobs_service.record_analysis().

    Args:
        job_id: Identifier of the job to score.
        session: Database session dependency.

    Returns:
        JobDetailOut: The job's detail view with its new fit score/status.

    Raises:
        HTTPException: 404 if no job with `job_id` exists.
    """
    job = await _get_job_or_404(session, job_id)
    settings = get_settings()
    analysis = job_scorer.score_job(
        job.description, settings.skills_path, settings.evidence_path, settings.constraints_path
    )
    await jobs_service.record_analysis(session, job, analysis)
    await jobs_service.set_job_status(session, job, job_scorer.decide(analysis))

    updated = await jobs_service.get_job(session, job_id)
    return JobDetailOut.model_validate(updated, from_attributes=True)


@router.post("/jobs/{job_id}/documents", response_model=GeneratedDocumentOut)
async def generate_document(job_id: int, payload: GenerateDocumentRequest, session: AsyncSession = Depends(get_db)):
    """Generate a tailored resume or cover letter for a job.

    Writes the document to a .docx, runs it through claim/ATS validation
    (see app/services/document_generator.py), and get-or-creates the
    job's Application row — this, not a separate action, is what starts a
    job's real application workflow (approve/open/mark-applied, all keyed
    by application_id — see app/api/routes/applications.py).

    Args:
        job_id: Identifier of the job to generate a document for.
        payload: Which document type to generate.
        session: Database session dependency.

    Returns:
        GeneratedDocumentOut: The new document's metadata, including
            whether it passed claim verification and ATS checks.

    Raises:
        HTTPException: 404 if no job with `job_id` exists.
    """
    job = await _get_job_or_404(session, job_id)
    document = await document_generator.generate_document(session, job, payload.type)
    return GeneratedDocumentOut.model_validate(document, from_attributes=True)
