"""
Thin SQLAlchemy engine wrapper so every caller shares one engine/connection
pool instead of each opening its own against DATABASE_URL.
"""

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create and cache a singleton SQLAlchemy Engine instance with connection pooling.

    Uses the connection string specified in the `DATABASE_URL` environment
    variable. Configures connection pool resilience with pre-ping validation,
    connection recycling, and pool size limits.

    Returns:
        Engine: A cached SQLAlchemy Engine connected to the database.

    Raises:
        RuntimeError: If the `DATABASE_URL` environment variable is not defined.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Please configure DATABASE_URL in your .env or system environment."
        )

    is_sqlite = database_url.startswith("sqlite")
    engine_kwargs: dict = {"pool_pre_ping": True}

    # QueuePool parameters are applicable only to non-SQLite database engines
    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
                "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
                "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "3600")),
            }
        )

    return create_engine(database_url, **engine_kwargs)
