"""Unit tests for app/api/dependencies.py's get_current_user()."""

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.core.security import create_access_token
from app.services.auth import DEFAULT_TENANT_SLUG, get_tenant_by_slug, init_auth_db


@pytest.fixture
async def auth_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session = async_sessionmaker(bind=engine, expire_on_commit=False)()
    await init_auth_db(session)
    yield session
    await session.close()
    await engine.dispose()


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_get_current_user_re_reads_tenant_slug_from_the_db_not_the_jwt(auth_session):
    # Full code audit finding: tenant_slug used to be read straight from
    # the JWT payload while every other UserContext field was re-read
    # fresh from the DB — a tenant renamed after the token was issued
    # would leave this one field stale for up to the token's full
    # lifetime. Simulates that by embedding a deliberately wrong slug in
    # the token's own claims; the DB's real, current slug must win.
    session = auth_session
    tenant = await get_tenant_by_slug(session, DEFAULT_TENANT_SLUG)

    token = create_access_token({
        "sub": "1",
        "tenant_id": tenant.id,
        "tenant_slug": "stale-slug-from-before-a-rename",
        "email": "admin@careerops.local",
        "role": "admin",
        "is_default_admin": True,
    })

    context = await get_current_user(auth=_bearer(token), session=session)

    assert context.tenant_slug == DEFAULT_TENANT_SLUG
    assert context.tenant_slug != "stale-slug-from-before-a-rename"
