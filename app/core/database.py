"""Centralized database connection and engine management for CareerOps.

Configures resilient connection pooling with pre-ping validation, session factory,
FastAPI dependency injection, and schema bootstrapping across PostgreSQL and SQLite.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create and cache a singleton SQLAlchemy Engine instance with resilient connection pooling.

    Uses `DATABASE_URL` from centralized application settings. Configures
    connection pool health pre-pinging, recycling, and pooling limits.

    Returns:
        Engine: Cached SQLAlchemy Engine connected to the database.

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

    is_sqlite = database_url.startswith("sqlite")
    engine_kwargs: dict = {"pool_pre_ping": True}

    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_recycle": settings.db_pool_recycle,
            }
        )

    return create_engine(database_url, **engine_kwargs)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Create and cache the SQLAlchemy sessionmaker bound to the shared engine.

    Returns:
        sessionmaker: Session factory producing transactional sessions.
    """
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a managed transactional database session.

    Ensures the session is cleanly closed upon request completion.

    Yields:
        Session: Open SQLAlchemy database session.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def check_database_health(engine: Engine | None = None) -> bool:
    """Verify database connectivity by executing a lightweight ping query.

    Args:
        engine: Optional Engine instance (defaults to singleton engine).

    Returns:
        bool: True if connection succeeded; False otherwise.
    """
    db_engine = engine or get_engine()
    try:
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def init_db(engine: Engine | None = None) -> None:
    """Bootstrap complete CareerOps schema, tables, indexes, and seed default admin.

    Supports both PostgreSQL and SQLite dialects automatically.

    Args:
        engine: Optional SQLAlchemy Engine instance.
    """
    from app.core.security import hash_password

    settings = get_settings()
    db_engine = engine or get_engine()
    is_sqlite = db_engine.dialect.name == "sqlite"

    id_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
    time_default = "CURRENT_TIMESTAMP" if is_sqlite else "now()"
    bool_true = "1" if is_sqlite else "true"
    bool_false = "0" if is_sqlite else "false"

    with db_engine.begin() as conn:
        # 1. Tenants table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS tenants (
                    id {id_type},
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    is_active BOOLEAN DEFAULT {bool_true},
                    created_at TIMESTAMP DEFAULT {time_default}
                )
                """
            )
        )

        # 2. Users table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {id_type},
                    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    hashed_password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_default_admin BOOLEAN DEFAULT {bool_false},
                    is_active BOOLEAN DEFAULT {bool_true},
                    created_at TIMESTAMP DEFAULT {time_default},
                    UNIQUE (tenant_id, email)
                )
                """
            )
        )

        # 3. Jobs table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS jobs (
                    id {id_type},
                    source TEXT NOT NULL,
                    source_job_id TEXT,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT,
                    url TEXT NOT NULL,
                    description TEXT NOT NULL,
                    description_hash TEXT UNIQUE,
                    posted_at TIMESTAMP,
                    collected_at TIMESTAMP DEFAULT {time_default},
                    employment_type TEXT,
                    salary_min INTEGER,
                    salary_max INTEGER,
                    status TEXT DEFAULT 'DISCOVERED'
                )
                """
            )
        )

        # 4. Job analysis table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS job_analysis (
                    id {id_type},
                    job_id INTEGER REFERENCES jobs(id),
                    fit_score INTEGER,
                    confidence TEXT,
                    eligible BOOLEAN,
                    strong_matches JSON,
                    missing_skills JSON,
                    risks JSON,
                    analyzed_at TIMESTAMP DEFAULT {time_default}
                )
                """
            )
        )

        # 5. Evidence table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    claim TEXT NOT NULL,
                    category TEXT,
                    source TEXT,
                    verified BOOLEAN DEFAULT {bool_true}
                )
                """
            )
        )

        # 6. Generated documents table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS generated_documents (
                    id {id_type},
                    job_id INTEGER REFERENCES jobs(id),
                    type TEXT,
                    file_path TEXT,
                    version INTEGER DEFAULT 1,
                    claim_check_passed BOOLEAN,
                    ats_check_passed BOOLEAN,
                    created_at TIMESTAMP DEFAULT {time_default}
                )
                """
            )
        )

        # 7. Applications table
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS applications (
                    id {id_type},
                    job_id INTEGER REFERENCES jobs(id),
                    status TEXT DEFAULT 'READY_FOR_REVIEW',
                    applied_at TIMESTAMP,
                    resume_version INTEGER,
                    cover_letter_version INTEGER,
                    notes TEXT
                )
                """
            )
        )

        # 8. Company application history
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS company_application_history (
                    id {id_type},
                    company TEXT NOT NULL,
                    job_id INTEGER REFERENCES jobs(id),
                    applied_at TIMESTAMP,
                    UNIQUE (company, job_id)
                )
                """
            )
        )

        # 9. Performance Indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_collected_at ON jobs(collected_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_job_analysis_job_analyzed ON job_analysis(job_id, analyzed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id)",
            "CREATE INDEX IF NOT EXISTS idx_gen_docs_job_id ON generated_documents(job_id)",
            "CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id)",
        ]
        for idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
            except Exception:
                pass

        # 10. Ensure default tenant exists
        row = conn.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"),
            {"slug": settings.default_tenant_slug},
        ).mappings().first()

        if row is None:
            res = conn.execute(
                text("INSERT INTO tenants (name, slug) VALUES (:name, :slug) RETURNING id"),
                {"name": settings.default_tenant_name, "slug": settings.default_tenant_slug},
            ).mappings().first()
            tenant_id = res["id"]
        else:
            tenant_id = row["id"]

        # 11. Ensure default admin exists
        admin_row = conn.execute(
            text("SELECT id, is_default_admin FROM users WHERE tenant_id = :tenant_id AND email = :email"),
            {"tenant_id": tenant_id, "email": settings.default_admin_email},
        ).mappings().first()

        if admin_row is None:
            hashed_pwd = hash_password(settings.default_admin_password)
            conn.execute(
                text(
                    f"""
                    INSERT INTO users (tenant_id, email, hashed_password, role, is_default_admin, is_active)
                    VALUES (:tenant_id, :email, :hashed_password, 'admin', {bool_true}, {bool_true})
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "email": settings.default_admin_email,
                    "hashed_password": hashed_pwd,
                },
            )
