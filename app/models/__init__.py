"""SQLAlchemy ORM models — the single source of truth for every table's
shape. `schema.sql` and app/core/database.py's old hand-written DDL are
superseded by this + Alembic (migrations/); see migrations/README or
CLAUDE.md's Architecture section.
"""

from app.models.application import Application, CompanyApplicationHistory
from app.models.base import Base
from app.models.chat_search import ChatSearchResult
from app.models.document import GeneratedDocument
from app.models.evidence import Evidence
from app.models.job import Job, JobAnalysis
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "Base",
    "Tenant",
    "User",
    "Job",
    "JobAnalysis",
    "Evidence",
    "GeneratedDocument",
    "Application",
    "CompanyApplicationHistory",
    "ChatSearchResult",
]
