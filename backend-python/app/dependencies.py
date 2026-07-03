"""Shared application objects and FastAPI dependency providers.

Singletons created once in the app lifespan (``main.py``) and accessed here:

    GpwCompanyService   — company seed data (JSON file, read-only).
    httpx.AsyncClient   — shared HTTP client for all stooq.pl traffic.
    StooqClient         — wraps the shared HTTP client.
    TTLCache × 2        — in-memory caches for per-ticker history and the
                          full ranking list.
    QuoteRepository     — optional persistence layer; None when no DATABASE_URL
                          is configured (app falls back to live stooq.pl).
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.db.repository import QuoteRepository
from app.models import StockRankingItem
from app.services.cache import TTLCache
from app.services.gpw_company_service import GpwCompanyService
from app.services.yahoo_finance_client import YahooFinanceClient

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ── Process-wide singletons ───────────────────────────────────────────────────

gpw_company_service = GpwCompanyService()

# Per-ticker OHLCV history, keyed "history:{ticker}:{from}:{to}".
history_cache: TTLCache = TTLCache()

# Pre-computed full ranking list.
ranking_cache: TTLCache[list[StockRankingItem]] = TTLCache()

_http_client: httpx.AsyncClient | None = None

# Set during lifespan when DATABASE_URL is configured; None otherwise.
_quote_repository: QuoteRepository | None = None


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


# ── FastAPI dependency providers ──────────────────────────────────────────────


def get_gpw_company_service() -> GpwCompanyService:
    return gpw_company_service


def get_history_cache() -> TTLCache:
    return history_cache


def get_ranking_cache() -> TTLCache[list[StockRankingItem]]:
    return ranking_cache


def get_stooq_client() -> YahooFinanceClient:
    """Return the shared Yahoo Finance data client.

    Named ``get_stooq_client`` for backwards compatibility; the stooq.pl
    client is still available in ``app.services.stooq_client`` if needed.
    """
    return YahooFinanceClient()


def get_quote_repository() -> QuoteRepository | None:
    """Return the repository, or None when no DB is configured.

    Callers that depend on the repo should check for None and fall back to
    stooq.pl directly (the same behaviour as before DB was added).
    """
    return _quote_repository
