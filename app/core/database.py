"""Centralized async database connection and engine management for CareerOps.

Configures resilient connection pooling with pre-ping validation, an async
session factory, FastAPI dependency injection, and dev/test schema
bootstrapping across PostgreSQL and SQLite. Runtime queries go through an
async engine (`asyncpg` for Postgres, `aiosqlite` for SQLite); Alembic
migrations (migrations/env.py) deliberately keep using the plain sync
`DATABASE_URL` — a one-off CLI process has no need for an async driver,
and it avoids asyncpg/alembic integration entirely.

Schema ownership: app/models/ (SQLAlchemy ORM declarative models) is the
single source of truth for table shape; migrations/ (Alembic) is how that
schema reaches a real database. `init_db()`'s `Base.metadata.create_all()`
call is a dev/test convenience only — idempotent and safe to run alongside
Alembic, but it will never apply a schema *change* to an existing table
the way a migration does. A real deployment should run `alembic upgrade
head`, not rely on this.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError
from app.models import Base, Tenant, User


def _to_async_url(database_url: str) -> str:
    """Upgrades a plain DATABASE_URL to its async-driver equivalent.

    Lets `.env`'s DATABASE_URL stay in the ordinary `postgresql://...` /
    `sqlite:///...` form everyone (Alembic, `psql`, docs) expects — this is
    the only place that needs to know the runtime uses asyncpg/aiosqlite.
    A URL that already names a driver (`postgresql+asyncpg://`, a custom
    dialect) passes through unchanged.
    """
    if database_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + database_url[len("postgresql://"):]
    if database_url.startswith("postgres://"):
        return "postgresql+asyncpg://" + database_url[len("postgres://"):]
    if database_url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + database_url[len("sqlite://"):]
    return database_url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create and cache a singleton async SQLAlchemy Engine with resilient connection pooling.

    Uses `DATABASE_URL` from centralized application settings. Configures
    connection pool health pre-pinging, recycling, and pooling limits.

    Returns:
        AsyncEngine: Cached async SQLAlchemy Engine connected to the database.

    Raises:
        ConfigurationError: If the `DATABASE_URL` setting is empty or undefined.
    """
    settings = get_settings()
    database_url = settings.database_url
    if not database_url:
        raise ConfigurationError(
            "DATABASE_URL environment variable is not set. "
            "Please configure DATABASE_URL in your .env or environment."
        )

    async_url = _to_async_url(database_url)
    is_sqlite = async_url.startswith("sqlite")
    engine_kwargs: dict = {"pool_pre_ping": True}

    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_recycle": settings.db_pool_recycle,
            }
        )

    return create_async_engine(async_url, **engine_kwargs)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create and cache the async sessionmaker bound to the shared engine.

    `expire_on_commit=False` — the default (True) expires every attribute
    after commit, and re-reading one afterward would silently try to
    lazy-load it, which fails outside an awaited context (SQLAlchemy's
    "greenlet_spawn has not been called" error). Standard practice for
    async SQLAlchemy: turn it off, accept slightly-stale in-memory values
    after a commit within the same request.

    Returns:
        async_sessionmaker: Session factory producing transactional async sessions.
    """
    engine = get_engine()
    return async_sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a managed transactional async database session.

    Ensures the session is cleanly closed upon request completion.

    Yields:
        AsyncSession: Open async database session.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def check_database_health(engine: AsyncEngine | None = None) -> bool:
    """Verify database connectivity by executing a lightweight ping query.

    Args:
        engine: Optional AsyncEngine instance (defaults to singleton engine).

    Returns:
        bool: True if connection succeeded; False otherwise — including if
            `DATABASE_URL` isn't configured at all (get_engine() raises
            ConfigurationError in that case). A health check must report
            "not healthy," never crash, on a misconfigured deployment —
            this used to call get_engine() outside the try/except.
    """
    try:
        db_engine = engine or get_engine()
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create tables (dev/test convenience — see module docstring) and seed the
    default tenant + protected default admin if they don't already exist.

    Args:
        engine: Optional async SQLAlchemy Engine instance.
    """
    from app.core.security import hash_password

    settings = get_settings()
    db_engine = engine or get_engine()

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
        if tenant is None:
            tenant = Tenant(name=settings.default_tenant_name, slug=settings.default_tenant_slug)
            session.add(tenant)
            await session.flush()

        admin = await session.scalar(
            select(User).where(User.tenant_id == tenant.id, User.email == settings.default_admin_email)
        )
        if admin is None:
            session.add(
                User(
                    tenant_id=tenant.id,
                    email=settings.default_admin_email,
                    hashed_password=hash_password(settings.default_admin_password),
                    role="admin",
                    is_default_admin=True,
                    is_active=True,
                )
            )
