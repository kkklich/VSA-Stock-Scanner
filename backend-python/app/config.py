"""Application configuration.

Settings are read from environment variables (optionally from a local ``.env``
file). This mirrors the .NET backend's ``appsettings.json`` + ``Cors`` section.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, populated from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="STOCKPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # CORS — origins allowed to call the API (the Vite dev server defaults to 5173).
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    # How long per-ticker history and the computed ranking stay cached, in
    # seconds. 24h: market data changes once per day (after the GPW close), so
    # outside the nightly job / manual Refresh nothing needs recomputing. The
    # refresh pipeline clears these caches explicitly when new data arrives.
    history_cache_seconds: int = 24 * 60 * 60

    # Outbound HTTP timeout for stooq.pl requests, in seconds.
    stooq_timeout_seconds: float = 30.0

    # Async PostgreSQL connection URL (asyncpg driver, used at runtime).
    # Override via STOCKPILOT_DATABASE_URL environment variable.
    # Set to empty string to disable DB persistence (app falls back to live stooq.pl only).
    database_url: str = ""

    # Daily ingest trigger time (Europe/Warsaw timezone).
    # GPW closes at 17:05; we run at 18:00 to give stooq.pl time to publish EOD data.
    ingest_hour: int = 18
    ingest_minute: int = 0

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic (psycopg2 instead of asyncpg)."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg2://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        raise ValueError(
            f"Unsupported DATABASE_URL format: {url!r}. "
            "Expected postgresql+asyncpg:// or postgresql://"
        )

    @property
    def db_enabled(self) -> bool:
        """True when a database URL is configured."""
        return bool(self.database_url)


# A single shared settings instance for the whole app.
settings = Settings()
