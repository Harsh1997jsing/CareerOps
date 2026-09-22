"""
Shared helpers for job-board source adapters: HTML stripping, location/
employment-type normalization onto the vocabulary hard_filters.py and
data/constraints.yaml expect, the description hash used for
jobs.description_hash dedupe, and the shared insert that skips anything
already collected.
"""

import hashlib
import math
import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job

# No source adapter should ever pull more than this many postings in one
# run — this is a job-fit assistant, not a scraper.
MAX_JOBS_PER_RUN = 50

LOCATION_ALIASES = {
    "remote": "Remote",
    "bangalore": "Bangalore",
    "bengaluru": "Bangalore",
    "pune": "Pune",
    "hyderabad": "Hyderabad",
}

EMPLOYMENT_TYPE_ALIASES = {
    "full-time": "Full-time",
    "full time": "Full-time",
    "fulltime": "Full-time",
    "part-time": "Part-time",
    "part time": "Part-time",
    "contract": "Contract",
    "contractor": "Contract",
    "intern": "Internship",
    "internship": "Internship",
}


def safe_int(value) -> int | None:
    """Safely coerce a numeric value (possibly a float, NaN, or string) to an int.

    An MCP source's JSON can hand back a salary as a float (e.g. HasData:
    `18590.084`), which pydantic's `int` field rejects outright rather than
    truncating (`ValidationError: int_from_float`) — this crashed the whole
    `/explore/search` response for every source, not just the offending
    one, since ExploreResultOut construction happens after all sources'
    results are merged (confirmed live). A pandas DataFrame cell (jobspy_source.py)
    has the same float-or-NaN shape for the same reason.

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


def strip_html(html: str) -> str:
    """Remove HTML tags from raw string content, preserving inner text.

    Args:
        html: Raw HTML string or None.

    Returns:
        str: Plain text with HTML tags replaced by spaces and excess whitespace trimmed.
    """
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def description_hash(description: str) -> str:
    """Compute deterministic SHA-256 hash of a normalized job description.

    Normalizes whitespace and converts text to lowercase before hashing, ensuring
    identical postings with minor spacing differences produce identical hashes
    for deduplication in the database.

    Args:
        description: Job description text.

    Returns:
        str: Hexadecimal SHA-256 digest string.
    """
    normalized = " ".join((description or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_location(raw_location: str) -> str:
    """Map free-text location strings onto canonical constraint names.

    Maps free-text location strings from job-board APIs onto the canonical
    names used in data/constraints.yaml's allowed_locations, so
    hard_filters can match on them directly. Anything unrecognized passes
    through unchanged — it will simply fail the location filter rather
    than silently matching something it shouldn't.

    Args:
        raw_location: Unformatted location string from API.

    Returns:
        str: Canonical location alias or trimmed original string.
    """
    lowered = (raw_location or "").lower()
    for keyword, canonical in LOCATION_ALIASES.items():
        if keyword in lowered:
            return canonical
    return (raw_location or "").strip()


def normalize_employment_type(raw_type: str | None) -> str | None:
    """Normalize raw employment type onto canonical allowed options.

    Args:
        raw_type: Raw commitment or job type string (e.g. 'fulltime', 'part-time').
            jobspy_source.py passes a pandas DataFrame cell straight through,
            which is `float('nan')`, not `None`, for a missing value — an
            `isinstance` check catches that (`not raw_type` alone doesn't:
            `bool(float('nan'))` is `True` in Python, so a bare NaN slips
            past that guard and crashes on `.strip()`).

    Returns:
        str | None: Canonical employment type (e.g. 'Full-time', 'Contract') or None.
    """
    if not isinstance(raw_type, str) or not raw_type.strip():
        return None
    return EMPLOYMENT_TYPE_ALIASES.get(raw_type.strip().lower(), raw_type.strip())


def matches_experience(haystack: str, experience: str) -> bool:
    """Case-insensitive substring match against a free-text experience-level filter.

    Shared by `jobspy_source.py` (haystack: a row's `job_level`/
    `experience_range` fields) and `targets.py` (haystack: a job's title +
    description, since Greenhouse/Lever expose no structured experience
    facet at all) — same "no query parameter for this, so filter app-side"
    shape, different haystack per source, previously implemented as two
    independent near-identical functions.

    Args:
        haystack: Source-specific text to search.
        experience: Free-text experience query (e.g. "senior", "3-5 years").

    Returns:
        bool: True if `experience` is blank, or appears in `haystack`
            case-insensitively.
    """
    needle = experience.strip().lower()
    if not needle:
        return True
    return needle in haystack.lower()


async def insert_jobs(session: AsyncSession, jobs: list[dict]) -> int:
    """Insert normalized jobs into the database, skipping duplicates.

    Inserts normalized jobs one at a time, skipping any whose
    description_hash already exists (relies on the UNIQUE constraint on
    Job.description_hash — see app/models/job.py). Each insert attempt runs
    in its own SAVEPOINT so one duplicate doesn't abort the rest of the
    batch. Returns the number of rows actually inserted (excluding
    duplicates).

    Args:
        session: Database session.
        jobs: List of normalized job dictionaries — keys must match Job's
            column names (source, source_job_id, company, title, location,
            url, description, description_hash, employment_type, posted_at,
            and optionally salary_min/salary_max).

    Returns:
        int: Number of new rows inserted.
    """
    if not jobs:
        return 0

    inserted = 0
    for job in jobs:
        posted_at = job.get("posted_at")
        if isinstance(posted_at, datetime) and posted_at.tzinfo is not None:
            # Job.posted_at is TIMESTAMP WITHOUT TIME ZONE (naive) — asyncpg
            # raises DataError (not IntegrityError, so uncaught below) on a
            # tz-aware value rather than silently dropping the offset.
            # Live bug (2026-09-19): every source that parses its own raw
            # date already produces a naive datetime, but a job posted back
            # through /explore/save round-trips through JSON, where pydantic
            # parses an ISO "...Z" string into a tz-aware UTC datetime —
            # this is the one path that needs normalizing.
            job = {**job, "posted_at": posted_at.replace(tzinfo=None)}
        try:
            async with session.begin_nested():
                session.add(Job(**job))
        except IntegrityError:
            continue
        inserted += 1

    await session.commit()
    return inserted
