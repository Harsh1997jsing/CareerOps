"""Backward-compatible database module forwarding to app.core.database."""

from app.core.database import check_database_health, get_db, get_engine, init_db

__all__ = ["get_engine", "get_db", "init_db", "check_database_health"]
