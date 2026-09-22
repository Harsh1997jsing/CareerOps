"""Centralized application and domain exceptions for CareerOps.

Consolidates all error classes into a single module following the DRY
(Don't Repeat Yourself) principle. Facilitates unified exception handling
and consistent HTTP problem responses across all services and routes.
"""


class CareerOpsError(Exception):
    """Base exception for all CareerOps application errors."""

    def __init__(self, message: str = "An internal application error occurred.") -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(CareerOpsError):
    """Raised when critical configuration settings or environment variables are missing."""


class LLMServiceError(CareerOpsError):
    """Raised when a Claude API call fails (timeout, rate limit, connection error) or
    returns output that can't be parsed into the schema the caller requested.

    Wraps `anthropic.APIError`/`pydantic.ValidationError` from
    `app/llm/anthropic_client.py:structured_call()` into one clear, catchable
    type so a transient LLM failure maps to a specific 503 response
    (`app/api/main.py`'s handler) instead of falling through to a generic
    500 or, worse, an unhandled plain-text response.
    """

    def __init__(self, message: str = "The AI service is temporarily unavailable. Please try again.") -> None:
        super().__init__(message)


class ConflictError(CareerOpsError):
    """Base exception for duplicate resources or unique constraint collisions."""


class UserAlreadyExistsError(ConflictError):
    """Raised when attempting to create a user with an already registered email."""

    def __init__(self, email: str = "") -> None:
        msg = f"User with email '{email}' already exists in tenant." if email else "User already exists in tenant."
        super().__init__(msg)
        self.email = email


class TenantAlreadyExistsError(ConflictError):
    """Raised when attempting to create a tenant with an existing slug."""

    def __init__(self, slug: str = "") -> None:
        msg = f"Tenant slug '{slug}' already exists." if slug else "Tenant slug already exists."
        super().__init__(msg)
        self.slug = slug


class AuthError(CareerOpsError):
    """Base exception for authentication and authorization errors."""


class InvalidCredentialsError(AuthError):
    """Raised when authentication credentials (email/password/tenant) are invalid."""

    def __init__(self, message: str = "Invalid email, password, or tenant.") -> None:
        super().__init__(message)


class ProtectedAdminError(AuthError):
    """Raised when attempting to delete or alter the immutable protected default administrator."""

    def __init__(
        self,
        message: str = "The default administrator user is protected and cannot be deleted.",
    ) -> None:
        super().__init__(message)


class TokenError(AuthError):
    """Base exception for JWT token processing errors."""


class TokenExpiredError(TokenError):
    """Raised when a JWT access token's expiration timestamp has passed."""

    def __init__(self, message: str = "Access token has expired.") -> None:
        super().__init__(message)


class InvalidTokenError(TokenError):
    """Raised when a JWT token signature is invalid, tampered, or malformed."""

    def __init__(self, message: str = "Invalid access token.") -> None:
        super().__init__(message)


class ApplicationWorkflowError(CareerOpsError):
    """Base exception for application workflow and review stage violations."""


class ApplicationNotConfirmedError(ApplicationWorkflowError, RuntimeError):
    """Raised when mark_applied() is called without explicit human confirmation.

    Inherits from RuntimeError to maintain complete backward compatibility with
    legacy callers while adhering to the unified CareerOps error hierarchy.
    """

    def __init__(
        self,
        message: str = (
            "Refusing to mark this APPLIED without explicit confirmation. Pass "
            "confirmed=True only after you've manually submitted this application "
            "yourself, in your own browser."
        ),
    ) -> None:
        super().__init__(message)
