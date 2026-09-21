"""
Manual company targeting: loads data/companies.yaml and pulls jobs for
each configured Greenhouse board / Lever company via the existing
adapters. This is the "manually company target" source path — distinct
from app/sources/jobspy_source.py (multi-site scrape) and the MCP explore
connectors under app/sources/mcp/. See CLAUDE.md rule 2.
"""

import asyncio
import logging

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.sources import greenhouse, lever
from app.sources.common import insert_jobs

COMPANIES_PATH = "data/companies.yaml"

logger = logging.getLogger(__name__)


def load_company_targets(path: str = COMPANIES_PATH) -> dict:
    """Load targeted Greenhouse and Lever company configurations from a YAML file.

    Args:
        path: Path to companies YAML file (defaults to `data/companies.yaml`).

    Returns:
        dict: Parsed dictionary containing lists under 'greenhouse' and 'lever' keys.
    """
    with open(path) as f:
        return yaml.safe_load(f) or {}


def fetch_all_targets(path: str = COMPANIES_PATH) -> list[dict]:
    """Fetch postings for all companies configured in the targets file.

    Fetches jobs for every configured target. One target failing (bad
    board token, network error) is logged and skipped rather than
    aborting the rest of the batch.

    Args:
        path: Filepath to company targets YAML configuration.

    Returns:
        list[dict]: Combined list of normalized jobs from all reachable targets.
    """
    targets = load_company_targets(path)
    jobs: list[dict] = []

    for entry in targets.get("greenhouse") or []:
        try:
            jobs.extend(greenhouse.fetch_jobs(entry["board_token"], entry["company"]))
        except Exception:
            logger.exception("greenhouse target failed: %s", entry.get("company"))

    for entry in targets.get("lever") or []:
        try:
            jobs.extend(lever.fetch_jobs(entry["company_slug"], entry["company"]))
        except Exception:
            logger.exception("lever target failed: %s", entry.get("company"))

    return jobs


def _matches_experience(job: dict, experience: str) -> bool:
    """Check a normalized target job's title/description against an experience query.

    Greenhouse's and Lever's public job-board APIs have no standardized
    experience/seniority facet (unlike jobspy's job_level/experience_range
    output fields), so there's no structured field to match here at all —
    this is a plain keyword heuristic against the text every posting does
    have, matching e.g. "senior" against a title like "Senior Backend
    Engineer".

    Args:
        job: Normalized job dict (from greenhouse.fetch_jobs/lever.fetch_jobs).
        experience: Free-text experience query (e.g. "senior", "entry level").

    Returns:
        bool: True if `experience` appears as a case-insensitive substring
            of the job's title or description.
    """
    needle = experience.strip().lower()
    if not needle:
        return True
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return needle in haystack


async def search_all(path: str = COMPANIES_PATH, experience: str | None = None) -> list[dict]:
    """Fetch postings from every configured company target without saving them.

    Backs `POST /targets/search` — the Dashboard shows these to the user
    first and only inserts the ones they explicitly pick (via
    `/explore/save`, shared across every discovery source). Same
    thread-offload reasoning as `ingest_all()` below, minus the DB write.

    Args:
        path: Filepath to company targets configuration.
        experience: Optional free-text experience-level filter, applied
            app-side via _matches_experience since neither board API
            exposes a structured experience facet to filter on upstream.

    Returns:
        list[dict]: Normalized jobs, not yet persisted.
    """
    jobs = await asyncio.to_thread(fetch_all_targets, path)
    if experience:
        jobs = [job for job in jobs if _matches_experience(job, experience)]
    return jobs


async def ingest_all(session: AsyncSession, path: str = COMPANIES_PATH) -> int:
    """Fetch postings from all configured company targets and persist them to the database.

    Auto-inserts everything found, no per-job review — not what
    `POST /targets/search` uses (see `search_all()` above; the Dashboard's
    search-then-select-then-save flow needs the un-inserted list). Kept as
    a standalone fetch-and-insert utility for scripted/REPL use, same
    convenience role as `applications_service.set_application_status()`.
    Returns the number of rows actually inserted (excludes duplicates
    already collected). Fetching itself (greenhouse/lever's blocking
    `requests` calls) runs in a worker thread via `asyncio.to_thread` so a
    slow board API doesn't stall the event loop for every other request;
    the DB write stays on the calling task, same as before.

    Args:
        session: Database session.
        path: Filepath to company targets configuration.

    Returns:
        int: Number of new jobs inserted.
    """
    jobs = await asyncio.to_thread(fetch_all_targets, path)
    return await insert_jobs(session, jobs)
