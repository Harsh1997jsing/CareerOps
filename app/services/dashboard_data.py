"""
DB access for the dashboard, kept separate from app/dashboard.py so the
query and row-mapping logic can be unit tested without a live Postgres
instance or a running Streamlit session.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.hard_filters import FilterResult, check_company_cooldown

APPROVED_STATUS = "APPROVED"
REJECTED_STATUS = "REJECTED"


from app.schemas import (
    ApplicationContext,
    ApplicationItem,
    GeneratedDocumentItem,
    JobDetail,
    JobListItem,
)

__all__ = [
    "APPROVED_STATUS",
    "REJECTED_STATUS",
    "JobListItem",
    "ApplicationItem",
    "GeneratedDocumentItem",
    "JobDetail",
    "ApplicationContext",
    "list_jobs",
    "get_job",
    "list_generated_documents",
    "approve_application",
    "reject_application",
    "get_application_context",
    "get_application_for_job",
    "check_cooldown_for_company",
    "get_company_applied_dates",
]


def _row_to_job_list_item(row: Mapping) -> JobListItem:
    """Map a database row mapping onto a JobListItem instance.

    Args:
        row: Database row mapping containing job and latest analysis columns.

    Returns:
        JobListItem: Instantiated dataclass with defaulted empty lists for match fields.
    """
    return JobListItem(
        job_id=row["id"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        url=row["url"],
        status=row["status"],
        fit_score=row["fit_score"],
        confidence=row["confidence"],
        strong_matches=row["strong_matches"] or [],
        missing_skills=row["missing_skills"] or [],
        risks=row["risks"] or [],
    )


def _fetch_job_rows(engine: Engine, status: str | None):
    """Execute query joining jobs to their latest analysis record.

    Args:
        engine: Database engine.
        status: Optional status to filter by.

    Returns:
        list[Mapping]: Database rows as dictionary-like mappings.
    """
    query = """
        SELECT j.id, j.company, j.title, j.location, j.url, j.status,
               a.fit_score, a.confidence, a.strong_matches, a.missing_skills, a.risks
        FROM jobs j
        LEFT JOIN LATERAL (
            SELECT * FROM job_analysis
            WHERE job_id = j.id
            ORDER BY analyzed_at DESC
            LIMIT 1
        ) a ON true
        {where}
        ORDER BY j.collected_at DESC
    """
    where_clause = "WHERE j.status = :status" if status else ""
    params = {"status": status} if status else {}

    with engine.connect() as conn:
        rows = conn.execute(text(query.format(where=where_clause)), params).mappings().all()
    return rows


def list_jobs(engine: Engine, status: str | None = None) -> list[JobListItem]:
    """List jobs with their latest analysis results, optionally filtered by status.

    Args:
        engine: SQLAlchemy Engine for database access.
        status: Status filter string (e.g. 'READY_FOR_REVIEW', 'APPROVED'), or None for all.

    Returns:
        list[JobListItem]: List of matching job summary items.
    """
    return [_row_to_job_list_item(row) for row in _fetch_job_rows(engine, status)]


def _fetch_job_row(engine: Engine, job_id: int):
    """Fetch raw database row mapping for a specific job and its latest analysis.

    Args:
        engine: Database engine.
        job_id: Job primary key.

    Returns:
        Mapping | None: Database row mapping or None if not found.
    """
    query = """
        SELECT j.id, j.company, j.title, j.location, j.url, j.description, j.status,
               a.fit_score, a.confidence, a.strong_matches, a.missing_skills, a.risks
        FROM jobs j
        LEFT JOIN LATERAL (
            SELECT * FROM job_analysis
            WHERE job_id = j.id
            ORDER BY analyzed_at DESC
            LIMIT 1
        ) a ON true
        WHERE j.id = :job_id
    """
    with engine.connect() as conn:
        return conn.execute(text(query), {"job_id": job_id}).mappings().first()


def get_job(engine: Engine, job_id: int) -> JobDetail | None:
    """Retrieve detailed information for a single job by its ID.

    Single-job detail for GET /jobs/{id} — list_jobs() intentionally omits
    `description` to keep the list query light, so this is a separate
    query rather than list_jobs() filtered down to one row.

    Args:
        engine: SQLAlchemy Engine for database access.
        job_id: Primary key of the requested job.

    Returns:
        JobDetail | None: Complete job details with full description and application status,
            or None if not found.
    """
    row = _fetch_job_row(engine, job_id)
    if row is None:
        return None

    return JobDetail(
        job_id=row["id"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        url=row["url"],
        description=row["description"],
        status=row["status"],
        fit_score=row["fit_score"],
        confidence=row["confidence"],
        strong_matches=row["strong_matches"] or [],
        missing_skills=row["missing_skills"] or [],
        risks=row["risks"] or [],
        application=get_application_for_job(engine, row["id"]),
    )


def _row_to_application_item(row: Mapping) -> ApplicationItem:
    """Map an applications database row mapping onto an ApplicationItem instance.

    Args:
        row: Database row mapping from the applications table.

    Returns:
        ApplicationItem: Mapped application item.
    """
    return ApplicationItem(
        application_id=row["id"],
        job_id=row["job_id"],
        status=row["status"],
        applied_at=row["applied_at"],
    )


def get_application_for_job(engine: Engine, job_id: int) -> ApplicationItem | None:
    """Retrieve the application record linked to a given job, if one exists.

    Args:
        engine: Database engine.
        job_id: Primary key of the job.

    Returns:
        ApplicationItem | None: Linked application record, or None if not yet created.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, job_id, status, applied_at FROM applications WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).mappings().first()
    return _row_to_application_item(row) if row else None


def _row_to_generated_document_item(row: Mapping) -> GeneratedDocumentItem:
    """Map a generated_documents database row mapping onto a GeneratedDocumentItem instance.

    Args:
        row: Database row mapping from the generated_documents table.

    Returns:
        GeneratedDocumentItem: Mapped document metadata item.
    """
    return GeneratedDocumentItem(
        id=row["id"],
        type=row["type"],
        file_path=row["file_path"],
        version=row["version"],
        claim_check_passed=row["claim_check_passed"],
        ats_check_passed=row["ats_check_passed"],
    )


def list_generated_documents(engine: Engine, job_id: int) -> list[GeneratedDocumentItem]:
    """List all generated documents for a specific job ordered by type and version descending.

    Args:
        engine: Database engine.
        job_id: Primary key of the job.

    Returns:
        list[GeneratedDocumentItem]: List of generated documents for the job.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, type, file_path, version, claim_check_passed, ats_check_passed "
                "FROM generated_documents WHERE job_id = :job_id ORDER BY type, version DESC"
            ),
            {"job_id": job_id},
        ).mappings().all()
    return [_row_to_generated_document_item(row) for row in rows]


def get_application_context(engine: Engine, application_id: int) -> ApplicationContext | None:
    """Lookup the job details (company, url) associated with an application ID.

    Looks up the job (company, url) behind an application_id — approve()/
    reject() only need the id itself, but open()/mark-applied() need the
    job's url/company too, and the API is keyed by application_id (unlike
    get_application_for_job(), which is keyed by job_id).

    Args:
        engine: Database engine.
        application_id: Primary key of the application.

    Returns:
        ApplicationContext | None: Context containing application ID, job ID, company,
            and URL, or None if not found.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT a.id AS application_id, a.job_id, j.company, j.url "
                "FROM applications a JOIN jobs j ON j.id = a.job_id "
                "WHERE a.id = :application_id"
            ),
            {"application_id": application_id},
        ).mappings().first()

    if row is None:
        return None

    return ApplicationContext(
        application_id=row["application_id"],
        job_id=row["job_id"],
        company=row["company"],
        url=row["url"],
    )


def get_company_applied_dates(engine: Engine, company: str) -> list[datetime]:
    """Retrieve historical application submission dates for a given company.

    Args:
        engine: Database engine.
        company: Company name to query.

    Returns:
        list[datetime]: Past application timestamps for the company.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT applied_at FROM company_application_history "
                "WHERE company = :company AND applied_at IS NOT NULL"
            ),
            {"company": company},
        ).scalars().all()
    return list(rows)


def check_cooldown_for_company(engine: Engine, company: str, cooldown_days: int) -> FilterResult:
    """Evaluate whether an application to a company is barred by a cooldown policy.

    Reuses hard_filters.check_company_cooldown so the dashboard's warning
    and the pre-scoring hard filter can never disagree about what's in cooldown.

    Args:
        engine: Database engine.
        company: Company name.
        cooldown_days: Required cooldown duration in days.

    Returns:
        FilterResult: Pass/fail outcome and explanation of remaining cooldown days.
    """
    applied_dates = get_company_applied_dates(engine, company)
    return check_company_cooldown(company, applied_dates, cooldown_days)


def set_application_status(engine: Engine, application_id: int, status: str) -> None:
    """Update the status of an application in the database.

    Args:
        engine: Database engine.
        application_id: Application primary key.
        status: New status string (e.g. 'APPROVED', 'REJECTED').
    """
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET status = :status WHERE id = :application_id"),
            {"status": status, "application_id": application_id},
        )


def approve_application(engine: Engine, application_id: int) -> None:
    """Mark an application as APPROVED.

    Args:
        engine: Database engine.
        application_id: Application primary key.
    """
    set_application_status(engine, application_id, APPROVED_STATUS)


def reject_application(engine: Engine, application_id: int) -> None:
    """Mark an application as REJECTED.

    Args:
        engine: Database engine.
        application_id: Application primary key.
    """
    set_application_status(engine, application_id, REJECTED_STATUS)
