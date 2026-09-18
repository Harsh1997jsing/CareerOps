"""Multi-tenant stateless JWT authentication and user management service.

Implements:
- Multi-tenant tenant and user domain models.
- Secure PBKDF2 password hashing and stateless JWT integration via `app.core`.
- Protected default admin enforcement: the default system admin can never be deleted.
- Admin-only user provisioning within tenant boundaries.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.database import init_db
from app.core.exceptions import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    ProtectedAdminError,
    TenantAlreadyExistsError,
    TenantNotFoundError,
    TokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# Re-export for complete backward compatibility
__all__ = [
    "Tenant",
    "User",
    "UserContext",
    "AuthError",
    "InvalidCredentialsError",
    "UserNotFoundError",
    "UserAlreadyExistsError",
    "ProtectedAdminError",
    "TenantNotFoundError",
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

# Settings-derived defaults
settings = get_settings()
DEFAULT_ADMIN_EMAIL = settings.default_admin_email
DEFAULT_ADMIN_PASSWORD = settings.default_admin_password
DEFAULT_TENANT_NAME = settings.default_tenant_name
DEFAULT_TENANT_SLUG = settings.default_tenant_slug


# Data models
@dataclass
class Tenant:
    """Tenant organization representation.

    Attributes:
        id: Primary key identifier.
        name: Display name of the tenant organization.
        slug: Unique URL and lookup slug.
        is_active: Whether the tenant is enabled.
        created_at: Creation timestamp.
    """
    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime | None


@dataclass
class User:
    """User account representation.

    Attributes:
        id: Primary key identifier.
        tenant_id: ID of the tenant organization this user belongs to.
        email: User's email address.
        role: User role ('admin' or 'user').
        is_default_admin: True if this is the protected default system admin.
        is_active: Whether the account is active.
        created_at: Account creation timestamp.
    """
    id: int
    tenant_id: int
    email: str
    role: str
    is_default_admin: bool
    is_active: bool
    created_at: datetime | None


@dataclass
class UserContext:
    """Authenticated user context extracted from JWT claims.

    Attributes:
        user_id: Unique identifier of the authenticated user.
        tenant_id: ID of the tenant organization.
        tenant_slug: Slug of the tenant organization.
        email: User's email address.
        role: User role ('admin' or 'user').
        is_default_admin: Whether user is the protected default administrator.
    """
    user_id: int
    tenant_id: int
    tenant_slug: str
    email: str
    role: str
    is_default_admin: bool


def init_auth_db(engine: Engine) -> None:
    """Bootstrap auth tables and seed the protected default admin user.

    Delegates to centralized database bootstrap in `app.core.database`.

    Args:
        engine: SQLAlchemy Engine instance.
    """
    init_db(engine)


# Mapping helpers
def _row_to_tenant(row: Mapping) -> Tenant:
    """Map database row mapping onto a Tenant dataclass instance.

    Args:
        row: Database row mapping.

    Returns:
        Tenant: Mapped tenant instance.
    """
    return Tenant(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        is_active=row["is_active"],
        created_at=row.get("created_at"),
    )


def _row_to_user(row: Mapping) -> User:
    """Map database row mapping onto a User dataclass instance.

    Args:
        row: Database row mapping.

    Returns:
        User: Mapped user instance.
    """
    return User(
        id=row["id"],
        tenant_id=row["tenant_id"],
        email=row["email"],
        role=row["role"],
        is_default_admin=bool(row.get("is_default_admin")),
        is_active=bool(row["is_active"]),
        created_at=row.get("created_at"),
    )


# Tenant Management
def create_tenant(engine: Engine, name: str, slug: str) -> Tenant:
    """Create a new tenant organization.

    Args:
        engine: Database engine.
        name: Organization display name.
        slug: Normalized identifier slug.

    Returns:
        Tenant: Newly created tenant record.

    Raises:
        TenantAlreadyExistsError: If a tenant with the same slug already exists.
    """
    clean_slug = slug.strip().lower()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"),
            {"slug": clean_slug},
        ).mappings().first()
        if existing:
            raise TenantAlreadyExistsError(f"Tenant slug '{clean_slug}' already exists")

        row = conn.execute(
            text("INSERT INTO tenants (name, slug) VALUES (:name, :slug) RETURNING id, name, slug, is_active, created_at"),
            {"name": name.strip(), "slug": clean_slug},
        ).mappings().first()

    return _row_to_tenant(row)


def get_tenant_by_id(engine: Engine, tenant_id: int) -> Tenant | None:
    """Retrieve tenant by primary key ID.

    Args:
        engine: Database engine.
        tenant_id: Tenant primary key ID.

    Returns:
        Tenant | None: Tenant instance or None if not found.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, slug, is_active, created_at FROM tenants WHERE id = :id"),
            {"id": tenant_id},
        ).mappings().first()
    return _row_to_tenant(row) if row else None


def get_tenant_by_slug(engine: Engine, slug: str) -> Tenant | None:
    """Retrieve tenant by URL slug.

    Args:
        engine: Database engine.
        slug: Normalized tenant identifier slug.

    Returns:
        Tenant | None: Tenant instance or None if not found.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, slug, is_active, created_at FROM tenants WHERE slug = :slug"),
            {"slug": slug.strip().lower()},
        ).mappings().first()
    return _row_to_tenant(row) if row else None


# User Management
def authenticate_user(engine: Engine, email: str, password: str, tenant_slug: str | None = None) -> UserContext:
    """Authenticate a user by email, password, and tenant slug.

    Args:
        engine: Database engine.
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

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT u.id, u.tenant_id, u.email, u.hashed_password, u.role,
                       u.is_default_admin, u.is_active, t.slug as tenant_slug, t.is_active as tenant_active
                FROM users u
                JOIN tenants t ON t.id = u.tenant_id
                WHERE LOWER(u.email) = :email AND t.slug = :slug
                """
            ),
            {"email": clean_email, "slug": slug},
        ).mappings().first()

    if row is None:
        raise InvalidCredentialsError("Invalid email, password, or tenant")

    if not row["is_active"] or not row["tenant_active"]:
        raise InvalidCredentialsError("User account or tenant is inactive")

    if not verify_password(password, row["hashed_password"]):
        raise InvalidCredentialsError("Invalid email, password, or tenant")

    return UserContext(
        user_id=row["id"],
        tenant_id=row["tenant_id"],
        tenant_slug=row["tenant_slug"],
        email=row["email"],
        role=row["role"],
        is_default_admin=bool(row.get("is_default_admin")),
    )


def create_user(engine: Engine, tenant_id: int, email: str, password: str, role: str = "user") -> User:
    """Create a new user within a specific tenant organization.

    Args:
        engine: Database engine.
        tenant_id: ID of the tenant organization.
        email: New user's email address.
        password: Raw password to hash and store.
        role: User role ('user' or 'admin').

    Returns:
        User: Newly created User instance.

    Raises:
        UserAlreadyExistsError: If the email already exists in this tenant.
        ValueError: If role is invalid.
    """
    clean_email = email.strip().lower()
    clean_role = role.strip().lower()
    if clean_role not in ("admin", "user"):
        raise ValueError("Role must be 'admin' or 'user'")

    hashed_pwd = hash_password(password)

    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE tenant_id = :tenant_id AND LOWER(email) = :email"),
            {"tenant_id": tenant_id, "email": clean_email},
        ).mappings().first()

        if existing:
            raise UserAlreadyExistsError(f"User with email '{clean_email}' already exists in tenant")

        row = conn.execute(
            text(
                """
                INSERT INTO users (tenant_id, email, hashed_password, role, is_default_admin, is_active)
                VALUES (:tenant_id, :email, :hashed_password, :role, false, true)
                RETURNING id, tenant_id, email, role, is_default_admin, is_active, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "email": clean_email,
                "hashed_password": hashed_pwd,
                "role": clean_role,
            },
        ).mappings().first()

    return _row_to_user(row)


def get_user_by_id(engine: Engine, user_id: int) -> User | None:
    """Retrieve user by primary key ID.

    Args:
        engine: Database engine.
        user_id: User primary key.

    Returns:
        User | None: User instance or None if not found.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, tenant_id, email, role, is_default_admin, is_active, created_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).mappings().first()
    return _row_to_user(row) if row else None


def list_users(engine: Engine, tenant_id: int) -> list[User]:
    """List all users within a given tenant organization.

    Args:
        engine: Database engine.
        tenant_id: Tenant primary key ID.

    Returns:
        list[User]: List of User instances in the tenant.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, tenant_id, email, role, is_default_admin, is_active, created_at
                FROM users WHERE tenant_id = :tenant_id ORDER BY id ASC
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings().all()
    return [_row_to_user(row) for row in rows]


def delete_user(engine: Engine, tenant_id: int, user_id: int) -> bool:
    """Delete a user from a tenant organization.

    Enforces the critical protection rule: the default admin user CANNOT be deleted.

    Args:
        engine: Database engine.
        tenant_id: Tenant organization ID.
        user_id: User ID to delete.

    Returns:
        bool: True if user was deleted; False if user did not exist.

    Raises:
        ProtectedAdminError: If the target user is the protected default admin.
    """
    with engine.begin() as conn:
        user_row = conn.execute(
            text("SELECT id, is_default_admin FROM users WHERE id = :id AND tenant_id = :tenant_id"),
            {"id": user_id, "tenant_id": tenant_id},
        ).mappings().first()

        if user_row is None:
            return False

        if user_row["is_default_admin"]:
            raise ProtectedAdminError("The default administrator user is protected and cannot be deleted")

        result = conn.execute(
            text("DELETE FROM users WHERE id = :id AND tenant_id = :tenant_id"),
            {"id": user_id, "tenant_id": tenant_id},
        )
        return result.rowcount > 0
