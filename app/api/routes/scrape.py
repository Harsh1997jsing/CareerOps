"""Multi-site JobSpy scrape endpoint.

Exposes app/sources/jobspy_source.py's fetch_jobs() over HTTP — previously
only callable from Python. LinkedIn is never requestable: fetch_jobs()
itself drops anything outside ALLOWED_SITES before scraping (CLAUDE.md
rule 2), so this route doesn't need to re-enforce that.

Results are never auto-inserted — same search-then-select-then-save flow
as Explore/targets (`/explore/save`, shared across every discovery
source). See that route's docstring.

Every route requires a valid bearer token (`Depends(get_current_user)` at
the router level, same pattern as every other route module).
"""

import asyncio

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.schemas import ExploreResultOut, ScrapeJobspyRequest
from app.sources import jobspy_source

router = APIRouter(tags=["scrape"], dependencies=[Depends(get_current_user)])


@router.post("/scrape/jobspy", response_model=list[ExploreResultOut])
async def scrape_jobspy(payload: ScrapeJobspyRequest):
    """Scrape job postings across allowed sites, without saving them.

    fetch_jobs() is synchronous and can take up to its own 90s internal
    timeout (FETCH_TIMEOUT_SECONDS) — run via asyncio.to_thread so a slow
    scrape doesn't block the event loop for every other request.

    Args:
        payload: Search term, optional location/sites/results_wanted.

    Returns:
        list[ExploreResultOut]: Normalized postings — save the ones you
            want via POST /explore/save.
    """
    jobs = await asyncio.to_thread(
        jobspy_source.fetch_jobs,
        payload.search_term,
        payload.location,
        payload.sites,
        payload.results_wanted,
        payload.experience,
    )
    return [ExploreResultOut(**job) for job in jobs]
