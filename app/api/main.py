"""FastAPI layer for CareerOps frontend and client services.

Provides read-heavy routes for jobs, applications, and MCP exploration,
plus full multi-tenant stateless JWT authentication and user administration.
"""

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.database import get_engine, init_db
from app.core.exceptions import (
    CareerOpsError,
    ConflictError,
    InvalidCredentialsError,
    LLMServiceError,
    ProtectedAdminError,
)

logger = logging.getLogger(__name__)


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
            await init_db(get_engine())
        except Exception:
            # Don't crash the whole process over a startup-time DB hiccup
            # (e.g. Postgres not up yet in a container's startup race) —
            # but never swallow it silently; a real failure here means
            # every route that touches the DB will fail too.
            logger.exception("init_db() failed during startup")
    yield


def _cors_origins(frontend_origin: str) -> list[str]:
    """Expand a configured frontend origin to cover its localhost/127.0.0.1 twin.

    The browser treats "http://localhost:5173" and "http://127.0.0.1:5173"
    as different origins even though they're the same dev server — whichever
    one a user happens to type/click gets silently CORS-blocked if only the
    other is allow-listed. `allow_origins` can't use a wildcard here since
    `allow_credentials=True` is set (the CORS spec forbids combining `*`
    with credentialed requests), so both concrete variants are listed
    instead of trying to make one env var cover both forms itself.

    Args:
        frontend_origin: The configured FRONTEND_ORIGIN value.

    Returns:
        list[str]: `[frontend_origin]`, plus its localhost/127.0.0.1 twin if
            its hostname is one of those two.
    """
    parsed = urlparse(frontend_origin)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        return [frontend_origin]
    port = f":{parsed.port}" if parsed.port else ""
    twin_host = "127.0.0.1" if parsed.hostname == "localhost" else "localhost"
    return [frontend_origin, f"{parsed.scheme}://{twin_host}{port}"]


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
    allow_origins=_cors_origins(settings.frontend_origin),
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)


# Global exception handlers. Every one of these — including the catch-all
# at the bottom — returns {"detail": "..."} (CONTRACT.md's documented error
# shape), the same shape FastAPI's own HTTPException handler already uses.
# ProtectedAdminError/InvalidCredentialsError/ConflictError are real,
# raised exception types (see app/services/auth.py) that today are always
# caught and converted to HTTPException locally in routes/auth.py first —
# these handlers are defense-in-depth for a route that ever forgets to,
# not currently load-bearing for auth.py's own routes.
@app.exception_handler(ProtectedAdminError)
async def protected_admin_exception_handler(request: Request, exc: ProtectedAdminError) -> JSONResponse:
    """Handle attempts to delete or alter the immutable default administrator."""
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_exception_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
    """Handle authentication credential mismatches."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(ConflictError)
async def conflict_exception_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """Handle duplicate resource and unique constraint collision errors."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(LLMServiceError)
async def llm_service_error_handler(request: Request, exc: LLMServiceError) -> JSONResponse:
    """Handle a failed/malformed Claude API call (see structured_call())."""
    logger.warning("LLM service error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)})


@app.exception_handler(CareerOpsError)
async def careerops_error_handler(request: Request, exc: CareerOpsError) -> JSONResponse:
    """Handle any other internal application error (e.g. ConfigurationError)."""
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for anything not covered above (a raw SQLAlchemy/anthropic/
    stdlib exception) so the client always gets JSON, never Starlette's
    default plain-text 500 — which is what `debug=False` (this app's
    default; `Settings.debug` is never actually passed to `FastAPI(...)`)
    otherwise produces for any unhandled exception. Logs the real
    exception server-side; never leaks its details to the client.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"})


# Register API Routers
app.include_router(api_router)
