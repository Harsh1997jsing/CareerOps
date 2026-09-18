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

    # Multi-Tenant Stateless JWT Security
    jwt_secret_key: str = "careerops-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    # Protected Default Administrator
    default_admin_email: str = "admin@careerops.local"
    default_admin_password: str = "adminpassword123"
    default_tenant_name: str = "Default Organization"
    default_tenant_slug: str = "default"

    # LLM / Anthropic Service
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Optional MCP Explore Sources
    jobo_mcp_url: str = "https://jobs-mcp.jobo.world/mcp"
    jobo_mcp_api_key: str = ""
    hasdata_mcp_url: str = ""
    hasdata_mcp_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve or initialize cached application Settings singleton.

    Returns:
        Settings: Validated application configuration settings instance.
    """
    return Settings()


# Convenient singleton alias
settings = get_settings()
