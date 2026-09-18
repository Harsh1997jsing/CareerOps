"""Unit tests for multi-tenant stateless JWT authentication and user management service."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine

from app.services.auth import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_TENANT_SLUG,
    InvalidCredentialsError,
    InvalidTokenError,
    ProtectedAdminError,
    TenantAlreadyExistsError,
    TokenExpiredError,
    UserAlreadyExistsError,
    authenticate_user,
    create_access_token,
    create_tenant,
    create_user,
    decode_access_token,
    delete_user,
    get_tenant_by_id,
    get_tenant_by_slug,
    get_user_by_id,
    hash_password,
    init_auth_db,
    list_users,
    verify_password,
)


@pytest.fixture
def test_engine():
    """Create an isolated in-memory SQLite database initialized with auth schema and seed admin."""
    engine = create_engine("sqlite:///:memory:")
    init_auth_db(engine)
    return engine


def test_hash_and_verify_password():
    """Verify password hashing produces verifiable hashes and rejects mismatches."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert "$" in hashed
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password(password, "invalid$format") is False


def test_create_and_decode_token():
    """Verify stateless JWT generation, payload decoding, and round-trip claims preservation."""
    payload = {"sub": "42", "email": "test@example.com", "role": "admin"}
    token = create_access_token(payload)

    assert isinstance(token, str)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "42"
    assert decoded["email"] == "test@example.com"
    assert decoded["role"] == "admin"
    assert "exp" in decoded
    assert "iat" in decoded


def test_expired_token_raises_token_expired_error():
    """Verify expired JWT tokens raise TokenExpiredError on decoding."""
    payload = {"sub": "42"}
    token = create_access_token(payload, expires_delta=timedelta(seconds=-10))

    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_invalid_token_raises_invalid_token_error():
    """Verify corrupted or improperly signed tokens raise InvalidTokenError."""
    with pytest.raises(InvalidTokenError):
        decode_access_token("this.is.not.a.valid.jwt")


def test_seed_default_admin(test_engine):
    """Verify init_auth_db creates the default tenant and protected default admin."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    assert tenant is not None
    assert tenant.slug == DEFAULT_TENANT_SLUG

    admin_ctx = authenticate_user(
        test_engine,
        email=DEFAULT_ADMIN_EMAIL,
        password=DEFAULT_ADMIN_PASSWORD,
        tenant_slug=DEFAULT_TENANT_SLUG,
    )
    assert admin_ctx.email == DEFAULT_ADMIN_EMAIL
    assert admin_ctx.role == "admin"
    assert admin_ctx.is_default_admin is True


def test_authenticate_user_invalid_credentials(test_engine):
    """Verify invalid password or non-existent user raises InvalidCredentialsError."""
    with pytest.raises(InvalidCredentialsError):
        authenticate_user(test_engine, email=DEFAULT_ADMIN_EMAIL, password="incorrect_password")

    with pytest.raises(InvalidCredentialsError):
        authenticate_user(test_engine, email="ghost@example.com", password="any_password")


def test_create_user_in_tenant(test_engine):
    """Verify an admin can create a user within a tenant and list all users."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    assert tenant is not None

    user = create_user(
        test_engine,
        tenant_id=tenant.id,
        email="developer@careerops.local",
        password="securedevpassword",
        role="user",
    )
    assert user.id is not None
    assert user.email == "developer@careerops.local"
    assert user.role == "user"
    assert user.is_default_admin is False

    users = list_users(test_engine, tenant_id=tenant.id)
    assert len(users) == 2
    emails = [u.email for u in users]
    assert DEFAULT_ADMIN_EMAIL in emails
    assert "developer@careerops.local" in emails


def test_create_user_duplicate_email_raises_error(test_engine):
    """Verify attempting to create a user with an existing email in a tenant raises UserAlreadyExistsError."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    with pytest.raises(UserAlreadyExistsError):
        create_user(
            test_engine,
            tenant_id=tenant.id,
            email=DEFAULT_ADMIN_EMAIL,
            password="newpassword",
        )


def test_create_user_invalid_role_raises_value_error(test_engine):
    """Verify invalid user roles raise a ValueError."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    with pytest.raises(ValueError):
        create_user(
            test_engine,
            tenant_id=tenant.id,
            email="invalidrole@example.com",
            password="password",
            role="super_superuser",
        )


def test_default_admin_cannot_be_deleted(test_engine):
    """CRITICAL SECURITY TEST: Verify the protected default admin can never be deleted."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    users = list_users(test_engine, tenant_id=tenant.id)
    default_admin = next(u for u in users if u.is_default_admin)

    with pytest.raises(ProtectedAdminError) as exc_info:
        delete_user(test_engine, tenant_id=tenant.id, user_id=default_admin.id)

    assert "protected and cannot be deleted" in str(exc_info.value)

    # Verify admin still exists in the database
    persisted_admin = get_user_by_id(test_engine, default_admin.id)
    assert persisted_admin is not None
    assert persisted_admin.id == default_admin.id


def test_delete_regular_user(test_engine):
    """Verify normal non-default-admin users can be deleted successfully."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    user = create_user(
        test_engine,
        tenant_id=tenant.id,
        email="temp_user@example.com",
        password="temppassword",
    )

    deleted = delete_user(test_engine, tenant_id=tenant.id, user_id=user.id)
    assert deleted is True

    # User no longer exists
    assert get_user_by_id(test_engine, user.id) is None


def test_delete_nonexistent_user(test_engine):
    """Verify deleting a nonexistent user returns False without errors."""
    tenant = get_tenant_by_slug(test_engine, DEFAULT_TENANT_SLUG)
    deleted = delete_user(test_engine, tenant_id=tenant.id, user_id=99999)
    assert deleted is False


def test_create_and_retrieve_tenant(test_engine):
    """Verify tenant creation, uniqueness enforcement, and lookup functions."""
    tenant = create_tenant(test_engine, name="Acme Corp", slug="acme")
    assert tenant.id is not None
    assert tenant.name == "Acme Corp"
    assert tenant.slug == "acme"

    by_id = get_tenant_by_id(test_engine, tenant.id)
    assert by_id is not None
    assert by_id.slug == "acme"

    by_slug = get_tenant_by_slug(test_engine, "acme")
    assert by_slug is not None
    assert by_slug.id == tenant.id

    with pytest.raises(TenantAlreadyExistsError):
        create_tenant(test_engine, name="Acme Clone", slug="acme")
