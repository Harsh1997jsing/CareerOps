"""
Shared pytest fixtures. `db_session` gives DB-touching tests a real,
fast SQLite-in-memory async session with every table created — used
instead of hand-mocked Session/Connection objects wherever code queries
through the ORM (app/models/). Mocking a query-builder chain by hand is
brittle and doesn't actually verify the SQL is correct; a real (if
disposable) database does.

`JWT_SECRET_KEY`/`DEFAULT_ADMIN_PASSWORD` are required Settings fields
(app/core/config.py) with no code-level default on purpose — but that
means importing app.core.config (transitively, almost everything) raises
without them set. These are throwaway values for the test run only;
setdefault() so a real .env/environment value, if present, still wins.
Set here, at conftest module level, so they exist before any test module
is imported, not inside a fixture (which runs too late).
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "pytest-only-jwt-secret-not-for-real-use")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "pytest-only-admin-password")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Job
from app.schemas import UserContext

# A stand-in authenticated user for route tests that override
# get_current_user rather than exercising the real login flow (those live
# in test_api_auth.py). Every route under jobs.py/applications.py/
# explore.py now requires auth (audit finding F1); tests that mock the
# service layer anyway don't need a real JWT, just a resolved dependency.
FAKE_USER_CONTEXT = UserContext(
    user_id=1, tenant_id=1, tenant_slug="default", email="test@example.local", role="admin",
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def make_job(session: AsyncSession, job_id: int = 1, status: str = "READY_FOR_REVIEW", **overrides) -> Job:
    """Shared fixture helper for tests/test_jobs.py and tests/test_applications.py."""
    defaults = dict(
        id=job_id, source="greenhouse", company="Acme", title="Backend Engineer",
        location="Remote", url="https://example.com/job/1",
        description="Build things with Python.", status=status,
    )
    job = Job(**{**defaults, **overrides})
    session.add(job)
    await session.commit()
    return job
