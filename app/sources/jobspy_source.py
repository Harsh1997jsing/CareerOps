"""
Multi-site scrape via the `python-jobspy` library — Glassdoor, Naukri,
Indeed, ZipRecruiter, and Google Jobs. LinkedIn is hardcoded out of the
site list on every call, never optional — see CLAUDE.md rule 2.
"""

import logging
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime

from jobspy import scrape_jobs

from app.sources.common import (
    MAX_JOBS_PER_RUN,
    description_hash,
    matches_experience,
    normalize_employment_type,
    normalize_location,
    safe_int,
    strip_html,
)

# The only sites this adapter is allowed to request. "linkedin" is
# deliberately absent — CLAUDE.md rule 2 forbids it outright, so it's
# filtered out below even if a caller passes it explicitly.
ALLOWED_SITES = ["indeed", "glassdoor", "naukri", "zip_recruiter", "google"]

# jobspy.scrape_jobs()'s own default is "usa" — this app's whole location
# vocabulary is India-only (data/constraints.yaml's allowed_locations:
# Remote/Bangalore/Pune/Hyderabad), so leaving the default in place makes
# Indeed silently search the wrong country's catalog and return zero
# results for every India query (confirmed: same search+location returned
# 0 rows against "usa", 5 real rows against "india"). Glassdoor reads the
# same setting for which country's site to hit.
DEFAULT_COUNTRY = "india"

# jobspy.scrape_jobs() accepts **kwargs but doesn't actually thread a
# timeout through to any scraper (verified against the installed
# python-jobspy source — the kwarg is silently dropped). Each site scraper
# hardcodes its own short per-request timeout internally (10-15s), but
# there's no outer bound on the whole call, which fans out to every
# requested site concurrently via jobspy's own thread pool. This wraps it
# in one so a single hung site can't block the caller indefinitely
# (audit finding F10).
FETCH_TIMEOUT_SECONDS = 90

logger = logging.getLogger(__name__)


def _clean_str(value) -> str:
    """Coerce a python-jobspy DataFrame cell to a plain string, NaN-safe.

    A pandas DataFrame represents a missing value in an object (string)
    column as `float('nan')`, not `None` — and the once-common `value or
    default` guard doesn't catch it, since `bool(float('nan'))` is `True`
    in Python. Left unguarded, that NaN reaches a `.strip()`/`.lower()`
    call downstream and raises `AttributeError: 'float' object has no
    attribute 'strip'`, crashing the whole scrape with a 500 (confirmed
    live via `POST /scrape/jobspy` — `job_type` was the one that surfaced
    it, but `company`/`title`/`location`/`description`/the URL fields were
    equally exposed). Cleaning every DataFrame cell through this the
    moment it's read is cheaper than guarding every downstream `.strip()`
    call individually.

    Args:
        value: A raw DataFrame cell — a string, NaN, None, or absent.

    Returns:
        str: The value as a string, "" if it was missing/NaN/None.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


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
    description = strip_html(_clean_str(row.get("description")))
    url = _clean_str(row.get("job_url")) or _clean_str(row.get("job_url_direct"))

    return {
        "source": _clean_str(row.get("site")) or "jobspy",
        "source_job_id": _clean_str(row.get("id")) or description_hash(url or description)[:16],
        "company": _clean_str(row.get("company")).strip(),
        "title": _clean_str(row.get("title")).strip(),
        "location": normalize_location(_clean_str(row.get("location"))),
        "url": url,
        "description": description,
        "description_hash": description_hash(description),
        "employment_type": normalize_employment_type(row.get("job_type")),
        "posted_at": _parse_posted_at(row.get("date_posted")),
        "salary_min": safe_int(row.get("min_amount")),
        "salary_max": safe_int(row.get("max_amount")),
    }


def _experience_haystack(row: dict) -> str:
    """Build the experience-matching text for a raw jobspy row.

    jobspy.scrape_jobs() has no experience/seniority filter parameter
    (verified against the installed python-jobspy source) — it's exposed
    only as an output field, and only for two of the five allowed sites:
    LinkedIn's `job_level` (e.g. "Entry level") isn't reachable here since
    LinkedIn is never scraped (CLAUDE.md rule 2), but Naukri's
    `experience_range` (e.g. "3-5 Yrs") is. See
    `app/sources/common.py:matches_experience()` for the actual match.

    Args:
        row: Raw jobspy DataFrame record, before normalize_job() strips it.

    Returns:
        str: The row's job_level + experience_range fields, space-joined.
    """
    return " ".join([_clean_str(row.get("job_level")), _clean_str(row.get("experience_range"))])


def fetch_jobs(
    search_term: str,
    location: str | None = None,
    sites: list[str] | None = None,
    results_wanted: int = MAX_JOBS_PER_RUN,
    experience: str | None = None,
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
        experience: Optional free-text experience-level filter, applied
            app-side after scraping (see matches_experience) since jobspy
            has no matching input parameter. Postings from sites that
            don't report an experience field are dropped when this is set.
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
    kwargs.setdefault("country_indeed", DEFAULT_COUNTRY)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            scrape_jobs,
            site_name=site_name,
            search_term=search_term,
            location=location,
            results_wanted=limit,
            **kwargs,
        )
        try:
            df = future.result(timeout=FETCH_TIMEOUT_SECONDS)
        except FutureTimeoutError as exc:
            raise TimeoutError(
                f"jobspy.scrape_jobs() did not return within {FETCH_TIMEOUT_SECONDS}s "
                f"(sites={site_name}, search_term={search_term!r})"
            ) from exc

    if df is None or df.empty:
        return []

    rows = df.to_dict("records")
    if experience:
        rows = [row for row in rows if matches_experience(_experience_haystack(row), experience)]
    rows = rows[:limit]
    return [normalize_job(row) for row in rows]
