"""
FastAPI layer for the frontend (see ../../frontend/README.md). Read-heavy
by design: displays what the pipeline already produced, and never
generates documents, scores jobs, or calls Anthropic directly — see
CLAUDE.md's Architecture section for what each route wraps.

Run with: uvicorn app.api.main:app --reload
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import applications, explore, jobs

app = FastAPI(title="CareerOps API")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(explore.router)
