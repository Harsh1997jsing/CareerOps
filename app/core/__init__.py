"""CareerOps Core Framework Module.

Provides centralized configuration, database management, security primitives,
and standardized application exception classes.
"""

from app.core.config import Settings, get_settings
from app.core.database import (
    check_database_health,
    get_db,
    get_engine,
    get_session_factory,
    init_db,
)
from app.core.exceptions import (
    ApplicationNotConfirmedError,
    ApplicationWorkflowError,
    AuthError,
    CareerOpsError,
    ConfigurationError,
    ConflictError,
    InvalidCredentialsError,
    InvalidTokenError,
    LLMServiceError,
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

__all__ = [
    "Settings",
    "get_settings",
    "get_engine",
    "get_session_factory",
    "get_db",
    "init_db",
    "check_database_health",
    "CareerOpsError",
    "ConfigurationError",
    "LLMServiceError",
    "ConflictError",
    "UserAlreadyExistsError",
    "TenantAlreadyExistsError",
    "AuthError",
    "InvalidCredentialsError",
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
