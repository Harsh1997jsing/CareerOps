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


@dataclass
class JobListItem:
    job_id: int
    company: str
    title: str
    location: str
    url: str
    status: str
    fit_score: int | None
    confidence: str | None
    strong_matches: list
    missing_skills: list
    risks: list


@dataclass
class ApplicationItem:
    application_id: int
    job_id: int
    status: str
    applied_at: datetime | None


@dataclass
class GeneratedDocumentItem:
    id: int
    type: str
    file_path: str
    version: int
    claim_check_passed: bool | None
    ats_check_passed: bool | None


def _row_to_job_list_item(row: Mapping) -> JobListItem:
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
    return [_row_to_job_list_item(row) for row in _fetch_job_rows(engine, status)]


def _row_to_application_item(row: Mapping) -> ApplicationItem:
    return ApplicationItem(
        application_id=row["id"],
        job_id=row["job_id"],
        status=row["status"],
        applied_at=row["applied_at"],
    )


def get_application_for_job(engine: Engine, job_id: int) -> ApplicationItem | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, job_id, status, applied_at FROM applications WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).mappings().first()
    return _row_to_application_item(row) if row else None


def _row_to_generated_document_item(row: Mapping) -> GeneratedDocumentItem:
    return GeneratedDocumentItem(
        id=row["id"],
        type=row["type"],
        file_path=row["file_path"],
        version=row["version"],
        claim_check_passed=row["claim_check_passed"],
        ats_check_passed=row["ats_check_passed"],
    )


def list_generated_documents(engine: Engine, job_id: int) -> list[GeneratedDocumentItem]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, type, file_path, version, claim_check_passed, ats_check_passed "
                "FROM generated_documents WHERE job_id = :job_id ORDER BY type, version DESC"
            ),
            {"job_id": job_id},
        ).mappings().all()
    return [_row_to_generated_document_item(row) for row in rows]


def get_company_applied_dates(engine: Engine, company: str) -> list[datetime]:
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
    """Reuses hard_filters.check_company_cooldown so the dashboard's warning
    and the pre-scoring hard filter can never disagree about what's in cooldown."""
    applied_dates = get_company_applied_dates(engine, company)
    return check_company_cooldown(company, applied_dates, cooldown_days)


def set_application_status(engine: Engine, application_id: int, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET status = :status WHERE id = :application_id"),
            {"status": status, "application_id": application_id},
        )


def approve_application(engine: Engine, application_id: int) -> None:
    set_application_status(engine, application_id, APPROVED_STATUS)


def reject_application(engine: Engine, application_id: int) -> None:
    set_application_status(engine, application_id, REJECTED_STATUS)
