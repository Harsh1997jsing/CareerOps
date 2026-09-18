"""
Shared helpers for job-board source adapters: HTML stripping, location/
employment-type normalization onto the vocabulary hard_filters.py and
data/constraints.yaml expect, the description hash used for
jobs.description_hash dedupe, and the shared insert that skips anything
already collected.
"""

import hashlib
import re

from sqlalchemy import text
from sqlalchemy.engine import Engine

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

    Returns:
        str | None: Canonical employment type (e.g. 'Full-time', 'Contract') or None.
    """
    if not raw_type:
        return None
    return EMPLOYMENT_TYPE_ALIASES.get(raw_type.strip().lower(), raw_type.strip())


def insert_jobs(engine: Engine, jobs: list[dict]) -> int:
    """Insert normalized jobs into the database, skipping duplicates.

    Inserts normalized jobs one at a time, skipping any whose
    description_hash already exists (relies on the UNIQUE constraint on
    jobs.description_hash in schema.sql). Returns the number of rows
    actually inserted (i.e. excluding duplicates).

    Args:
        engine: Database engine instance.
        jobs: List of normalized job dictionaries.

    Returns:
        int: Number of new rows inserted.
    """
    if not jobs:
        return 0

    inserted = 0
    with engine.begin() as conn:
        for job in jobs:
            result = conn.execute(
                text(
                    "INSERT INTO jobs (source, source_job_id, company, title, location, url, "
                    "description, description_hash, employment_type, posted_at) "
                    "VALUES (:source, :source_job_id, :company, :title, :location, :url, "
                    ":description, :description_hash, :employment_type, :posted_at) "
                    "ON CONFLICT (description_hash) DO NOTHING"
                ),
                job,
            )
            inserted += result.rowcount
    return inserted
