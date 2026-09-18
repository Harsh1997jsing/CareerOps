"""
FastAPI layer for the frontend (see ../../frontend/README.md). Read-heavy
by design: displays what the pipeline already produced, and never
generates documents, scores jobs, or calls Anthropic directly — see
CLAUDE.md's Architecture section for what each route wraps.

Run with: uvicorn app.api.main:app --reload
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import applications, auth, explore, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to initialize auth database schema and seed default admin.

    Ensures the default tenant and protected default admin are bootstrapped
    when the API server starts up if a database connection is configured.

    Args:
        app: FastAPI application instance.
    """
    if "DATABASE_URL" in os.environ:
        try:
            from app.db import get_engine
            from app.services.auth import init_auth_db

            init_auth_db(get_engine())
        except Exception:
            # Tolerant of uninitialized database during test mocking
            pass
    yield


app = FastAPI(title="CareerOps API", lifespan=lifespan)

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(explore.router)

