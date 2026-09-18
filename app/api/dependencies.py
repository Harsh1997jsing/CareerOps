from sqlalchemy.engine import Engine

from app.db import get_engine


def get_db_engine() -> Engine:
    """FastAPI dependency that provides the shared SQLAlchemy database Engine.

    Returns:
        Engine: Shared database engine instance for executing queries.
    """
    return get_engine()
