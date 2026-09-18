"""Unit tests for domain-layer Pydantic models (app/schemas/domain.py).

app/schemas/database.py — a parallel set of Pydantic models mirroring
table columns 1:1 — was removed: app/models/ (real SQLAlchemy ORM
classes) is the single source of truth for table shape now, and nothing
in the application ever constructed those "database schema" models.
"""

from app.schemas import FilterResult, JobDetail, JobListItem


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
