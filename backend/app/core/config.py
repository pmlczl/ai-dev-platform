"""Application configuration.

Every runtime setting is read from environment variables (12-factor style).
Secrets are never hard-coded: the database password comes from
``POSTGRES_PASSWORD`` or from a full ``DATABASE_URL`` override that is supplied
by the deployment environment (``.env`` for local development, Docker Compose
environment for containers).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Directory that contains the backend package (``backend/``).
BACKEND_DIR = Path(__file__).resolve().parents[2]
#: Repository root, one level above ``backend/``.
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings container backed by environment variables."""

    model_config = SettingsConfigDict(
        # Absolute paths: a relative "env_file" is resolved against the current
        # working directory, so the same dotenv file would be picked up from one
        # directory and ignored from another. The backend dotenv is listed last
        # on purpose - pydantic-settings lets later files override earlier ones.
        env_file=(
            str(PROJECT_ROOT / ".env"),
            str(BACKEND_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "AI Dev Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"

    # --- Logging ---------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # --- CORS ------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    # --- Database --------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_db: str = "ai_dev_platform"
    database_url: str | None = None
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True

    # --- Derived helpers -------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        """Allowed CORS origins parsed from a comma separated environment value."""

        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cors_method_list(self) -> list[str]:
        return [method.strip() for method in self.cors_allow_methods.split(",") if method.strip()]

    @property
    def cors_header_list(self) -> list[str]:
        return [header.strip() for header in self.cors_allow_headers.split(",") if header.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Async SQLAlchemy DSN.

        ``DATABASE_URL`` wins when present; otherwise the DSN is assembled from
        the discrete ``POSTGRES_*`` variables so that the password never has to
        live in source code.
        """

        if self.database_url:
            return self.database_url
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def masked_database_uri(self) -> str:
        """Database URI with the password replaced by ``***`` (safe for logs)."""

        return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", self.sqlalchemy_database_uri)

    @property
    def uses_sqlite(self) -> bool:
        """True when the configured DSN targets SQLite (used by local smoke tests)."""

        return self.sqlalchemy_database_uri.startswith("sqlite")

    def runtime_errors(self) -> list[str]:
        """Configuration problems that must stop a production deployment."""

        errors: list[str] = []
        if self.environment.lower() == "production":
            if not self.database_url and not self.postgres_password:
                errors.append(
                    "POSTGRES_PASSWORD (or DATABASE_URL) must be provided in production"
                )
            if self.debug:
                errors.append("DEBUG must be disabled in production")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton."""

    return Settings()
