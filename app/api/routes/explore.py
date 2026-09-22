"""Explore endpoints for remote MCP job search, plus the shared save route.

Allows querying connected MCP servers for capabilities and fanning out
live searches. `/explore/save` is misleadingly named by history, not by
current scope: it's the single "add this discovered job to the Dashboard"
endpoint for every discovery source — Explore, `/targets/search`, and
`/scrape/jobspy` all hand back the same `ExploreResultOut` shape and all
save through here, so a job is never inserted until the user explicitly
picks it, regardless of which page found it.

Every route requires a valid bearer token (`Depends(get_current_user)` at
the router level, audit finding F1).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.schemas import (
    CapabilityMatrixOut,
    ExploreResultOut,
    ExploreSaveRequest,
    ExploreSaveResponseOut,
    ExploreSearchRequest,
)
from app.core import get_db
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models import Job
from app.services import jobs as jobs_service
from app.sources.common import description_hash, insert_jobs
from app.sources.mcp import explore as mcp_explore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/explore", tags=["explore"], dependencies=[Depends(get_current_user)])


@router.get("/capabilities", response_model=dict[str, CapabilityMatrixOut])
async def capabilities():
    """Retrieve capability matrices for all configured MCP job sources.

    Returns:
        dict[str, CapabilityMatrixOut]: Mapping from source names to their supported
            search and filter feature flags.
    """
    matrix = await mcp_explore.get_all_capabilities()
    return {
        name: CapabilityMatrixOut(flags=capability.flags, required_filters=capability.required_filters)
        for name, capability in matrix.items()
    }


@router.post("/search", response_model=list[ExploreResultOut])
async def search(payload: ExploreSearchRequest):
    """Perform a distributed search across all active MCP servers.

    Args:
        payload: ExploreSearchRequest containing search query and filter parameters.

    Returns:
        list[ExploreResultOut]: Normalized job postings aggregated from responsive sources.
    """
    results = await mcp_explore.search(payload.query, payload.filters)
    return [ExploreResultOut(**result) for result in results]


@router.post("/save", response_model=ExploreSaveResponseOut)
async def save(payload: ExploreSaveRequest, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_db)):
    """Persist a user-selected discovered job into the local `jobs` table.

    The shared save endpoint for Explore, `/targets/search`, and
    `/scrape/jobspy` alike (see module docstring) — none of those results
    are cached server-side, so there's no id to save by; the frontend
    posts the full result it already has back here. This is the only way
    any of them enters `jobs`; the description hash is recomputed
    server-side rather than trusted from the client.

    A newly inserted (non-duplicate) job is queued for auto-analysis
    (`_auto_analyze()` below) via FastAPI's `BackgroundTasks`, which runs
    after the response is sent — so the save itself stays fast and the job
    no longer sits at `DISCOVERED` until someone opens its Job Detail page
    and clicks Analyze (see memory/known-gaps.md).

    Args:
        payload: ExploreSaveRequest containing full job posting details.
        background_tasks: FastAPI background-task queue.
        session: Database session dependency.

    Returns:
        ExploreSaveResponseOut: Whether the job was newly inserted (False if duplicate).
    """
    hash_ = description_hash(payload.description)
    job = {
        "source": payload.source,
        "source_job_id": payload.source_job_id,
        "company": payload.company,
        "title": payload.title,
        "location": payload.location,
        "url": payload.url,
        "description": payload.description,
        "description_hash": hash_,
        "employment_type": payload.employment_type,
        "posted_at": payload.posted_at,
        "salary_min": payload.salary_min,
        "salary_max": payload.salary_max,
    }
    inserted = await insert_jobs(session, [job])
    if inserted:
        background_tasks.add_task(_auto_analyze, hash_)
    return ExploreSaveResponseOut(inserted=bool(inserted))


async def _auto_analyze(job_description_hash: str) -> None:
    """Run jobs_service.analyze_job() against a just-saved job, off-request.

    Opens its own session (the request's `get_db()` session is already
    closed by the time a BackgroundTasks callback runs) and looks the job
    up by `description_hash` rather than carrying an id across the
    boundary, since `insert_jobs()` only reports a count, not the row.
    Logs and swallows any failure (a DB connection error, a bad LLM call,
    a missing evidence file) rather than raising — a Starlette
    BackgroundTasks callback that raises propagates out of the ASGI call
    after the response has already been sent, so nothing here can be
    allowed to escape. A job that fails auto-analysis simply stays at
    `DISCOVERED` for manual analysis later, same as before this existed.

    Args:
        job_description_hash: The saved job's `Job.description_hash`.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as bg_session:
            job = await bg_session.scalar(select(Job).where(Job.description_hash == job_description_hash))
            if job is None:
                return
            await jobs_service.analyze_job(bg_session, job, get_settings())
    except Exception:
        logger.exception("auto-analyze failed for job description_hash=%s", job_description_hash)
