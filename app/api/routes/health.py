"""Health check endpoint (audit finding F9 — check_database_health() already
existed in app/core/database.py but nothing called it; no route exposed it).
Deliberately unauthenticated: a health check needs to work before a caller
has a token, and a load balancer / orchestrator probing it isn't a user.
"""

from fastapi import APIRouter

from app.core.database import check_database_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Report service and database connectivity status.

    Returns:
        dict: `{"status": "ok" | "degraded", "database": "ok" | "unreachable"}`.
            Always returns 200 — a monitoring probe should read the body,
            not just the status code, to distinguish "up but DB down" from
            fully healthy.
    """
    database_ok = await check_database_health()
    return {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "unreachable",
    }
