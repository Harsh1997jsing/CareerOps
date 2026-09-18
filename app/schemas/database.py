"""Pydantic schemas corresponding to every database table in CareerOps.

Provides strongly-typed, validated Pydantic models for:
- tenants
- users
- jobs
- job_analysis
- evidence
- generated_documents
- applications
- company_application_history
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# 1. Tenants Table Schema
# -----------------------------------------------------------------------------
class TenantBase(BaseModel):
    """Base attributes for a tenant organization."""
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Organization display name")
    slug: str = Field(..., description="Unique URL slug")
    is_active: bool = Field(default=True, description="Whether the organization is active")


class TenantCreate(TenantBase):
    """Payload to create a new tenant."""
    pass


class TenantInDB(TenantBase):
    """Full database representation of a tenant row."""
    id: int
    created_at: datetime | str | None = None


TenantSchema = TenantInDB


# -----------------------------------------------------------------------------
# 2. Users Table Schema
# -----------------------------------------------------------------------------
class UserBase(BaseModel):
    """Base attributes for a user account."""
    model_config = ConfigDict(from_attributes=True)

    tenant_id: int
    email: str
    role: str = Field(default="user", description="Account role ('user' or 'admin')")
    is_default_admin: bool = Field(default=False, description="Whether account is immutable default admin")
    is_active: bool = Field(default=True, description="Whether user account is enabled")


class UserCreate(BaseModel):
    """Payload to provision a new user."""
    model_config = ConfigDict(from_attributes=True)

    tenant_id: int
    email: str
    password: str
    role: str = "user"


class UserInDB(UserBase):
    """Full database representation of a user row including hashed password."""
    id: int
    hashed_password: str
    created_at: datetime | str | None = None


class UserSchema(UserBase):
    """Public user record without password hash."""
    id: int
    created_at: datetime | str | None = None


# -----------------------------------------------------------------------------
# 3. Jobs Table Schema
# -----------------------------------------------------------------------------
class JobBase(BaseModel):
    """Base attributes for a job posting."""
    model_config = ConfigDict(from_attributes=True)

    source: str = Field(..., description="Source platform (e.g. 'greenhouse', 'lever', 'jobo')")
    source_job_id: str | None = None
    company: str
    title: str
    location: str | None = None
    url: str
    description: str
    description_hash: str | None = None
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    status: str = Field(default="DISCOVERED", description="Job processing status")


class JobCreate(JobBase):
    """Payload to insert a new job posting."""
    posted_at: datetime | str | None = None


class JobInDB(JobBase):
    """Full database representation of a job row."""
    id: int
    posted_at: datetime | str | None = None
    collected_at: datetime | str | None = None


JobSchema = JobInDB


# -----------------------------------------------------------------------------
# 4. Job Analysis Table Schema
# -----------------------------------------------------------------------------
class JobAnalysisBase(BaseModel):
    """Base attributes for LLM job fit analysis."""
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    fit_score: int | None = Field(default=None, ge=0, le=100)
    confidence: str | None = None
    eligible: bool | None = None
    strong_matches: list[Any] = Field(default_factory=list)
    missing_skills: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)


class JobAnalysisCreate(JobAnalysisBase):
    """Payload to insert job fit analysis."""
    pass


class JobAnalysisInDB(JobAnalysisBase):
    """Full database representation of a job analysis row."""
    id: int
    analyzed_at: datetime | str | None = None


JobAnalysisSchema = JobAnalysisInDB


# -----------------------------------------------------------------------------
# 5. Evidence Table Schema
# -----------------------------------------------------------------------------
class EvidenceBase(BaseModel):
    """Base attributes for a candidate qualification evidence item."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique alphanumeric identifier (e.g. 'EV-001')")
    claim: str = Field(..., description="Factual experience claim")
    category: str | None = None
    source: str | None = None
    verified: bool = Field(default=True, description="Whether claim has been verified")


class EvidenceCreate(EvidenceBase):
    """Payload to insert an evidence record."""
    pass


class EvidenceInDB(EvidenceBase):
    """Full database representation of an evidence row."""
    pass


EvidenceSchema = EvidenceInDB


# -----------------------------------------------------------------------------
# 6. Generated Documents Table Schema
# -----------------------------------------------------------------------------
class GeneratedDocumentBase(BaseModel):
    """Base attributes for a generated tailored resume or cover letter."""
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    type: str | None = Field(default=None, description="'resume' or 'cover_letter'")
    file_path: str | None = None
    version: int = Field(default=1)
    claim_check_passed: bool | None = None
    ats_check_passed: bool | None = None


class GeneratedDocumentCreate(GeneratedDocumentBase):
    """Payload to record a generated document."""
    pass


class GeneratedDocumentInDB(GeneratedDocumentBase):
    """Full database representation of a generated document row."""
    id: int
    created_at: datetime | str | None = None


GeneratedDocumentSchema = GeneratedDocumentInDB


# -----------------------------------------------------------------------------
# 7. Applications Table Schema
# -----------------------------------------------------------------------------
class ApplicationBase(BaseModel):
    """Base attributes for an application workflow record."""
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    status: str = Field(default="READY_FOR_REVIEW")
    applied_at: datetime | str | None = None
    resume_version: int | None = None
    cover_letter_version: int | None = None
    notes: str | None = None


class ApplicationCreate(ApplicationBase):
    """Payload to create an application."""
    pass


class ApplicationInDB(ApplicationBase):
    """Full database representation of an application row."""
    id: int


ApplicationSchema = ApplicationInDB


# -----------------------------------------------------------------------------
# 8. Company Application History Table Schema
# -----------------------------------------------------------------------------
class CompanyApplicationHistoryBase(BaseModel):
    """Base attributes for company cooldown tracking."""
    model_config = ConfigDict(from_attributes=True)

    company: str
    job_id: int
    applied_at: datetime | str | None = None


class CompanyApplicationHistoryCreate(CompanyApplicationHistoryBase):
    """Payload to record company application submission."""
    pass


class CompanyApplicationHistoryInDB(CompanyApplicationHistoryBase):
    """Full database representation of company application history."""
    id: int


CompanyApplicationHistorySchema = CompanyApplicationHistoryInDB
