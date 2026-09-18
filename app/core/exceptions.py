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


class DatabaseError(CareerOpsError):
    """Base exception for persistence and database access errors."""


class DatabaseConnectionError(DatabaseError):
    """Raised when the database engine fails to connect or ping the server."""


class NotFoundError(CareerOpsError):
    """Base exception for requested resources that cannot be located."""


class JobNotFoundError(NotFoundError):
    """Raised when a specific job cannot be found in the database."""

    def __init__(self, job_id: int | str) -> None:
        super().__init__(f"Job with ID '{job_id}' not found.")
        self.job_id = job_id


class ApplicationNotFoundError(NotFoundError):
    """Raised when an application record cannot be found."""

    def __init__(self, application_id: int | str) -> None:
        super().__init__(f"Application with ID '{application_id}' not found.")
        self.application_id = application_id


class UserNotFoundError(NotFoundError):
    """Raised when a user account cannot be found."""

    def __init__(self, identifier: int | str = "") -> None:
        msg = f"User '{identifier}' not found." if identifier else "User not found."
        super().__init__(msg)
        self.identifier = identifier


class TenantNotFoundError(NotFoundError):
    """Raised when a tenant organization cannot be found."""

    def __init__(self, slug_or_id: int | str = "") -> None:
        msg = f"Tenant '{slug_or_id}' not found." if slug_or_id else "Tenant not found."
        super().__init__(msg)
        self.slug_or_id = slug_or_id


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


class ForbiddenError(AuthError):
    """Raised when an authenticated user lacks required permissions or roles."""

    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
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
