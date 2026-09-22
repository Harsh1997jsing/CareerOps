"""Multi-tenant stateless JWT authentication and user management service.

Implements:
- Multi-tenant tenant and user domain models.
- Secure PBKDF2 password hashing and stateless JWT integration via `app.core`.
- Protected default admin enforcement: the default system admin can never be deleted.
- Admin-only user provisioning within tenant boundaries.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import init_db
from app.core.exceptions import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    ProtectedAdminError,
    TenantAlreadyExistsError,
    TokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import Tenant, User
from app.schemas import UserContext

# Re-export for complete backward compatibility
__all__ = [
    "Tenant",
    "User",
    "UserContext",
    "AuthError",
    "InvalidCredentialsError",
    "UserAlreadyExistsError",
    "ProtectedAdminError",
    "TenantAlreadyExistsError",
    "TokenError",
    "TokenExpiredError",
    "InvalidTokenError",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "init_auth_db",
    "create_tenant",
    "get_tenant_by_id",
    "get_tenant_by_slug",
    "authenticate_user",
    "create_user",
    "get_user_by_id",
    "list_users",
    "delete_user",
    "DEFAULT_ADMIN_EMAIL",
    "DEFAULT_ADMIN_PASSWORD",
    "DEFAULT_TENANT_NAME",
    "DEFAULT_TENANT_SLUG",
]

# Settings-derived defaults.
_settings = get_settings()
DEFAULT_ADMIN_EMAIL = _settings.default_admin_email
DEFAULT_ADMIN_PASSWORD = _settings.default_admin_password
DEFAULT_TENANT_NAME = _settings.default_tenant_name
DEFAULT_TENANT_SLUG = _settings.default_tenant_slug


async def init_auth_db(session: AsyncSession) -> None:
    """Bootstrap auth tables and seed the protected default admin user.

    Delegates to centralized database bootstrap in `app.core.database`.

    Args:
        session: Async SQLAlchemy Session — only its bound AsyncEngine is
            used (`session.bind`, not `get_bind()`, which returns the
            internal sync-facing proxy AsyncSession wraps, not the actual
            AsyncEngine), since init_db() manages its own session internally.
    """
    await init_db(session.bind)


# Tenant Management
async def create_tenant(session: AsyncSession, name: str, slug: str) -> Tenant:
    """Create a new tenant organization.

    Args:
        session: Database session.
        name: Organization display name.
        slug: Normalized identifier slug.

    Returns:
        Tenant: Newly created tenant record.

    Raises:
        TenantAlreadyExistsError: If a tenant with the same slug already
            exists — either seen by the check below, or, for two
            concurrent requests racing past that check together, caught
            from the unique-constraint violation the second commit hits
            (same pattern as app/sources/common.py:insert_jobs()).
    """
    clean_slug = slug.strip().lower()
    if await session.scalar(select(Tenant).where(Tenant.slug == clean_slug)) is not None:
        raise TenantAlreadyExistsError(f"Tenant slug '{clean_slug}' already exists")

    tenant = Tenant(name=name.strip(), slug=clean_slug)
    session.add(tenant)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise TenantAlreadyExistsError(f"Tenant slug '{clean_slug}' already exists") from exc
    await session.refresh(tenant)
    return tenant


async def get_tenant_by_id(session: AsyncSession, tenant_id: int) -> Tenant | None:
    """Retrieve tenant by primary key ID."""
    return await session.get(Tenant, tenant_id)


async def get_tenant_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    """Retrieve tenant by URL slug."""
    return await session.scalar(select(Tenant).where(Tenant.slug == slug.strip().lower()))


# User Management
async def authenticate_user(
    session: AsyncSession, email: str, password: str, tenant_slug: str | None = None
) -> UserContext:
    """Authenticate a user by email, password, and tenant slug.

    Args:
        session: Database session.
        email: User email address.
        password: Raw password string.
        tenant_slug: Optional tenant slug (defaults to 'default').

    Returns:
        UserContext: Verified user context.

    Raises:
        InvalidCredentialsError: If credentials do not match an active user and tenant.
    """
    slug = (tenant_slug or DEFAULT_TENANT_SLUG).strip().lower()
    clean_email = email.strip().lower()

    tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    user = None
    if tenant is not None:
        user = await session.scalar(
            select(User).where(User.tenant_id == tenant.id, User.email == clean_email)
        )

    if tenant is None or user is None:
        raise InvalidCredentialsError("Invalid email, password, or tenant")

    if not user.is_active or not tenant.is_active:
        raise InvalidCredentialsError("User account or tenant is inactive")

    if not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("Invalid email, password, or tenant")

    return UserContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        tenant_slug=tenant.slug,
        email=user.email,
        role=user.role,
        is_default_admin=user.is_default_admin,
    )


async def create_user(
    session: AsyncSession, tenant_id: int, email: str, password: str, role: str = "user"
) -> User:
    """Create a new user within a specific tenant organization.

    Args:
        session: Database session.
        tenant_id: ID of the tenant organization.
        email: New user's email address.
        password: Raw password to hash and store.
        role: User role ('user' or 'admin').

    Returns:
        User: Newly created User instance.

    Raises:
        UserAlreadyExistsError: If the email already exists in this tenant
            — either seen by the check below, or, for two concurrent
            requests racing past that check together, caught from the
            unique-constraint violation the second commit hits (same
            pattern as app/sources/common.py:insert_jobs()).
        ValueError: If role is invalid.
    """
    clean_email = email.strip().lower()
    clean_role = role.strip().lower()
    if clean_role not in ("admin", "user"):
        raise ValueError("Role must be 'admin' or 'user'")

    existing = await session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.email == clean_email)
    )
    if existing is not None:
        raise UserAlreadyExistsError(f"User with email '{clean_email}' already exists in tenant")

    user = User(
        tenant_id=tenant_id,
        email=clean_email,
        hashed_password=hash_password(password),
        role=clean_role,
        is_default_admin=False,
        is_active=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise UserAlreadyExistsError(f"User with email '{clean_email}' already exists in tenant") from exc
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Retrieve user by primary key ID."""
    return await session.get(User, user_id)


async def list_users(session: AsyncSession, tenant_id: int) -> list[User]:
    """List all users within a given tenant organization, ordered by id."""
    stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.id)
    return list((await session.scalars(stmt)).all())


async def delete_user(session: AsyncSession, tenant_id: int, user_id: int) -> bool:
    """Delete a user from a tenant organization.

    Enforces the critical protection rule: the default admin user CANNOT be deleted.

    Args:
        session: Database session.
        tenant_id: Tenant organization ID.
        user_id: User ID to delete.

    Returns:
        bool: True if user was deleted; False if user did not exist.

    Raises:
        ProtectedAdminError: If the target user is the protected default admin.
    """
    user = await session.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if user is None:
        return False

    if user.is_default_admin:
        raise ProtectedAdminError("The default administrator user is protected and cannot be deleted")

    await session.delete(user)
    await session.commit()
    return True
