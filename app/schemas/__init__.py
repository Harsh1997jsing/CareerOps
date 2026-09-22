"""Domain-layer Pydantic models for CareerOps services (app/schemas/domain.py).

Deliberately does not re-export app/api/schemas.py's HTTP wire models —
routes import those directly from app.api.schemas. Doing it the other way
(as this module briefly did) makes the domain layer depend on the HTTP
layer, backwards from how the dependency should point; routes already
import both this package and app.api.schemas separately, so nothing
needs the two funneled through one barrel import.

app/schemas/database.py — a set of Pydantic models mirroring table
columns 1:1 — was removed: app/models/ (real SQLAlchemy ORM classes) is
the single source of truth for table shape now.
"""

from app.schemas.domain import (
    ApplicationContext,
    ApplicationItem,
    FilterResult,
    GeneratedDocumentItem,
    JobDetail,
    JobListItem,
    UserContext,
)

__all__ = [
    "UserContext",
    "ApplicationItem",
    "GeneratedDocumentItem",
    "JobListItem",
    "JobDetail",
    "ApplicationContext",
    "FilterResult",
]
