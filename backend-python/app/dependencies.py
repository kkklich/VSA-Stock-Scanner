"""Shared application objects and FastAPI dependency providers.

These are the Python analogue of the .NET DI container registrations in
``Program.cs``:

    - ``GpwCompanyService``  → singleton (loads the seed JSON once).
    - ``httpx.AsyncClient``  → one shared client with a cookie jar and a
                               browser-like User-Agent (keeps the stooq auth
                               cookie across calls), created/closed by the app
                               lifespan in ``main.py``.
    - ``StooqClient``        → wraps that shared client.
    - ``TTLCache``           → process-local in-memory cache (≈ IMemoryCache).
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.models import StockHistoryResponse
from app.services.cache import TTLCache
from app.services.gpw_company_service import GpwCompanyService
from app.services.stooq_client import StooqClient

# A browser-like User-Agent avoids trivial blocks from stooq.pl.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Process-wide singletons. The AsyncClient is assigned by the app lifespan so its
# sockets are opened and closed with the application.
gpw_company_service = GpwCompanyService()
history_cache: TTLCache[StockHistoryResponse] = TTLCache()
_http_client: httpx.AsyncClient | None = None


def create_http_client() -> httpx.AsyncClient:
    """Build the shared httpx client used for all stooq.pl traffic."""
    return httpx.AsyncClient(
        timeout=settings.stooq_timeout_seconds,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )


def set_http_client(client: httpx.AsyncClient | None) -> None:
    """Install (or clear) the process-wide httpx client. Called by the lifespan."""
    global _http_client
    _http_client = client


# --- FastAPI dependency providers -----------------------------------------


def get_gpw_company_service() -> GpwCompanyService:
    return gpw_company_service


def get_history_cache() -> TTLCache[StockHistoryResponse]:
    return history_cache


def get_stooq_client() -> StooqClient:
    if _http_client is None:  # pragma: no cover - guards against misconfiguration
        raise RuntimeError("HTTP client is not initialized; is the app lifespan running?")
    return StooqClient(_http_client)
