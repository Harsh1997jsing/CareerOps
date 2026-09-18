"""Multi-tenant stateless JWT authentication and user management service.

Implements:
- Multi-tenant tenant and user models.
- Secure PBKDF2 password hashing (pure standard library with high iteration count).
- Stateless JWT generation and validation without session tracking tables.
- Protected default admin enforcement: the default system admin can never be deleted.
- Admin-only user provisioning within tenant boundaries.
"""

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import jwt
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Configuration constants with safe defaults
DEFAULT_JWT_SECRET = "careerops-super-secret-jwt-key-change-in-production"
DEFAULT_ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 1440  # 24 hours
DEFAULT_ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@careerops.local")
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "adminpassword123")
DEFAULT_TENANT_NAME = "Default Organization"
DEFAULT_TENANT_SLUG = "default"

PBKDF2_ITERATIONS = 100_000


# Exceptions
class AuthError(Exception):
    """Base exception for authentication and authorization errors."""


class InvalidCredentialsError(AuthError):
    """Raised when authentication credentials (email/password) are incorrect."""


class UserNotFoundError(AuthError):
    """Raised when a specified user does not exist."""


class UserAlreadyExistsError(AuthError):
    """Raised when attempting to create a user with an already registered email."""


class ProtectedAdminError(AuthError):
    """Raised when attempting to delete or alter the protected default administrator."""


class TenantNotFoundError(AuthError):
    """Raised when a tenant organization cannot be found."""


class TenantAlreadyExistsError(AuthError):
    """Raised when attempting to create a tenant with an existing slug."""


class TokenError(AuthError):
    """Base exception for JWT token processing errors."""


class TokenExpiredError(TokenError):
    """Raised when a JWT token has expired."""


class InvalidTokenError(TokenError):
    """Raised when a JWT token is invalid or malformed."""


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


# Password Security Functions
def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with 100,000 iterations.

    Args:
        password: Plaintext password string.
        salt: Optional 16-byte salt (generated randomly if None).

    Returns:
        str: Encoded hash string in format: `salt_hex$iterations$hash_hex`.
    """
    if salt is None:
        salt = secrets.token_bytes(16)

    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${PBKDF2_ITERATIONS}${pwd_hash.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an encoded PBKDF2 hash.

    Args:
        plain_password: Provided password string to test.
        hashed_password: Stored hash string in `salt_hex$iterations$hash_hex` format.

    Returns:
        bool: True if password matches; False otherwise.
    """
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        salt_hex, iterations_str, expected_hash_hex = parts
        salt = bytes.fromhex(salt_hex)
        iterations = int(iterations_str)
        expected_hash = bytes.fromhex(expected_hash_hex)

        computed_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed_hash, expected_hash)
    except Exception:
        return False


# JWT Token Functions
def get_jwt_secret() -> str:
    """Retrieve the configured JWT secret key from the environment.

    Returns:
        str: Secret key string.
    """
    return os.environ.get("JWT_SECRET_KEY", DEFAULT_JWT_SECRET)


def get_jwt_algorithm() -> str:
    """Retrieve the configured JWT signature algorithm.

    Returns:
        str: JWT algorithm identifier (e.g., 'HS256').
    """
    return os.environ.get("JWT_ALGORITHM", DEFAULT_ALGORITHM)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed, stateless JWT access token.

    Args:
        data: Dictionary of claims to encode in the token payload.
        expires_delta: Optional custom expiration timedelta.

    Returns:
        str: Encoded JWT access token string.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        minutes = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", DEFAULT_EXPIRE_MINUTES))
        expire = now + timedelta(minutes=minutes)

    to_encode.update({"exp": expire, "iat": now})
    secret = get_jwt_secret()
    algorithm = get_jwt_algorithm()
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Args:
        token: JWT string.

    Returns:
        dict[str, Any]: Decoded payload claims dictionary.

    Raises:
        TokenExpiredError: If token expiration timestamp (`exp`) has passed.
        InvalidTokenError: If token signature is invalid or token is malformed.
    """
    secret = get_jwt_secret()
    algorithm = get_jwt_algorithm()
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError("Access token has expired") from e
    except jwt.PyJWTError as e:
        raise InvalidTokenError("Invalid access token") from e


# Database Initialization & Seeding
def init_auth_db(engine: Engine) -> None:
    """Bootstrap auth tables and seed the protected default admin user.

    Ensures `tenants` and `users` tables exist, verifies the default tenant,
    and seeds the protected default administrator account if missing.

    Args:
        engine: SQLAlchemy Engine instance.
    """
    is_sqlite = engine.dialect.name == "sqlite"
    id_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
    time_default = "CURRENT_TIMESTAMP" if is_sqlite else "now()"
    bool_true = "1" if is_sqlite else "true"
    bool_false = "0" if is_sqlite else "false"

    with engine.begin() as conn:
        # Create tenants table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS tenants (
                    id {id_type},
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    is_active BOOLEAN DEFAULT {bool_true},
                    created_at TIMESTAMP DEFAULT {time_default}
                )
                """
            )
        )
        # Create users table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {id_type},
                    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    hashed_password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_default_admin BOOLEAN DEFAULT {bool_false},
                    is_active BOOLEAN DEFAULT {bool_true},
                    created_at TIMESTAMP DEFAULT {time_default},
                    UNIQUE (tenant_id, email)
                )
                """
            )
        )

        # Ensure default tenant exists
        row = conn.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"),
            {"slug": DEFAULT_TENANT_SLUG},
        ).mappings().first()

        if row is None:
            res = conn.execute(
                text("INSERT INTO tenants (name, slug) VALUES (:name, :slug) RETURNING id"),
                {"name": DEFAULT_TENANT_NAME, "slug": DEFAULT_TENANT_SLUG},
            ).mappings().first()
            tenant_id = res["id"]
        else:
            tenant_id = row["id"]

        # Ensure default admin user exists
        admin_row = conn.execute(
            text("SELECT id, is_default_admin FROM users WHERE tenant_id = :tenant_id AND email = :email"),
            {"tenant_id": tenant_id, "email": DEFAULT_ADMIN_EMAIL},
        ).mappings().first()

        if admin_row is None:
            hashed_pwd = hash_password(DEFAULT_ADMIN_PASSWORD)
            conn.execute(
                text(
                    """
                    INSERT INTO users (tenant_id, email, hashed_password, role, is_default_admin, is_active)
                    VALUES (:tenant_id, :email, :hashed_password, 'admin', true, true)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "email": DEFAULT_ADMIN_EMAIL,
                    "hashed_password": hashed_pwd,
                },
            )


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
