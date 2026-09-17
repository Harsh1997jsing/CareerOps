"""
Greenhouse's public job-board API — no auth, no ToS issue: this is the same
JSON a company's Greenhouse-hosted careers page fetches client-side.
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""

from datetime import datetime

import requests

from app.sources.common import (
    MAX_JOBS_PER_RUN,
    description_hash,
    normalize_employment_type,
    normalize_location,
    strip_html,
)

JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


def _parse_updated_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _find_employment_type(raw: dict) -> str | None:
    # The base Greenhouse API has no dedicated employment-type field; some
    # boards expose it as a custom "metadata" question instead.
    for field in raw.get("metadata") or []:
        name = (field.get("name") or "").lower()
        if "employment" in name or "job type" in name:
            return field.get("value")
    return None


def normalize_job(company: str, raw: dict) -> dict:
    description = strip_html(raw.get("content", ""))
    raw_location = (raw.get("location") or {}).get("name", "")

    return {
        "source": "greenhouse",
        "source_job_id": str(raw.get("id")),
        "company": company,
        "title": (raw.get("title") or "").strip(),
        "location": normalize_location(raw_location),
        "url": raw.get("absolute_url", ""),
        "description": description,
        "description_hash": description_hash(description),
        "employment_type": normalize_employment_type(_find_employment_type(raw)),
        "posted_at": _parse_updated_at(raw.get("updated_at")),
    }


def fetch_jobs(board_token: str, company: str, limit: int = MAX_JOBS_PER_RUN) -> list[dict]:
    """
    Fetches up to `limit` (capped at MAX_JOBS_PER_RUN) open postings for a
    Greenhouse board token — the slug in a company's careers URL,
    boards.greenhouse.io/<board_token>. `company` is the display name to
    store on each normalized job.
    """
    limit = min(limit, MAX_JOBS_PER_RUN)
    response = requests.get(
        JOBS_URL.format(board_token=board_token),
        params={"content": "true"},
        timeout=15,
    )
    response.raise_for_status()

    raw_jobs = response.json().get("jobs", [])[:limit]
    return [normalize_job(company, raw) for raw in raw_jobs]
