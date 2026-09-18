"""
Manual company targeting: loads data/companies.yaml and pulls jobs for
each configured Greenhouse board / Lever company via the existing
adapters. This is the "manually company target" source path — distinct
from app/sources/jobspy_source.py (multi-site scrape) and the MCP explore
connectors under app/sources/mcp/. See CLAUDE.md rule 2.
"""

import logging

import yaml
from sqlalchemy.engine import Engine

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


def ingest_all(engine: Engine, path: str = COMPANIES_PATH) -> int:
    """Fetch postings from all configured company targets and persist them to the database.

    Fetches every configured target and inserts new postings into `jobs`.
    Returns the number of rows actually inserted (excludes duplicates
    already collected).

    Args:
        engine: Database engine.
        path: Filepath to company targets configuration.

    Returns:
        int: Number of new jobs inserted.
    """
    jobs = fetch_all_targets(path)
    return insert_jobs(engine, jobs)
