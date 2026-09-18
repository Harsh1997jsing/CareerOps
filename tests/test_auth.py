"""Unit tests for multi-tenant stateless JWT authentication and user management service."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
async def test_session():
    """Create an isolated in-memory SQLite database initialized with auth schema and seed admin."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session = async_sessionmaker(bind=engine, expire_on_commit=False)()
    await init_auth_db(session)
    yield session
    await engine.dispose()


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


async def test_seed_default_admin(test_session):
    """Verify init_auth_db creates the default tenant and protected default admin."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    assert tenant is not None
    assert tenant.slug == DEFAULT_TENANT_SLUG

    admin_ctx = await authenticate_user(
        test_session,
        email=DEFAULT_ADMIN_EMAIL,
        password=DEFAULT_ADMIN_PASSWORD,
        tenant_slug=DEFAULT_TENANT_SLUG,
    )
    assert admin_ctx.email == DEFAULT_ADMIN_EMAIL
    assert admin_ctx.role == "admin"
    assert admin_ctx.is_default_admin is True


async def test_authenticate_user_invalid_credentials(test_session):
    """Verify invalid password or non-existent user raises InvalidCredentialsError."""
    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(test_session, email=DEFAULT_ADMIN_EMAIL, password="incorrect_password")

    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(test_session, email="ghost@example.com", password="any_password")


async def test_create_user_in_tenant(test_session):
    """Verify an admin can create a user within a tenant and list all users."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    assert tenant is not None

    user = await create_user(
        test_session,
        tenant_id=tenant.id,
        email="developer@careerops.local",
        password="securedevpassword",
        role="user",
    )
    assert user.id is not None
    assert user.email == "developer@careerops.local"
    assert user.role == "user"
    assert user.is_default_admin is False

    users = await list_users(test_session, tenant_id=tenant.id)
    assert len(users) == 2
    emails = [u.email for u in users]
    assert DEFAULT_ADMIN_EMAIL in emails
    assert "developer@careerops.local" in emails


async def test_create_user_duplicate_email_raises_error(test_session):
    """Verify attempting to create a user with an existing email in a tenant raises UserAlreadyExistsError."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    with pytest.raises(UserAlreadyExistsError):
        await create_user(
            test_session,
            tenant_id=tenant.id,
            email=DEFAULT_ADMIN_EMAIL,
            password="newpassword",
        )


async def test_create_user_invalid_role_raises_value_error(test_session):
    """Verify invalid user roles raise a ValueError."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    with pytest.raises(ValueError):
        await create_user(
            test_session,
            tenant_id=tenant.id,
            email="invalidrole@example.com",
            password="password",
            role="super_superuser",
        )


async def test_default_admin_cannot_be_deleted(test_session):
    """CRITICAL SECURITY TEST: Verify the protected default admin can never be deleted."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    users = await list_users(test_session, tenant_id=tenant.id)
    default_admin = next(u for u in users if u.is_default_admin)

    with pytest.raises(ProtectedAdminError) as exc_info:
        await delete_user(test_session, tenant_id=tenant.id, user_id=default_admin.id)

    assert "protected and cannot be deleted" in str(exc_info.value)

    # Verify admin still exists in the database
    persisted_admin = await get_user_by_id(test_session, default_admin.id)
    assert persisted_admin is not None
    assert persisted_admin.id == default_admin.id


async def test_delete_regular_user(test_session):
    """Verify normal non-default-admin users can be deleted successfully."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    user = await create_user(
        test_session,
        tenant_id=tenant.id,
        email="temp_user@example.com",
        password="temppassword",
    )

    deleted = await delete_user(test_session, tenant_id=tenant.id, user_id=user.id)
    assert deleted is True

    # User no longer exists
    assert await get_user_by_id(test_session, user.id) is None


async def test_delete_nonexistent_user(test_session):
    """Verify deleting a nonexistent user returns False without errors."""
    tenant = await get_tenant_by_slug(test_session, DEFAULT_TENANT_SLUG)
    deleted = await delete_user(test_session, tenant_id=tenant.id, user_id=99999)
    assert deleted is False


async def test_create_and_retrieve_tenant(test_session):
    """Verify tenant creation, uniqueness enforcement, and lookup functions."""
    tenant = await create_tenant(test_session, name="Acme Corp", slug="acme")
    assert tenant.id is not None
    assert tenant.name == "Acme Corp"
    assert tenant.slug == "acme"

    by_id = await get_tenant_by_id(test_session, tenant.id)
    assert by_id is not None
    assert by_id.slug == "acme"

    by_slug = await get_tenant_by_slug(test_session, "acme")
    assert by_slug is not None
    assert by_slug.id == tenant.id

    with pytest.raises(TenantAlreadyExistsError):
        await create_tenant(test_session, name="Acme Clone", slug="acme")
