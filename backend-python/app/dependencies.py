"""Shared application objects and FastAPI dependency providers.

Singletons created once in the app lifespan (``main.py``) and accessed here:

    GpwCompanyService   — company seed data (JSON file, read-only).
    httpx.AsyncClient   — shared HTTP client for all stooq.pl traffic.
    StooqClient         — wraps the shared HTTP client.
    YahooFinanceClient  — the market-data client every endpoint reads through.
    TTLCache × 2        — in-memory caches for per-ticker history and the
                          full ranking list.
    QuoteRepository     — optional persistence layer; None when no DATABASE_URL
                          is configured (app falls back to live stooq.pl).
    ActionLogService    — the audit trail: every API call and background job,
                          written to a rotating file and (when a DB exists) to
                          the action_logs table.
    ErrorTracker        — grouped, counted errors: every ERROR-level log line
                          in the app, readable at GET /api/admin/errors.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.config import settings
from app.db.action_log_repository import ActionLogRepository
from app.db.health_repository import DataHealthRepository
from app.db.repository import QuoteRepository
from app.services.action_log import ActionLogService
from app.services.cache import TTLCache
from app.services.error_tracker import ErrorTracker
from app.services.gpw_company_service import GpwCompanyService
from app.services.yahoo_finance_client import YahooFinanceClient

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ── Process-wide singletons ───────────────────────────────────────────────────

gpw_company_service = GpwCompanyService()

# The market-data client. One instance for the whole process, as the docstrings
# in this module have always claimed — it used to hand out a fresh
# YahooFinanceClient per request, which happened to be harmless (the download
# semaphore is class-level, so the concurrency limit held anyway) but made the
# code read as if a per-request object mattered when nothing about it does.
yahoo_client = YahooFinanceClient()

# Per-ticker OHLCV history, keyed "history:{ticker}:{from}:{to}".
# The larger of the two bounds: the three full-universe scans keep one entry per
# tracked company each (~290 × 3), and each stock page a visitor opens adds a
# few more for its own chart ranges and intraday bar sizes.
history_cache: TTLCache = TTLCache(max_entries=4096)

# Pre-computed analysis results, keyed by endpoint + settings hash: the full
# ranking list ("ranking…"), scanner stats ("scanner:stats…"), the heatmap
# ("heatmap…"), the volume-surge scan, the capex screen and the per-method
# back-tests all live here so the nightly refresh invalidates them together.
#
# The bound has to be counted in MEMORY, not in entries. One ranking entry is
# ~290 StockRankingItem objects, each carrying every registered method's result
# plus the 52-week and weekly fields — call it a few MB. The settings hash in
# the key comes from the query string, so a client varying it fills this cache
# with whole ranked universes; at 256 entries that is tens of thousands of rich
# Pydantic models retained at once, hundreds of MB in the single-worker
# production container. 32 leaves room for everything the app itself keeps
# warm (one entry per endpoint for the default settings, a few method
# back-tests, a couple of volume-surge parameter sets) plus a handful of
# settings variants. Past that the least-recently-used entry is evicted and
# whoever wants it pays one recomputation — much the better trade.
ranking_cache: TTLCache = TTLCache(max_entries=32)

# The action log (audit trail). Created here rather than in the lifespan so
# that a request arriving while the app is still starting up — or a test that
# never runs the lifespan at all — still has somewhere to record. The lifespan
# opens its file and attaches the database writer.
action_log = ActionLogService(
    enabled=settings.action_log_enabled,
    to_file=settings.action_log_to_file,
    directory=settings.action_log_path,
    file_max_bytes=settings.action_log_file_max_bytes,
    file_backups=settings.action_log_file_backups,
    memory_entries=settings.action_log_memory_entries,
    exclude_paths=settings.action_log_exclude_paths,
)

# Error tracking (app/services/error_tracker.py). Created here for the same
# reason as the action log: something has to be able to record a failure that
# happens while the app is still starting up. The lifespan attaches it to the
# root logger and hands it the action log so its groups are persisted too.
error_tracker = ErrorTracker(
    enabled=settings.error_tracking_enabled,
    action_log=action_log,
    max_groups=settings.error_tracking_max_groups,
)

# When this process started — the uptime shown on the system-health screen.
# Module import time is close enough to the start and needs no wiring.
APP_STARTED_AT = datetime.now(tz=UTC)

_http_client: httpx.AsyncClient | None = None

# Set during lifespan when DATABASE_URL is configured; None otherwise.
_quote_repository: QuoteRepository | None = None

# The refresh pipeline (Yahoo ingest → ranking → rating snapshots). Created in
# the lifespan; typed loosely to avoid importing RefreshService at module load.
_refresh_service = None

# Set during lifespan when DATABASE_URL is configured; None otherwise. Used by
# GET /api/admin/logs to read the stored audit trail.
_action_log_repository: ActionLogRepository | None = None

# Set during lifespan when DATABASE_URL is configured; None otherwise. Used by
# GET /api/admin/health to report how fresh the stored market data is.
_data_health_repository: DataHealthRepository | None = None

# The APScheduler instance running the nightly refresh, when there is one (it
# is only started when a database is configured). The health endpoint reads its
# next run time, so "the job is scheduled for 18:00" is reported from the
# scheduler itself rather than from what the configuration intended.
_scheduler = None


def create_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.stooq_timeout_seconds,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )


def set_http_client(client: httpx.AsyncClient | None) -> None:
    global _http_client
    _http_client = client


def set_quote_repository(repo: QuoteRepository | None) -> None:
    """Install (or clear) the process-wide repository. Called by the lifespan."""
    global _quote_repository
    _quote_repository = repo


def set_refresh_service(service) -> None:
    """Install (or clear) the process-wide refresh service. Called by the lifespan."""
    global _refresh_service
    _refresh_service = service


def set_action_log_repository(repo: ActionLogRepository | None) -> None:
    """Install (or clear) the action-log repository. Called by the lifespan."""
    global _action_log_repository
    _action_log_repository = repo


def set_data_health_repository(repo: DataHealthRepository | None) -> None:
    """Install (or clear) the data-health repository. Called by the lifespan."""
    global _data_health_repository
    _data_health_repository = repo


def set_scheduler(scheduler) -> None:
    """Install (or clear) the nightly scheduler. Called by the lifespan."""
    global _scheduler
    _scheduler = scheduler


# ── FastAPI dependency providers ──────────────────────────────────────────────


def get_gpw_company_service() -> GpwCompanyService:
    return gpw_company_service


def get_history_cache() -> TTLCache:
    return history_cache


def get_ranking_cache() -> TTLCache:
    return ranking_cache


def get_stooq_client() -> YahooFinanceClient:
    """Return the shared Yahoo Finance data client.

    Named ``get_stooq_client`` for backwards compatibility; the stooq.pl
    client is still available in ``app.services.stooq_client`` if needed.
    """
    return yahoo_client


def get_quote_repository() -> QuoteRepository | None:
    """Return the repository, or None when no DB is configured.

    Callers that depend on the repo should check for None and fall back to
    stooq.pl directly (the same behaviour as before DB was added).
    """
    return _quote_repository


def get_refresh_service():
    """Return the RefreshService, or None before the lifespan installed it."""
    return _refresh_service


def get_action_log() -> ActionLogService:
    """Return the process-wide action log. Always present."""
    return action_log


def get_action_log_repository() -> ActionLogRepository | None:
    """Return the action-log repository, or None when no DB is configured."""
    return _action_log_repository


def get_data_health_repository() -> DataHealthRepository | None:
    """Return the data-health repository, or None when no DB is configured."""
    return _data_health_repository


def get_scheduler():
    """Return the nightly scheduler, or None when it was never started."""
    return _scheduler


def get_error_tracker() -> ErrorTracker:
    """Return the process-wide error tracker. Always present."""
    return error_tracker
