"""Integration and route tests for multi-tenant stateless JWT auth API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db_engine
from app.api.main import app
from app.services.auth import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    create_user,
    init_auth_db,
)


@pytest.fixture
def auth_client():
    """Create a TestClient with an isolated in-memory SQLite database for authentication testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_auth_db(engine)

    app.dependency_overrides[get_db_engine] = lambda: engine
    client = TestClient(app)

    yield client, engine

    app.dependency_overrides.pop(get_db_engine, None)


def _login_as(client: TestClient, email: str, password: str, tenant_slug: str = "default") -> str:
    """Helper to login and obtain bearer token."""
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


def test_login_success(auth_client):
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


def test_login_invalid_credentials(auth_client):
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


def test_get_me_authenticated(auth_client):
    """Verify /auth/me returns the profile for a user with a valid bearer token."""
    client, _ = auth_client
    token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == DEFAULT_ADMIN_EMAIL
    assert data["role"] == "admin"
    assert data["is_default_admin"] is True


def test_get_me_unauthenticated(auth_client):
    """Verify /auth/me returns 401 when no token is provided."""
    client, _ = auth_client
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_admin_can_create_user(auth_client):
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


def test_non_admin_cannot_create_user(auth_client):
    """Verify a regular non-admin user cannot provision users (403 Forbidden)."""
    client, engine = auth_client
    create_user(engine, tenant_id=1, email="regular@careerops.local", password="regularpassword", role="user")
    user_token = _login_as(client, "regular@careerops.local", "regularpassword")

    response = client.post(
        "/auth/users",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"email": "another@careerops.local", "password": "password123", "role": "user"},
    )
    assert response.status_code == 403
    assert "Administrator role required" in response.json()["detail"]


def test_create_user_duplicate_email(auth_client):
    """Verify provisioning an existing user email returns 409 Conflict."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.post(
        "/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "password123", "role": "user"},
    )
    assert response.status_code == 409


def test_admin_can_list_users(auth_client):
    """Verify an administrator can list all users in their tenant organization."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.get("/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    users = response.json()
    assert len(users) >= 1
    assert users[0]["email"] == DEFAULT_ADMIN_EMAIL


def test_non_admin_cannot_list_users(auth_client):
    """Verify a regular user cannot list tenant users."""
    client, engine = auth_client
    create_user(engine, tenant_id=1, email="regular2@careerops.local", password="regularpassword", role="user")
    user_token = _login_as(client, "regular2@careerops.local", "regularpassword")

    response = client.get("/auth/users", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 403


def test_default_admin_cannot_be_deleted_via_api(auth_client):
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


def test_admin_can_delete_regular_user(auth_client):
    """Verify an administrator can delete a regular non-default-admin user."""
    client, engine = auth_client
    user = create_user(engine, tenant_id=1, email="delete_me@careerops.local", password="password", role="user")
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.delete(f"/auth/users/{user.id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_delete_nonexistent_user_returns_404(auth_client):
    """Verify deleting a nonexistent user returns 404 Not Found."""
    client, _ = auth_client
    admin_token = _login_as(client, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    response = client.delete("/auth/users/99999", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404


def test_admin_can_create_tenant(auth_client):
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
