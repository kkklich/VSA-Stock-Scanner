"""Application configuration.

Settings are read from environment variables (optionally from a local ``.env``
file). This mirrors the .NET backend's ``appsettings.json`` + ``Cors`` section.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend-python/ — this file lives at backend-python/app/config.py.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


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

    # ── Action log (audit trail) ──────────────────────────────────────────────
    # Every API call and every background job is recorded: what was done, when,
    # how long it took and how it ended. See app/services/action_log.py.

    # Master switch. False disables recording entirely (no file, no DB, no
    # in-memory buffer) — the middleware then costs one boolean check.
    action_log_enabled: bool = True

    # Where the rotating JSON-lines file is written. A relative path is
    # resolved against the backend-python/ directory (the package root), so the
    # location does not depend on the shell's working directory.
    action_log_dir: str = "logs"

    # Write the JSON-lines file at all. Turned off in the test suite.
    action_log_to_file: bool = True

    # Rotation: actions.jsonl grows to this size, then becomes actions.jsonl.1
    # and a new file starts. At most `backups` old files are kept, so the log
    # occupies at most (backups + 1) x max_bytes on disk.
    action_log_file_max_bytes: int = 10 * 1024 * 1024
    action_log_file_backups: int = 5

    # Mirror every entry into the `action_logs` table when a DB is configured.
    # Writes are queued and batched off the request path.
    action_log_to_db: bool = True

    # Stored rows older than this are deleted by a daily prune, so the audit
    # trail cannot grow without bound. 0 disables pruning (keep everything).
    action_log_retention_days: int = 30

    # How many recent entries stay in memory for GET /api/admin/logs when no
    # database is configured (the app runs stateless without one).
    action_log_memory_entries: int = 2000

    # Paths that are NOT recorded. /health is polled every 30s by the Docker
    # healthcheck; logging it would bury the real actions in noise.
    action_log_exclude_paths: list[str] = ["/health"]

    # ── Error tracking + admin access ─────────────────────────────────────────

    # Capture every ERROR-level log line as a grouped, counted error
    # (app/services/error_tracker.py), readable at GET /api/admin/errors.
    # False disables the capture entirely.
    error_tracking_enabled: bool = True

    # How many distinct error groups are kept in memory. Beyond this the
    # least-recently-seen group is dropped, so a flood of unique errors cannot
    # grow the process without bound.
    error_tracking_max_groups: int = 200

    # Optional shared secret for /api/admin/*. When set, those endpoints
    # require an `X-Admin-Token` header matching it; when empty they are open,
    # which is fine locally but NOT on a public deployment — the admin screens
    # carry stack traces and caller IP addresses. GET /api/admin/health reports
    # `protected: false` when this is unset so the UI can warn about it.
    admin_token: str = ""

    @property
    def action_log_path(self) -> Path:
        """Absolute directory the action-log file is written to.

        A relative ``action_log_dir`` is anchored to the backend-python/
        package root rather than to the process's working directory, so the
        file lands in the same place whether the app is started from the repo
        root, from backend-python/, or by the run-backend-python.bat script.
        """
        configured = Path(self.action_log_dir)
        if configured.is_absolute():
            return configured
        return _PACKAGE_ROOT / configured

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
