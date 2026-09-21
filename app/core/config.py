"""Centralized application configuration management for CareerOps.

Uses Pydantic Settings to load, validate, and provide strongly-typed configuration
from environment variables and `.env` files across the entire application.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime configuration settings."""

    # Application metadata
    app_name: str = "CareerOps API"
    environment: str = "development"
    debug: bool = False

    # Database connection & pooling
    database_url: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600

    # Frontend CORS origin
    frontend_origin: str = "http://localhost:5173"

    # Multi-Tenant Stateless JWT Security — no defaults: a secret or admin
    # password sitting in source control isn't a default, it's a published
    # credential. Required in .env; Settings() raises at startup if unset
    # rather than silently booting with a known-in-source secret.
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    # 8h, not 24h — this is a stateless JWT with no revocation/blocklist,
    # so a leaked token is valid until it expires, full stop. Shortening
    # the default reduces that window; a real fix would add a refresh-token
    # flow (audit finding F5), out of scope for this pass.
    jwt_access_token_expire_minutes: int = 480

    # Protected Default Administrator
    default_admin_email: str = "admin@careerops.local"
    default_admin_password: str
    default_tenant_name: str = "Default Organization"
    default_tenant_slug: str = "default"

    # LLM / Anthropic Service
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Optional MCP Explore Sources
    jobo_mcp_url: str = "https://jobs-mcp.jobo.world/mcp"
    jobo_mcp_api_key: str = ""
    hasdata_mcp_url: str = ""
    hasdata_mcp_api_key: str = ""

    # Candidate data files — the single source of truth for these paths,
    # so job_scorer/resume_generator/cover_letter/ats_validator callers
    # (app/services/document_generator.py, app/api/routes/jobs.py) don't
    # each hardcode "data/...yaml" separately.
    skills_path: str = "data/skills.yaml"
    evidence_path: str = "data/evidence.yaml"
    constraints_path: str = "data/constraints.yaml"
    profile_path: str = "data/profile.yaml"
    voice_samples_dir: str = "data/voice_samples"
    # Where generated .docx files are written — local-first (CLAUDE.md
    # rule 1), so this is a path on the same machine the browser runs on,
    # not something served back over HTTP.
    documents_dir: str = "data/generated_documents"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve or initialize cached application Settings singleton.

    Deliberately not evaluated at import time (no module-level `settings =
    get_settings()`) — required fields like `jwt_secret_key` would then
    raise as a side effect of merely importing this module, including
    during test collection for code that has nothing to do with auth.

    Returns:
        Settings: Validated application configuration settings instance.
    """
    return Settings()
