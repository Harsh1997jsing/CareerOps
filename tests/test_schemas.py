"""Unit tests for Pydantic database schemas and domain models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    ApplicationContext,
    ApplicationCreate,
    ApplicationInDB,
    ApplicationItem,
    ApplicationSchema,
    CompanyApplicationHistoryCreate,
    CompanyApplicationHistoryInDB,
    CompanyApplicationHistorySchema,
    EvidenceCreate,
    EvidenceInDB,
    EvidenceSchema,
    FilterResult,
    GeneratedDocumentCreate,
    GeneratedDocumentInDB,
    GeneratedDocumentItem,
    GeneratedDocumentSchema,
    JobAnalysisCreate,
    JobAnalysisInDB,
    JobAnalysisSchema,
    JobCreate,
    JobDetail,
    JobInDB,
    JobListItem,
    JobSchema,
    Tenant,
    TenantCreate,
    TenantInDB,
    TenantSchema,
    User,
    UserContext,
    UserCreate,
    UserInDB,
    UserSchema,
)


def test_tenant_schemas():
    """Verify tenant database and domain schemas validate accurately."""
    t_create = TenantCreate(name="Acme Corp", slug="acme")
    assert t_create.name == "Acme Corp"
    assert t_create.slug == "acme"
    assert t_create.is_active is True

    t_db = TenantInDB(id=1, name="Acme Corp", slug="acme", created_at=datetime.now())
    assert t_db.id == 1

    # Domain model
    t_domain = Tenant(id=1, name="Acme Corp", slug="acme")
    assert t_domain.id == 1
    assert t_domain.slug == "acme"


def test_user_schemas():
    """Verify user database and domain schemas validate and handle password hashes."""
    u_create = UserCreate(tenant_id=1, email="test@example.com", password="secretpassword")
    assert u_create.email == "test@example.com"
    assert u_create.role == "user"

    u_db = UserInDB(
        id=1,
        tenant_id=1,
        email="test@example.com",
        hashed_password="salt$iter$hash",
        role="admin",
        is_default_admin=True,
    )
    assert u_db.id == 1
    assert u_db.is_default_admin is True

    # UserSchema without password
    u_schema = UserSchema(id=1, tenant_id=1, email="test@example.com", role="admin")
    assert u_schema.email == "test@example.com"
    assert not hasattr(u_schema, "hashed_password")


def test_job_schemas():
    """Verify job table schemas validate correctly."""
    job_create = JobCreate(
        source="greenhouse",
        company="TechCorp",
        title="Staff Engineer",
        url="https://example.com/job/1",
        description="Write clean code",
        location="Remote",
    )
    assert job_create.source == "greenhouse"
    assert job_create.status == "DISCOVERED"

    job_db = JobInDB(
        id=10,
        source="greenhouse",
        company="TechCorp",
        title="Staff Engineer",
        url="https://example.com/job/1",
        description="Write clean code",
    )
    assert job_db.id == 10
    assert job_db.company == "TechCorp"


def test_job_analysis_schemas():
    """Verify job analysis schemas validate fit score boundaries."""
    analysis = JobAnalysisInDB(
        id=1,
        job_id=10,
        fit_score=95,
        confidence="high",
        eligible=True,
        strong_matches=["Python", "FastAPI"],
        missing_skills=[],
        risks=[],
    )
    assert analysis.fit_score == 95
    assert len(analysis.strong_matches) == 2

    # Fit score must be between 0 and 100
    with pytest.raises(ValidationError):
        JobAnalysisInDB(id=1, job_id=10, fit_score=150)


def test_evidence_and_document_schemas():
    """Verify evidence and generated document schemas validate correctly."""
    ev = EvidenceSchema(id="EV-001", claim="10 years backend experience", verified=True)
    assert ev.id == "EV-001"
    assert ev.verified is True

    doc = GeneratedDocumentInDB(
        id=5,
        job_id=10,
        type="resume",
        file_path="/output/resume_v1.docx",
        version=1,
        claim_check_passed=True,
        ats_check_passed=True,
    )
    assert doc.id == 5
    assert doc.claim_check_passed is True


def test_application_and_history_schemas():
    """Verify application and company application history schemas."""
    app = ApplicationInDB(id=1, job_id=10, status="READY_FOR_REVIEW")
    assert app.id == 1
    assert app.status == "READY_FOR_REVIEW"

    history = CompanyApplicationHistoryInDB(id=1, company="TechCorp", job_id=10)
    assert history.company == "TechCorp"
    assert history.job_id == 10


def test_domain_models():
    """Verify domain models support attribute access and conversion."""
    item = JobListItem(
        job_id=1,
        company="Google",
        title="Software Engineer",
        location="Mountain View, CA",
        url="https://careers.google.com/jobs/1",
        status="DISCOVERED",
    )
    assert item.company == "Google"
    assert item.strong_matches == []

    detail = JobDetail(
        **item.model_dump(),
        description="Build great search software.",
    )
    assert detail.description == "Build great search software."
    assert detail.company == "Google"

    # FilterResult
    res = FilterResult(passed=True, reasons=[])
    assert res.passed is True
