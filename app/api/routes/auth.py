"""Multi-tenant stateless JWT authentication and user provisioning endpoints.

Provides routes for user authentication, stateless JWT issuance, profile lookup,
and tenant-scoped administrator operations including user creation and deletion.
Strictly enforces the immutable protection of the default system administrator.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import Engine

from app.api.dependencies import get_current_user, get_db_engine, require_admin
from app.api.schemas import (
    LoginRequest,
    TenantCreateRequest,
    TenantOut,
    TokenOut,
    UserCreateRequest,
    UserOut,
)
from app.services.auth import (
    InvalidCredentialsError,
    ProtectedAdminError,
    Tenant,
    TenantAlreadyExistsError,
    User,
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


def _format_datetime(dt: Any) -> str | None:
    """Format datetime value into an ISO-8601 string across DB dialects.

    Args:
        dt: Datetime object, timestamp string, or None.

    Returns:
        str | None: Formatted string or None.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _user_to_out(user: User) -> UserOut:
    """Convert an internal User domain entity to a UserOut response schema.

    Args:
        user: User dataclass instance.

    Returns:
        UserOut: Formatted Pydantic response schema.
    """
    return UserOut(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
        is_default_admin=user.is_default_admin,
        is_active=user.is_active,
        created_at=_format_datetime(user.created_at),
    )


def _tenant_to_out(tenant: Tenant) -> TenantOut:
    """Convert an internal Tenant domain entity to a TenantOut response schema.

    Args:
        tenant: Tenant dataclass instance.

    Returns:
        TenantOut: Formatted Pydantic response schema.
    """
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        is_active=tenant.is_active,
        created_at=_format_datetime(tenant.created_at),
    )


@router.post("/login", response_model=TokenOut)
def login(request: LoginRequest, engine: Engine = Depends(get_db_engine)) -> TokenOut:
    """Authenticate user credentials and issue a stateless JWT access token.

    Authenticates the provided email, password, and tenant slug. Issues a
    cryptographically signed JWT bearing user identity and role claims without
    requiring server-side session persistence.

    Args:
        request: Login payload containing email, password, and optional tenant slug.
        engine: SQLAlchemy Engine dependency.

    Returns:
        TokenOut: Encoded bearer token and authenticated user metadata.

    Raises:
        HTTPException: 401 Unauthorized if credentials or tenant are invalid or inactive.
    """
    try:
        user_context = authenticate_user(
            engine=engine,
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
def get_current_user_profile(
    current_user: UserContext = Depends(get_current_user),
    engine: Engine = Depends(get_db_engine),
) -> UserOut:
    """Retrieve full profile details for the currently authenticated user.

    Args:
        current_user: Authenticated user context derived from the JWT bearer token.
        engine: SQLAlchemy Engine dependency.

    Returns:
        UserOut: Current user account attributes.

    Raises:
        HTTPException: 404 Not Found if user account record no longer exists.
    """
    user = get_user_by_id(engine, current_user.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found",
        )
    return _user_to_out(user)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_tenant_user(
    request: UserCreateRequest,
    current_admin: UserContext = Depends(require_admin),
    engine: Engine = Depends(get_db_engine),
) -> UserOut:
    """Provision a new user within the authenticated administrator's tenant.

    Restricted strictly to users with the 'admin' role. All created users are
    strictly bound to the administrator's tenant organization.

    Args:
        request: Payload specifying user email, raw password, and role ('user' or 'admin').
        current_admin: Verified administrator user context.
        engine: SQLAlchemy Engine dependency.

    Returns:
        UserOut: Newly created user record details.

    Raises:
        HTTPException: 400 Bad Request if role or fields are invalid.
        HTTPException: 409 Conflict if email is already registered in the tenant.
    """
    try:
        new_user = create_user(
            engine=engine,
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

    return _user_to_out(new_user)


@router.get("/users", response_model=list[UserOut])
def list_tenant_users(
    current_admin: UserContext = Depends(require_admin),
    engine: Engine = Depends(get_db_engine),
) -> list[UserOut]:
    """List all user accounts belonging to the authenticated administrator's tenant.

    Restricted strictly to users with the 'admin' role. Returns only users
    within the tenant organization of the requesting administrator.

    Args:
        current_admin: Verified administrator user context.
        engine: SQLAlchemy Engine dependency.

    Returns:
        list[UserOut]: All active and inactive users in the administrator's tenant.
    """
    users = list_users(engine, tenant_id=current_admin.tenant_id)
    return [_user_to_out(u) for u in users]


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
def delete_tenant_user(
    user_id: int,
    current_admin: UserContext = Depends(require_admin),
    engine: Engine = Depends(get_db_engine),
) -> dict[str, Any]:
    """Delete a user account from the administrator's tenant.

    Guarantees the system invariant that the default system administrator
    can NEVER be deleted under any circumstances. Non-existent users return 404.

    Args:
        user_id: Target user primary key ID.
        current_admin: Verified administrator user context.
        engine: SQLAlchemy Engine dependency.

    Returns:
        dict[str, Any]: Confirmation containing deletion status and target user ID.

    Raises:
        HTTPException: 403 Forbidden if attempting to delete the protected default admin.
        HTTPException: 404 Not Found if user does not exist in this tenant.
    """
    try:
        deleted = delete_user(engine, tenant_id=current_admin.tenant_id, user_id=user_id)
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
def create_new_tenant(
    request: TenantCreateRequest,
    current_admin: UserContext = Depends(require_admin),
    engine: Engine = Depends(get_db_engine),
) -> TenantOut:
    """Create a new tenant organization.

    Restricted strictly to users with the 'admin' role.

    Args:
        request: Payload containing organization display name and unique slug.
        current_admin: Verified administrator user context.
        engine: SQLAlchemy Engine dependency.

    Returns:
        TenantOut: Newly registered tenant details.

    Raises:
        HTTPException: 409 Conflict if tenant slug already exists.
    """
    try:
        tenant = create_tenant(engine=engine, name=request.name, slug=request.slug)
    except TenantAlreadyExistsError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err

    return _tenant_to_out(tenant)
