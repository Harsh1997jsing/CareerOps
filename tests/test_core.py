"""Unit tests for centralized app.core modules (config, database, security, exceptions)."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core import (
    ApplicationNotConfirmedError,
    AuthError,
    CareerOpsError,
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotFoundError,
    ProtectedAdminError,
    Settings,
    TokenExpiredError,
    UserAlreadyExistsError,
    check_database_health,
    create_access_token,
    decode_access_token,
    get_db,
    get_engine,
    get_settings,
    hash_password,
    init_db,
    verify_password,
)


def test_core_settings_defaults():
    """Verify application Settings loads valid defaults."""
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.app_name == "CareerOps API"
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes > 0
    assert settings.default_admin_email == "admin@careerops.local"


def test_core_security_hash_and_verify():
    """Verify core password hashing with PBKDF2."""
    password = "CorrectHorseBatteryStaple!"
    hashed = hash_password(password)

    assert hashed != password
    assert "$" in hashed
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password(password, "malformed$hash") is False


def test_core_security_jwt_lifecycle():
    """Verify token encoding, decoding, and expiration enforcement."""
    claims = {"sub": "99", "role": "admin", "tenant_id": 1}
    token = create_access_token(claims)
    decoded = decode_access_token(token)

    assert decoded["sub"] == "99"
    assert decoded["role"] == "admin"
    assert decoded["tenant_id"] == 1
    assert "exp" in decoded

    # Expired token
    expired_token = create_access_token(claims, expires_delta=timedelta(seconds=-1))
    with pytest.raises(TokenExpiredError):
        decode_access_token(expired_token)

    # Invalid token
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.valid.jwt")


def test_core_exceptions_hierarchy():
    """Verify DRY exception hierarchy and inheritance."""
    # Base inheritance
    assert issubclass(AuthError, CareerOpsError)
    assert issubclass(NotFoundError, CareerOpsError)
    assert issubclass(ConflictError, CareerOpsError)

    # Specific errors
    assert issubclass(ProtectedAdminError, AuthError)
    assert issubclass(ForbiddenError, AuthError)
    assert issubclass(InvalidCredentialsError, AuthError)
    assert issubclass(UserAlreadyExistsError, ConflictError)

    # Backward compatibility for ApplicationNotConfirmedError
    assert issubclass(ApplicationNotConfirmedError, RuntimeError)
    assert issubclass(ApplicationNotConfirmedError, CareerOpsError)

    err = ProtectedAdminError("Protected admin invariant")
    assert "Protected admin" in str(err)
    assert isinstance(err, CareerOpsError)


def test_core_database_init_and_health():
    """Verify core database initialization, table creation, and ping health check."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Ping before init
    assert check_database_health(engine) is True

    # Bootstrap tables and seed admin
    init_db(engine)

    # Verify session generator
    from unittest.mock import patch

    with patch("app.core.database.get_engine", return_value=engine):
        db_gen = get_db()
        session = next(db_gen)
        assert session is not None
        session.close()
