"""
Lever's public job-board API — no auth, no ToS issue: this is the same JSON
a company's Lever-hosted careers page fetches client-side.
https://api.lever.co/v0/postings/{company_slug}?mode=json
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

JOBS_URL = "https://api.lever.co/v0/postings/{company_slug}"


def _parse_created_at(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000)
    except (TypeError, ValueError, OSError):
        return None


def normalize_job(company: str, raw: dict) -> dict:
    description = strip_html(raw.get("descriptionPlain") or raw.get("description") or "")
    categories = raw.get("categories") or {}

    return {
        "source": "lever",
        "source_job_id": str(raw.get("id", "")),
        "company": company,
        "title": (raw.get("text") or "").strip(),
        "location": normalize_location(categories.get("location", "")),
        "url": raw.get("hostedUrl", ""),
        "description": description,
        "description_hash": description_hash(description),
        "employment_type": normalize_employment_type(categories.get("commitment")),
        "posted_at": _parse_created_at(raw.get("createdAt")),
    }


def fetch_jobs(company_slug: str, company: str, limit: int = MAX_JOBS_PER_RUN) -> list[dict]:
    """
    Fetches up to `limit` (capped at MAX_JOBS_PER_RUN) open postings for a
    Lever company slug — the name in a company's careers URL,
    jobs.lever.co/<company_slug>. `company` is the display name to store
    on each normalized job.
    """
    limit = min(limit, MAX_JOBS_PER_RUN)
    response = requests.get(
        JOBS_URL.format(company_slug=company_slug),
        params={"mode": "json"},
        timeout=15,
    )
    response.raise_for_status()

    raw_jobs = response.json()[:limit]
    return [normalize_job(company, raw) for raw in raw_jobs]
