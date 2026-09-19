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

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.api.schemas import (
    CapabilityMatrixOut,
    ExploreResultOut,
    ExploreSaveRequest,
    ExploreSaveResponseOut,
    ExploreSearchRequest,
)
from app.sources.common import description_hash, insert_jobs
from app.sources.mcp import explore as mcp_explore

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
async def save(payload: ExploreSaveRequest, session: AsyncSession = Depends(get_db)):
    """Persist a user-selected discovered job into the local `jobs` table.

    The shared save endpoint for Explore, `/targets/search`, and
    `/scrape/jobspy` alike (see module docstring) — none of those results
    are cached server-side, so there's no id to save by; the frontend
    posts the full result it already has back here. This is the only way
    any of them enters `jobs`; the description hash is recomputed
    server-side rather than trusted from the client.

    Args:
        payload: ExploreSaveRequest containing full job posting details.
        session: Database session dependency.

    Returns:
        ExploreSaveResponseOut: Whether the job was newly inserted (False if duplicate).
    """
    job = {
        "source": payload.source,
        "source_job_id": payload.source_job_id,
        "company": payload.company,
        "title": payload.title,
        "location": payload.location,
        "url": payload.url,
        "description": payload.description,
        "description_hash": description_hash(payload.description),
        "employment_type": payload.employment_type,
        "posted_at": payload.posted_at,
        "salary_min": payload.salary_min,
        "salary_max": payload.salary_max,
    }
    inserted = await insert_jobs(session, [job])
    return ExploreSaveResponseOut(inserted=bool(inserted))
