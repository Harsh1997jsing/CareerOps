from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine

from app.db import get_engine
from app.services.auth import (
    InvalidTokenError,
    TokenExpiredError,
    UserContext,
    decode_access_token,
    get_user_by_id,
)

security_bearer = HTTPBearer(auto_error=False)


def get_db_engine() -> Engine:
    """FastAPI dependency that provides the shared SQLAlchemy database Engine.

    Returns:
        Engine: Shared database engine instance for executing queries.
    """
    return get_engine()


def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Security(security_bearer),
    engine: Engine = Depends(get_db_engine),
) -> UserContext:
    """FastAPI dependency to extract and authenticate the current user from stateless JWT.

    Validates bearer token, verifies expiration, and checks user account activity.

    Args:
        auth: Bearer token credentials from Authorization header.
        engine: Database engine dependency.

    Returns:
        UserContext: Context containing user_id, tenant_id, tenant_slug, email, and role.

    Raises:
        HTTPException: 401 Unauthorized if token is missing, invalid, or expired.
        HTTPException: 403 Forbidden if user account is deactivated.
    """
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(engine, user_id_int)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        tenant_slug=payload.get("tenant_slug", "default"),
        email=user.email,
        role=user.role,
        is_default_admin=user.is_default_admin,
    )


def require_admin(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """FastAPI dependency to restrict endpoints strictly to users with the 'admin' role.

    Args:
        current_user: Authenticated user context.

    Returns:
        UserContext: Verified administrator context.

    Raises:
        HTTPException: 403 Forbidden if the authenticated user is not an administrator.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required for this action",
        )
    return current_user

