"""Multi-tenant stateless JWT authentication and user provisioning endpoints.

Provides routes for user authentication, stateless JWT issuance, profile lookup,
and tenant-scoped administrator operations including user creation and deletion.
Strictly enforces the immutable protection of the default system administrator.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_admin
from app.api.schemas import (
    LoginRequest,
    TenantCreateRequest,
    TenantOut,
    TokenOut,
    UserCreateRequest,
    UserOut,
)
from app.core import get_db, rate_limit
from app.services.auth import (
    InvalidCredentialsError,
    ProtectedAdminError,
    TenantAlreadyExistsError,
    UserAlreadyExistsError,
    UserContext,
    authenticate_user,
    create_access_token,
    create_tenant,
    create_user,
    delete_user,
    get_user_by_id,
    list_users,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(request: LoginRequest, http_request: Request, session: AsyncSession = Depends(get_db)) -> TokenOut:
    """Authenticate user credentials and issue a stateless JWT access token.

    Authenticates the provided email, password, and tenant slug. Issues a
    cryptographically signed JWT bearing user identity and role claims without
    requiring server-side session persistence.

    Rate limited (audit finding F6, via `pyrate-limiter`): 5 attempts per
    client-ip+email within 5 minutes returns 429 before touching the
    database at all — every attempt counts against the budget, not just
    failures (see app/core/rate_limit.py for why).

    Args:
        request: Login payload containing email, password, and optional tenant slug.
        http_request: Raw request, used only for the client IP (rate-limit key).
        session: Database session dependency.

    Returns:
        TokenOut: Encoded bearer token and authenticated user metadata.

    Raises:
        HTTPException: 401 Unauthorized if credentials or tenant are invalid or inactive.
        HTTPException: 429 Too Many Requests if rate limited.
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    rate_limit_key = f"{client_ip}:{request.email.strip().lower()}"

    if not rate_limit.is_allowed(rate_limit_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in a few minutes.",
        )

    try:
        user_context = await authenticate_user(
            session=session,
            email=request.email,
            password=request.password,
            tenant_slug=request.tenant_slug,
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    token_data = {
        "sub": str(user_context.user_id),
        "tenant_id": user_context.tenant_id,
        "tenant_slug": user_context.tenant_slug,
        "email": user_context.email,
        "role": user_context.role,
        "is_default_admin": user_context.is_default_admin,
    }
    access_token = create_access_token(token_data)

    return TokenOut(
        access_token=access_token,
        token_type="bearer",
        tenant_id=user_context.tenant_id,
        tenant_slug=user_context.tenant_slug,
        role=user_context.role,
        email=user_context.email,
    )


@router.get("/me", response_model=UserOut)
async def get_current_user_profile(
    current_user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    """Retrieve full profile details for the currently authenticated user.

    Args:
        current_user: Authenticated user context derived from the JWT bearer token.
        session: Database session dependency.

    Returns:
        UserOut: Current user account attributes.

    Raises:
        HTTPException: 404 Not Found if user account record no longer exists.
    """
    user = await get_user_by_id(session, current_user.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found",
        )
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_tenant_user(
    request: UserCreateRequest,
    current_admin: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    """Provision a new user within the authenticated administrator's tenant.

    Restricted strictly to users with the 'admin' role. All created users are
    strictly bound to the administrator's tenant organization.

    Args:
        request: Payload specifying user email, raw password, and role ('user' or 'admin').
        current_admin: Verified administrator user context.
        session: Database session dependency.

    Returns:
        UserOut: Newly created user record details.

    Raises:
        HTTPException: 400 Bad Request if role or fields are invalid.
        HTTPException: 409 Conflict if email is already registered in the tenant.
    """
    try:
        new_user = await create_user(
            session=session,
            tenant_id=current_admin.tenant_id,
            email=request.email,
            password=request.password,
            role=request.role,
        )
    except UserAlreadyExistsError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    return UserOut.model_validate(new_user, from_attributes=True)


@router.get("/users", response_model=list[UserOut])
async def list_tenant_users(
    current_admin: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    """List all user accounts belonging to the authenticated administrator's tenant.

    Restricted strictly to users with the 'admin' role. Returns only users
    within the tenant organization of the requesting administrator.

    Args:
        current_admin: Verified administrator user context.
        session: Database session dependency.

    Returns:
        list[UserOut]: All active and inactive users in the administrator's tenant.
    """
    users = await list_users(session, tenant_id=current_admin.tenant_id)
    return [UserOut.model_validate(u, from_attributes=True) for u in users]


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_tenant_user(
    user_id: int,
    current_admin: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete a user account from the administrator's tenant.

    Guarantees the system invariant that the default system administrator
    can NEVER be deleted under any circumstances. Non-existent users return 404.

    Args:
        user_id: Target user primary key ID.
        current_admin: Verified administrator user context.
        session: Database session dependency.

    Returns:
        dict[str, Any]: Confirmation containing deletion status and target user ID.

    Raises:
        HTTPException: 403 Forbidden if attempting to delete the protected default admin.
        HTTPException: 404 Not Found if user does not exist in this tenant.
    """
    try:
        deleted = await delete_user(session, tenant_id=current_admin.tenant_id, user_id=user_id)
    except ProtectedAdminError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this tenant organization",
        )

    return {"deleted": True, "user_id": user_id}


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_new_tenant(
    request: TenantCreateRequest,
    current_admin: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> TenantOut:
    """Create a new tenant organization.

    Restricted strictly to users with the 'admin' role.

    Args:
        request: Payload containing organization display name and unique slug.
        current_admin: Verified administrator user context.
        session: Database session dependency.

    Returns:
        TenantOut: Newly registered tenant details.

    Raises:
        HTTPException: 409 Conflict if tenant slug already exists.
    """
    try:
        tenant = await create_tenant(session=session, name=request.name, slug=request.slug)
    except TenantAlreadyExistsError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err

    return TenantOut.model_validate(tenant, from_attributes=True)
