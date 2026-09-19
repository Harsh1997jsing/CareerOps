"""Manual company-target listing and search endpoints.

Exposes app/sources/targets.py's Greenhouse/Lever fetch over HTTP —
previously only callable from Python. See CONTRACT.md.

Search results are never auto-inserted — same search-then-select-then-save
flow as Explore (`/explore/search` + `/explore/save`), reused here so a
target search doesn't silently dump un-reviewed postings into the
Dashboard. See `/explore/save`'s docstring.

Every route requires a valid bearer token (`Depends(get_current_user)` at
the router level, same pattern as every other route module).
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.schemas import CompanyTargetOut, ExploreResultOut
from app.sources import targets

router = APIRouter(tags=["targets"], dependencies=[Depends(get_current_user)])


@router.get("/targets", response_model=list[CompanyTargetOut])
async def list_targets():
    """List every company target configured in data/companies.yaml.

    Returns:
        list[CompanyTargetOut]: Configured Greenhouse and Lever targets.
    """
    config = targets.load_company_targets()
    items = [
        CompanyTargetOut(source="greenhouse", company=entry["company"], identifier=entry["board_token"])
        for entry in config.get("greenhouse") or []
    ]
    items += [
        CompanyTargetOut(source="lever", company=entry["company"], identifier=entry["company_slug"])
        for entry in config.get("lever") or []
    ]
    return items


@router.post("/targets/search", response_model=list[ExploreResultOut])
async def search_targets():
    """Fetch postings from every configured company target, without saving them.

    Returns:
        list[ExploreResultOut]: Normalized postings — save the ones you
            want via POST /explore/save.
    """
    jobs = await targets.search_all()
    return [ExploreResultOut(**job) for job in jobs]
