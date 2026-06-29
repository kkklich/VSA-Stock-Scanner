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

    # How long per-ticker stooq history stays cached, in seconds (6h, matching .NET).
    history_cache_seconds: int = 6 * 60 * 60

    # Outbound HTTP timeout for stooq.pl requests, in seconds.
    stooq_timeout_seconds: float = 30.0


# A single shared settings instance for the whole app.
settings = Settings()
