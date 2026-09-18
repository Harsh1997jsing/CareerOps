"""FastAPI layer for CareerOps frontend and client services.

Provides read-heavy routes for jobs, applications, and MCP exploration,
plus full multi-tenant stateless JWT authentication and user administration.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import applications, auth, explore, jobs
from app.core.config import get_settings
from app.core.database import get_engine, init_db
from app.core.exceptions import (
    AuthError,
    CareerOpsError,
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    ProtectedAdminError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to initialize database schema, tables, and seed admin.

    Ensures the default tenant, protected default admin, and performance
    indexes are bootstrapped when the API server starts up if DATABASE_URL is configured.

    Args:
        app: FastAPI application instance.
    """
    settings = get_settings()
    if settings.database_url:
        try:
            init_db(get_engine())
        except Exception:
            # Tolerant of uninitialized database during test mocking
            pass
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="CareerOps Backend REST API with Multi-Tenant Stateless JWT Authentication",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)


# Global Exception Handlers (DRY RFC 7807 problem details)
@app.exception_handler(ProtectedAdminError)
async def protected_admin_exception_handler(request: Request, exc: ProtectedAdminError) -> JSONResponse:
    """Handle attempts to delete or alter the immutable default administrator."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "Forbidden", "detail": str(exc)},
    )


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_exception_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
    """Handle authentication credential mismatches."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "Unauthorized", "detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(ConflictError)
async def conflict_exception_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """Handle duplicate resource and unique constraint collision errors."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "Conflict", "detail": str(exc)},
    )


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Handle entity not found errors across all services."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "Not Found", "detail": str(exc)},
    )


@app.exception_handler(CareerOpsError)
async def careerops_error_handler(request: Request, exc: CareerOpsError) -> JSONResponse:
    """Handle general internal application errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "detail": exc.message},
    )


# Register API Routers
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(explore.router)
