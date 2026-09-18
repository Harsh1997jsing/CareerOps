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
    """Create and cache a singleton SQLAlchemy Engine instance.

    Uses the connection string specified in the `DATABASE_URL` environment
    variable. Caches the engine instance to ensure callers across the application
    share a single connection pool.

    Returns:
        Engine: A cached SQLAlchemy Engine connected to the database.

    Raises:
        KeyError: If the `DATABASE_URL` environment variable is not defined.
    """
    return create_engine(os.environ["DATABASE_URL"])
