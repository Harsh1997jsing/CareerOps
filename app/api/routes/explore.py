"""Explore endpoints for remote MCP job search and curation.

Allows querying connected MCP servers for capabilities, fanning out live searches,
and saving selected postings into the local `jobs` table.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from app.api.dependencies import get_db_engine
from app.api.schemas import (
    CapabilityMatrixOut,
    ExploreResultOut,
    ExploreSaveRequest,
    ExploreSaveResponseOut,
    ExploreSearchRequest,
)
from app.sources.common import description_hash, insert_jobs
from app.sources.mcp import explore as mcp_explore

router = APIRouter(prefix="/explore", tags=["explore"])


@router.get("/capabilities", response_model=dict[str, CapabilityMatrixOut])
async def capabilities():
    """Retrieve capability matrices for all configured MCP job sources.

    Returns:
        dict[str, CapabilityMatrixOut]: Mapping from source names to their supported
            search and filter feature flags.
    """
    matrix = await mcp_explore.get_all_capabilities()
    return {name: CapabilityMatrixOut(flags=capability.flags) for name, capability in matrix.items()}


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
def save(payload: ExploreSaveRequest, engine: Engine = Depends(get_db_engine)):
    """Persist a selected exploration result into the local `jobs` table.

    Explore results aren't cached server-side (see mcp/explore.py), so
    there's no id to save by — the frontend posts the result it already
    has back here. Only way an Explore result enters `jobs`; the hash is
    recomputed server-side rather than trusted from the client.

    Args:
        payload: ExploreSaveRequest containing full job posting details.
        engine: Database engine dependency.

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
        "posted_at": None,
    }
    inserted = insert_jobs(engine, [job])
    return ExploreSaveResponseOut(inserted=bool(inserted))
