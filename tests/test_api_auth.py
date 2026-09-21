"""Integration and route tests for multi-tenant stateless JWT auth API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.api.main import app
from app.core import get_db, rate_limit
from app.services.auth import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    create_user,
    init_auth_db,
)


@pytest.fixture
async def auth_client():
    """Create a TestClient with an isolated in-memory SQLite database for authentication testing.

    These tests exercise the *real* get_current_user (unauthenticated ->
    401, non-admin -> 403), so this fixture must guarantee no stray
    override from another test module survives here — app.dependency_
    overrides is a plain dict on the one shared `app` singleton, and other
    test files (test_api_jobs.py etc.) set `get_current_user` at module
    level without ever clearing it, so without this it silently leaks
    across test files depending on collection/import order.

    Also resets app.core.rate_limit's module-global bucket state — same
    class of cross-test pollution: TestClient always reports the same
    client host ("testclient"), so a rate-limit test that deliberately
    trips the 429 for DEFAULT_ADMIN_EMAIL would otherwise lock every later
    test's login attempts for the rest of the pytest session.
    """
    rate_limit.reset_all_for_tests()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    await init_auth_db(session_factory())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_user_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)

    yield client, session_factory

    if previous_db_override is not None:
        app.dependency_overrides[get_db] = previous_db_override
    else:
        app.dependency_overrides.pop(get_db, None)
    if previous_user_override is not None:
        app.dependency_overrides[get_current_user] = previous_user_override
    await engine.dispose()


def _login_as(client: TestClient, email: str, password: str, tenant_slug: str = "default") -> str:
    """Helper to login and obtain bearer token."""
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


async def test_login_success(auth_client):
    """Verify login with valid credentials returns a valid stateless JWT access token."""
    client, _ = auth_client
    response = client.post(
        "/auth/login",
        json={
            "email": DEFAULT_ADMIN_EMAIL,
            "password": DEFAULT_ADMIN_PASSWORD,
            "tenant_slug": "default",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    assert data["email"] == DEFAULT_ADMIN_EMAIL
    assert data["tenant_slug"] == "default"


async def test_login_rate_limited_after_five_failures(auth_client):
    """Audit finding F6: /auth/login had no rate limiting at all."""
    client, _ = auth_client
    bad_login = {"email": DEFAULT_ADMIN_EMAIL, "password": "wrong", "tenant_slug": "default"}

    for _ in range(5):
        response = client.post("/auth/login", json=bad_login)
        assert response.status_code == 401

    limited_response = client.post("/auth/login", json=bad_login)
    assert limited_response.status_code == 429

    # A correct password is still blocked while rate-limited — the limit
    # is on attempts, not on failures specifically.
    good_login = {"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD, "tenant_slug": "default"}
    assert client.post("/auth/login", json=good_login).status_code == 429


async def test_login_invalid_credentials(auth_client):
    """Verify login with invalid password returns 401 Unauthorized."""
    client, _ = auth_client
    response = client.post(
        "/auth/login",
        json={
            "email": DEFAULT_ADMIN_EMAIL,
            "password": "wrong_password_here",
            "tenant_slug": "default",
        },
    )
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


async def test_get_me_authenticated(auth_client):
    """Verify /auth/me returns the profile for a user with a valid bearer token."""
    client, _ = auth_client
    token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == DEFAULT_ADMIN_EMAIL
    assert data["role"] == "admin"
    assert data["is_default_admin"] is True


async def test_get_me_unauthenticated(auth_client):
    """Verify /auth/me returns 401 when no token is provided."""
    client, _ = auth_client
    response = client.get("/auth/me")
    assert response.status_code == 401


async def test_admin_can_create_user(auth_client):
    """Verify an admin can provision a new user within their tenant."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.post(
        "/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": "newdev@careerops.local", "password": "password123", "role": "user"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newdev@careerops.local"
    assert data["role"] == "user"
    assert data["is_default_admin"] is False


async def test_create_user_rejects_short_password(auth_client):
    """Audit finding F7: password had no length validation at all."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.post(
        "/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": "weak@careerops.local", "password": "short", "role": "user"},
    )
    assert response.status_code == 422


async def test_create_tenant_rejects_malformed_slug(auth_client):
    """Audit finding F7: slug had no format validation — spaces/uppercase/
    punctuation were accepted and merely lowercased, never rejected."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.post(
        "/auth/tenants",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Bad Corp", "slug": "Not A Valid Slug!"},
    )
    assert response.status_code == 422


async def test_non_admin_cannot_create_user(auth_client):
    """Verify a regular non-admin user cannot provision users (403 Forbidden)."""
    client, session_factory = auth_client
    async with session_factory() as session:
        await create_user(session, tenant_id=1, email="regular@careerops.local", password="regularpassword", role="user")
    user_token = _login_as(client, "regular@careerops.local", "regularpassword")

    response = client.post(
        "/auth/users",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"email": "another@careerops.local", "password": "password123", "role": "user"},
    )
    assert response.status_code == 403
    assert "Administrator role required" in response.json()["detail"]


async def test_create_user_duplicate_email(auth_client):
    """Verify provisioning an existing user email returns 409 Conflict."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.post(
        "/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "password123", "role": "user"},
    )
    assert response.status_code == 409


async def test_admin_can_list_users(auth_client):
    """Verify an administrator can list all users in their tenant organization."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.get("/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    users = response.json()
    assert len(users) >= 1
    assert users[0]["email"] == DEFAULT_ADMIN_EMAIL


async def test_non_admin_cannot_list_users(auth_client):
    """Verify a regular user cannot list tenant users."""
    client, session_factory = auth_client
    async with session_factory() as session:
        await create_user(session, tenant_id=1, email="regular2@careerops.local", password="regularpassword", role="user")
    user_token = _login_as(client, "regular2@careerops.local", "regularpassword")

    response = client.get("/auth/users", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 403


async def test_default_admin_cannot_be_deleted_via_api(auth_client):
    """CRITICAL SECURITY TEST: Ensure DELETE /auth/users/{admin_id} returns 403 and prevents deletion."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    # Get admin user ID
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    admin_id = me_resp.json()["id"]

    delete_resp = client.delete(f"/auth/users/{admin_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert delete_resp.status_code == 403
    assert "protected and cannot be deleted" in delete_resp.json()["detail"]

    # Verify admin is still intact and can still query /auth/me
    verify_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert verify_resp.status_code == 200


async def test_admin_can_delete_regular_user(auth_client):
    """Verify an administrator can delete a regular non-default-admin user."""
    client, session_factory = auth_client
    async with session_factory() as session:
        user = await create_user(session, tenant_id=1, email="delete_me@careerops.local", password="password", role="user")
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.delete(f"/auth/users/{user.id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["deleted"] is True


async def test_delete_nonexistent_user_returns_404(auth_client):
    """Verify deleting a nonexistent user returns 404 Not Found."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.delete("/auth/users/99999", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404


async def test_admin_can_create_tenant(auth_client):
    """Verify an administrator can create a new tenant organization."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.post(
        "/auth/tenants",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Beta Corp", "slug": "beta-corp"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Beta Corp"
    assert data["slug"] == "beta-corp"
