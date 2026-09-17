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
    return create_engine(os.environ["DATABASE_URL"])
