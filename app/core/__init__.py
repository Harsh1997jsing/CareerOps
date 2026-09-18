"""CareerOps Core Framework Module.

Provides centralized configuration, database management, security primitives,
and standardized application exception classes.
"""

from app.core.config import Settings, get_settings, settings
from app.core.database import (
    check_database_health,
    get_db,
    get_engine,
    get_session_factory,
    init_db,
)
from app.core.exceptions import (
    ApplicationNotConfirmedError,
    ApplicationNotFoundError,
    ApplicationWorkflowError,
    AuthError,
    CareerOpsError,
    ConfigurationError,
    ConflictError,
    DatabaseConnectionError,
    DatabaseError,
    ForbiddenError,
    InvalidCredentialsError,
    InvalidTokenError,
    JobNotFoundError,
    NotFoundError,
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

__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "get_engine",
    "get_session_factory",
    "get_db",
    "init_db",
    "check_database_health",
    "CareerOpsError",
    "ConfigurationError",
    "DatabaseError",
    "DatabaseConnectionError",
    "NotFoundError",
    "JobNotFoundError",
    "ApplicationNotFoundError",
    "UserNotFoundError",
    "TenantNotFoundError",
    "ConflictError",
    "UserAlreadyExistsError",
    "TenantAlreadyExistsError",
    "AuthError",
    "InvalidCredentialsError",
    "ForbiddenError",
    "ProtectedAdminError",
    "TokenError",
    "TokenExpiredError",
    "InvalidTokenError",
    "ApplicationWorkflowError",
    "ApplicationNotConfirmedError",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
]
