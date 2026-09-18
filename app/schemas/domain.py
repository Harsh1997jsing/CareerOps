"""Pydantic domain models for CareerOps business services and workflows.

Replaces raw dataclasses with validated Pydantic models supporting
attribute access, serialization, and database row mapping.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class Tenant(BaseModel):
    """Domain model representing a tenant organization."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_active: bool = True
    created_at: datetime | str | None = None


class User(BaseModel):
    """Domain model representing a user account."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    email: str
    role: str = "user"
    is_default_admin: bool = False
    is_active: bool = True
    created_at: datetime | str | None = None


class UserContext(BaseModel):
    """Authenticated user context extracted from JWT claims."""
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    tenant_id: int
    tenant_slug: str
    email: str
    role: str
    is_default_admin: bool = False


class ApplicationItem(BaseModel):
    """Application record associated with a job."""
    model_config = ConfigDict(from_attributes=True)

    application_id: int
    job_id: int
    status: str
    applied_at: datetime | str | None = None


class GeneratedDocumentItem(BaseModel):
    """Generated document item representing tailored resumes or cover letters."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    file_path: str
    version: int
    claim_check_passed: bool | None = None
    ats_check_passed: bool | None = None
    created_at: datetime | str | None = None


class JobListItem(BaseModel):
    """Summary of a job posting along with its latest fit analysis."""
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    company: str
    title: str
    location: str
    url: str
    status: str
    fit_score: int | None = None
    confidence: str | None = None
    strong_matches: list[Any] = Field(default_factory=list)
    missing_skills: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)


class JobDetail(JobListItem):
    """Complete detail of a job, including full description and linked application."""
    description: str
    application: ApplicationItem | None = None


class ApplicationContext(BaseModel):
    """Minimal context needed to open a job URL or record manual submission."""
    model_config = ConfigDict(from_attributes=True)

    application_id: int
    job_id: int
    company: str
    url: str


class FilterResult(BaseModel):
    """Outcome of evaluating deterministic filter rules against a job posting."""
    model_config = ConfigDict(from_attributes=True)

    passed: bool
    reasons: list[str] = Field(default_factory=list)
