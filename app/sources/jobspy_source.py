"""
Multi-site scrape via the `python-jobspy` library — Glassdoor, Naukri,
Indeed, ZipRecruiter, and Google Jobs. LinkedIn is hardcoded out of the
site list on every call, never optional — see CLAUDE.md rule 2.
"""

import logging
import math
from datetime import date, datetime

from jobspy import scrape_jobs

from app.sources.common import (
    MAX_JOBS_PER_RUN,
    description_hash,
    normalize_employment_type,
    normalize_location,
    strip_html,
)

# The only sites this adapter is allowed to request. "linkedin" is
# deliberately absent — CLAUDE.md rule 2 forbids it outright, so it's
# filtered out below even if a caller passes it explicitly.
ALLOWED_SITES = ["indeed", "glassdoor", "naukri", "zip_recruiter", "google"]

logger = logging.getLogger(__name__)


def _safe_int(value) -> int | None:
    """Safely convert numeric, float, or NaN value into an integer.

    Args:
        value: Numeric value, NaN, string representation, or None.

    Returns:
        int | None: Converted integer, or None if input is None, NaN, or unparseable.
    """
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_posted_at(value) -> datetime | None:
    """Convert various date and string formats from scrape results into a datetime object.

    Args:
        value: Datetime, date, ISO string representation, or None.

    Returns:
        datetime | None: Normalized datetime instance, or None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def normalize_job(row: dict) -> dict:
    """Normalize a raw python-jobspy DataFrame dictionary row into schema format.

    Args:
        row: Record dictionary from python-jobspy DataFrame.

    Returns:
        dict: Normalized job payload conforming to `jobs` database table.
    """
    description = strip_html(row.get("description") or "")
    url = row.get("job_url") or row.get("job_url_direct") or ""

    return {
        "source": row.get("site") or "jobspy",
        "source_job_id": str(row.get("id") or description_hash(url or description)[:16]),
        "company": (row.get("company") or "").strip(),
        "title": (row.get("title") or "").strip(),
        "location": normalize_location(row.get("location") or ""),
        "url": url,
        "description": description,
        "description_hash": description_hash(description),
        "employment_type": normalize_employment_type(row.get("job_type")),
        "posted_at": _parse_posted_at(row.get("date_posted")),
        "salary_min": _safe_int(row.get("min_amount")),
        "salary_max": _safe_int(row.get("max_amount")),
    }


def fetch_jobs(
    search_term: str,
    location: str | None = None,
    sites: list[str] | None = None,
    results_wanted: int = MAX_JOBS_PER_RUN,
    **kwargs,
) -> list[dict]:
    """Scrape job postings matching a search term across allowed job board sites.

    Scrapes up to `results_wanted` (capped at MAX_JOBS_PER_RUN) postings
    matching `search_term` across `sites` (default: all of ALLOWED_SITES).
    Any "linkedin" entry in `sites` is dropped before the call is made (CLAUDE.md rule 2).

    Args:
        search_term: Keywords or title query to scrape for.
        location: Optional location query.
        sites: List of job sites to scrape (defaults to ALLOWED_SITES).
        results_wanted: Target number of postings (capped at MAX_JOBS_PER_RUN = 50).
        **kwargs: Additional parameters forwarded to `jobspy.scrape_jobs`.

    Returns:
        list[dict]: Normalized job dictionaries.
    """
    site_name = [s for s in (sites or ALLOWED_SITES) if s in ALLOWED_SITES]
    dropped = set(sites or []) - set(site_name)
    if dropped:
        logger.warning("dropped disallowed jobspy sites: %s", sorted(dropped))
    if not site_name:
        return []

    limit = min(results_wanted, MAX_JOBS_PER_RUN)
    df = scrape_jobs(
        site_name=site_name,
        search_term=search_term,
        location=location,
        results_wanted=limit,
        **kwargs,
    )
    if df is None or df.empty:
        return []

    rows = df.to_dict("records")[:limit]
    return [normalize_job(row) for row in rows]
