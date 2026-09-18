"""Aggregates every route module into one router `main.py` mounts once."""

from fastapi import APIRouter

from app.api.routes import applications, auth, explore, health, jobs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(explore.router)
