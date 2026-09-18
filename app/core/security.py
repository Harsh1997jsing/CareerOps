"""Centralized cryptographic and security primitives for CareerOps.

Provides PBKDF2-HMAC-SHA256 password hashing (100,000 iterations, 16-byte random salt)
and stateless JWT token issuance/validation without session storage.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError

PBKDF2_ITERATIONS = 100_000


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


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed, stateless JWT access token.

    Args:
        data: Dictionary of claims to encode in the token payload.
        expires_delta: Optional custom expiration timedelta.

    Returns:
        str: Encoded JWT access token string.
    """
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Args:
        token: Encoded JWT string.

    Returns:
        dict[str, Any]: Decoded payload claims dictionary.

    Raises:
        TokenExpiredError: If token expiration timestamp (`exp`) has passed.
        InvalidTokenError: If token signature is invalid or token is malformed.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError("Access token has expired") from e
    except jwt.PyJWTError as e:
        raise InvalidTokenError("Invalid access token") from e
