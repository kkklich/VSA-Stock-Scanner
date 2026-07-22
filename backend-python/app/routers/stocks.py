"""Market-data endpoints backed by the DB (primary) and stooq.pl (fallback).

Routes under ``/api/stocks``:

    GET /api/stocks                    — GPW company list
    GET /api/stocks/ranking            — VSA-ranked stock feed
    GET /api/stocks/{ticker}/history   — raw EOD OHLCV
    GET /api/stocks/{ticker}/signals   — OHLCV + VSA overlay for charts

Data source priority per request:
    in-memory TTL cache  →  PostgreSQL (via QuoteRepository)  →  stooq.pl live

The stooq.pl fallback keeps the app functional when the DB is not configured
(STOCKPILOT_DATABASE_URL unset) and is also used on first run before bootstrap
ingest completes.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError

from app.analysis.ai_insight import analyze_stock
from app.analysis.returns import compute_price_returns
from app.analysis.trust_score import compute_trust_score
from app.analysis.vsa import (
    VsaConfig,
    compute_rating,
    config_from_settings,
    detect_signals,
)
from app.config import settings
from app.db.repository import QuoteRepository
from app.dependencies import (
    get_gpw_company_service,
    get_history_cache,
    get_quote_repository,
    get_ranking_cache,
    get_refresh_service,
    get_stooq_client,
)
from app.models import (
    AiAnalysisResponse,
    CandleBar,
    CapexResponse,
    CapexSummary,
    CashflowPeriod,
    CompanyFundamentalsResponse,
    GpwCompany,
    HeatmapResponse,
    PriceReturns,
    RatingHistoryResponse,
    RefreshStatusResponse,
    SignalEffectiveness,
    StockHistoryResponse,
    StockRankingItem,
    StockSignalsResponse,
    StooqDailyQuote,
    TrustScoreResponse,
    VolumeSurgeResponse,
    VsaSettings,
    VsaSignalResponse,
)
from app.services.cache import TTLCache
from app.services.capex_service import build_capex_screen, sum_ttm, summarize_capex
from app.services.exceptions import StooqAccessError
from app.services.gpw_company_service import GpwCompanyService
from app.services.heatmap_service import compute_heatmap
from app.services.ranking_service import compute_ranking
from app.services.refresh_service import RefreshService, build_rating_points
from app.services.scanner_service import compute_scanner_stats
from app.services.stooq_client import StooqClient
from app.services.volume_surge_service import (
    DEFAULT_BASELINE_DAYS,
    DEFAULT_MIN_RATIO,
    DEFAULT_RECENT_DAYS,
    compute_volume_surge,
)
from app.services.yahoo_finance_client import YahooFinanceClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

_SIGNALS_DEFAULT_DAYS = 365


# ── Helpers ───────────────────────────────────────────────────────────────────

# Sortable ranking columns: camelCase key (as the frontend sends it) → the
# StockRankingItem attribute name. Anything outside this whitelist is rejected
# so a bad client can't probe arbitrary attributes.
_RANKING_SORT_KEYS: dict[str, str] = {
    "ticker": "ticker",
    "name": "name",
    "lastPrice": "last_price",
    "priceChangePct": "price_change_pct",
    "currentRating": "current_rating",
    "ratingChange": "rating_change",
    "lastSignal": "last_signal",
    "daysSinceSignal": "days_since_signal",
    "volume": "volume",
    "sector": "sector",
    "aiConfidence": "ai_confidence",
    "distFrom52wHighPct": "dist_from_52w_high_pct",
    "distFrom52wLowPct": "dist_from_52w_low_pct",
}

# Verdict ordering so "Last Signal" sorts by conviction (Strong Buy → Strong
# Sell) rather than alphabetically.
_SIGNAL_RANK: dict[str, int] = {
    "Strong Buy": 5,
    "Buy": 4,
    "Hold": 3,
    "Sell": 2,
    "Strong Sell": 1,
}


def _sort_value(item: object, attr: str) -> object:
    """Return a type-consistent, comparable key for one column.

    Shared by the ranking and volume-surge feeds (both carry ``last_signal``,
    optional ``sector`` and otherwise numeric/string columns).
    """
    value = getattr(item, attr)
    if attr == "last_signal":
        return _SIGNAL_RANK.get(value, 0)
    if value is None:
        # Missing sector sorts as an empty string; a missing value in an
        # optional NUMERIC column (the 52-week distances) must sort as a
        # number or Python would refuse to compare it with the real floats.
        return "" if attr == "sector" else float("-inf")
    if isinstance(value, str):
        return value.casefold()
    return value


def _query_ranking(
    items: list[StockRankingItem],
    *,
    q: str | None,
    min_rating: int,
    max_rating: int = 100,
    signal: str | None,
    sector: str | None = None,
    max_days_since_signal: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_volume: int | None = None,
    max_dist_from_52w_high_pct: float | None = None,
    max_dist_from_52w_low_pct: float | None = None,
    new_52w_high: bool = False,
    new_52w_low: bool = False,
    tickers: set[str] | None,
    sort_by: str,
    sort_dir: str,
) -> list[StockRankingItem]:
    """Filter → search → sort the full ranking (pagination is applied later).

    Kept pure and separate from the endpoint so it is trivially unit-testable
    and so the expensive ranking computation stays fully cached: only this cheap
    in-memory pass runs per request.
    """
    rows = items
    if tickers is not None:
        rows = [r for r in rows if r.ticker.casefold() in tickers]
    if q:
        needle = q.strip().casefold()
        if needle:
            rows = [
                r
                for r in rows
                if needle in r.ticker.casefold() or needle in r.name.casefold()
            ]
    if min_rating > 0:
        rows = [r for r in rows if r.current_rating >= min_rating]
    if max_rating < 100:
        rows = [r for r in rows if r.current_rating <= max_rating]
    if signal and signal.casefold() != "all":
        rows = [r for r in rows if r.last_signal == signal]
    if sector and sector.casefold() != "all":
        wanted = sector.strip().casefold()
        rows = [r for r in rows if (r.sector or "").casefold() == wanted]
    if max_days_since_signal is not None:
        # days_since_signal is 999 when no signal ever fired, so a recency
        # filter naturally drops signal-less stocks too.
        rows = [r for r in rows if r.days_since_signal <= max_days_since_signal]
    if min_price is not None:
        rows = [r for r in rows if r.last_price >= min_price]
    if max_price is not None:
        rows = [r for r in rows if r.last_price <= max_price]
    if min_volume is not None:
        rows = [r for r in rows if r.volume >= min_volume]
    if max_dist_from_52w_high_pct is not None:
        # "Within N% of the 52-week high": the stored distance is ≤ 0
        # (percent below the high), so within-N means distance ≥ −N.
        rows = [
            r
            for r in rows
            if r.dist_from_52w_high_pct is not None
            and r.dist_from_52w_high_pct >= -max_dist_from_52w_high_pct
        ]
    if max_dist_from_52w_low_pct is not None:
        # "Within N% of the 52-week low": the stored distance is ≥ 0
        # (percent above the low).
        rows = [
            r
            for r in rows
            if r.dist_from_52w_low_pct is not None
            and r.dist_from_52w_low_pct <= max_dist_from_52w_low_pct
        ]
    if new_52w_high:
        rows = [r for r in rows if r.is_new_52w_high]
    if new_52w_low:
        rows = [r for r in rows if r.is_new_52w_low]

    attr = _RANKING_SORT_KEYS.get(sort_by, "current_rating")
    reverse = sort_dir.casefold() != "asc"
    return sorted(rows, key=lambda r: _sort_value(r, attr), reverse=reverse)


def _parse_vsa_settings(raw: str | None) -> VsaConfig:
    """Parse the optional ``settings`` query parameter (URL-encoded JSON).

    The Scanner page sends its saved VSA engine configuration here so the
    detection thresholds and signal toggles actually drive the calculation.
    Returns the default config when the parameter is absent; raises 400 on
    malformed input so a broken client can't poison the cache.
    """
    if not raw or not raw.strip():
        return VsaConfig.default()
    try:
        payload = VsaSettings.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid 'settings' parameter: {exc.error_count()} validation error(s).",
        ) from exc
    return config_from_settings(payload)


# Stored history counts as covering a request when its first bar is at most
# this many days after the requested from_date (weekends / market holidays).
_BACKFILL_TOLERANCE_DAYS = 14
# (ticker, from_date) pairs already backfilled from stooq in this process, so
# stocks whose full history simply starts later (listed after from_date) are
# not re-fetched on every request.
_backfill_attempted: set[tuple[str, date]] = set()


async def _get_quotes(
    ticker: str,
    from_date: date,
    to_date: date | None,
    cache: TTLCache,
    cache_ttl: int,
    repo: QuoteRepository | None,
    stooq: StooqClient,
) -> list[StooqDailyQuote]:
    """Fetch OHLCV for a single ticker using the cache → repo → stooq priority.

    When the stored history starts later than ``from_date`` (the ingest only
    bootstraps ~400 days), the missing older bars are fetched from stooq once
    and persisted, permanently backfilling the DB for that ticker.
    """
    cache_key = f"history:{ticker}:{from_date}:{to_date}"
    cached: list[StooqDailyQuote] | None = cache.get(cache_key)
    if cached is not None:
        return cached

    stored: list[StooqDailyQuote] = []
    if repo is not None:
        stored = await repo.get_quotes(ticker, from_date, to_date)
    covers_range = (
        bool(stored) and (stored[0].date - from_date).days <= _BACKFILL_TOLERANCE_DAYS
    )
    if stored and (covers_range or (ticker, from_date) in _backfill_attempted):
        cache.set(cache_key, stored, cache_ttl)
        return stored

    try:
        fetched = await stooq.get_daily_history(ticker, from_date, to_date)
    except StooqAccessError as exc:
        if stored:
            logger.warning(
                "stooq.pl backfill for %s failed (%s); serving stored history.",
                ticker,
                exc,
            )
            cache.set(cache_key, stored, cache_ttl)
            return stored
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream data provider (stooq.pl) unavailable: {exc}",
        ) from exc

    if repo is not None:
        _backfill_attempted.add((ticker, from_date))

    # Keep the ingested (Yahoo) bars where the ranges overlap; stooq only
    # supplies the older prefix the DB does not have yet.
    if stored:
        new_bars = [q for q in fetched if q.date < stored[0].date]
        quotes = new_bars + stored
    else:
        new_bars = fetched
        quotes = fetched

    if repo is not None and new_bars:
        try:
            await repo.upsert_quotes(ticker, new_bars)
        except Exception:
            logger.exception(
                "Failed to persist %s quotes to DB; serving live data.", ticker
            )

    cache.set(cache_key, quotes or [], cache_ttl)
    return quotes or []


# ── Endpoint 1: company list ──────────────────────────────────────────────────


@router.get("", response_model=list[GpwCompany], summary="Tracked GPW companies")
async def get_companies(
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
) -> list[GpwCompany]:
    return companies.get_companies()


# ── Endpoint 2: VSA ranking ───────────────────────────────────────────────────


@router.get(
    "/ranking",
    response_model=list[StockRankingItem],
    response_model_by_alias=True,
    summary="VSA-ranked stock feed",
    responses={status.HTTP_502_BAD_GATEWAY: {"description": "stooq.pl unavailable"}},
)
async def get_ranking(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, alias="pageSize")] = 25,
    sort_by: Annotated[str, Query(alias="sortBy")] = "currentRating",
    sort_dir: Annotated[Literal["asc", "desc"], Query(alias="sortDir")] = "desc",
    q: Annotated[str | None, Query(max_length=64)] = None,
    min_rating: Annotated[int, Query(alias="minRating", ge=0, le=100)] = 0,
    max_rating: Annotated[int, Query(alias="maxRating", ge=0, le=100)] = 100,
    signal: Annotated[str | None, Query(max_length=32)] = None,
    sector: Annotated[str | None, Query(max_length=64)] = None,
    max_days_since_signal: Annotated[
        int | None, Query(alias="maxDaysSinceSignal", ge=0, le=999)
    ] = None,
    min_price: Annotated[float | None, Query(alias="minPrice", ge=0)] = None,
    max_price: Annotated[float | None, Query(alias="maxPrice", ge=0)] = None,
    min_volume: Annotated[int | None, Query(alias="minVolume", ge=0)] = None,
    max_dist_from_52w_high_pct: Annotated[
        float | None, Query(alias="maxDistFrom52wHighPct", ge=0, le=100)
    ] = None,
    max_dist_from_52w_low_pct: Annotated[
        float | None, Query(alias="maxDistFrom52wLowPct", ge=0)
    ] = None,
    new_52w_high: Annotated[bool, Query(alias="new52wHigh")] = False,
    new_52w_low: Annotated[bool, Query(alias="new52wLow")] = False,
    tickers: Annotated[str | None, Query(max_length=4000)] = None,
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)] = ...,
    stooq: Annotated[StooqClient, Depends(get_stooq_client)] = ...,
    cache: Annotated[TTLCache, Depends(get_ranking_cache)] = ...,
    history_cache: Annotated[TTLCache, Depends(get_history_cache)] = ...,
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = ...,
) -> list[StockRankingItem]:
    if sort_by not in _RANKING_SORT_KEYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid 'sortBy' value '{sort_by}'. "
                f"Allowed: {', '.join(_RANKING_SORT_KEYS)}."
            ),
        )

    config = _parse_vsa_settings(vsa_settings)
    cache_key = f"ranking:full{config.cache_suffix()}"
    full_ranking: list[StockRankingItem] | None = cache.get(cache_key)

    if full_ranking is None:
        logger.info("Ranking cache cold — computing ranking.")
        full_ranking = await compute_ranking(
            companies=companies.get_companies(),
            stooq=stooq,
            history_cache=history_cache,
            history_cache_ttl=settings.history_cache_seconds,
            repo=repo,
            config=config,
        )
        cache.set(cache_key, full_ranking, settings.history_cache_seconds)
        logger.info("Ranking ready: %d stocks passed pre-filters.", len(full_ranking))

    # Optional allow-list of tickers (used by the "favorites only" view).
    ticker_set: set[str] | None = None
    if tickers is not None:
        ticker_set = {t.strip().casefold() for t in tickers.split(",") if t.strip()}

    filtered = _query_ranking(
        full_ranking,
        q=q,
        min_rating=min_rating,
        max_rating=max_rating,
        signal=signal,
        sector=sector,
        max_days_since_signal=max_days_since_signal,
        min_price=min_price,
        max_price=max_price,
        min_volume=min_volume,
        max_dist_from_52w_high_pct=max_dist_from_52w_high_pct,
        max_dist_from_52w_low_pct=max_dist_from_52w_low_pct,
        new_52w_high=new_52w_high,
        new_52w_low=new_52w_low,
        tickers=ticker_set,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    # Total matching rows before pagination — the frontend reads this to build
    # its pager. Exposed to the browser via CORS (see main.py).
    response.headers["X-Total-Count"] = str(len(filtered))

    start = (page - 1) * page_size
    return filtered[start : start + page_size]


# ── Endpoints: manual data refresh ────────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=RefreshStatusResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a data refresh (Yahoo ingest → ranking → rating snapshots)",
)
async def trigger_refresh(
    refresh: Annotated[RefreshService | None, Depends(get_refresh_service)],
) -> RefreshStatusResponse:
    """Kick off the refresh pipeline in the background and return its status.

    This is the only way (besides the nightly 18:00 job) that fresh data is
    pulled from Yahoo Finance. If a refresh is already running, the in-flight
    run is kept and its status is returned — pressing the button twice never
    starts two downloads.
    """
    if refresh is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Refresh service not initialised yet — try again in a moment.",
        )
    started = refresh.start()
    if started:
        logger.info("Manual refresh triggered via POST /api/stocks/refresh.")
    else:
        logger.info("Manual refresh requested but one is already running.")
    return refresh.status()


@router.get(
    "/refresh/status",
    response_model=RefreshStatusResponse,
    response_model_by_alias=True,
    summary="Status of the data-refresh pipeline",
)
async def get_refresh_status(
    refresh: Annotated[RefreshService | None, Depends(get_refresh_service)],
) -> RefreshStatusResponse:
    if refresh is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Refresh service not initialised yet — try again in a moment.",
        )
    return refresh.status()


# ── Endpoint 3: scanner back-test statistics ─────────────────────────────────


@router.get(
    "/scanner/stats",
    response_model=list[SignalEffectiveness],
    response_model_by_alias=True,
    summary="Back-test effectiveness stats for each VSA signal type",
)
async def get_scanner_stats(
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)] = ...,
    stooq: Annotated[StooqClient, Depends(get_stooq_client)] = ...,
    cache: Annotated[TTLCache, Depends(get_ranking_cache)] = ...,
    history_cache: Annotated[TTLCache, Depends(get_history_cache)] = ...,
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = ...,
) -> list[SignalEffectiveness]:
    config = _parse_vsa_settings(vsa_settings)
    cache_key = f"scanner:stats{config.cache_suffix()}"
    cached: list[SignalEffectiveness] | None = cache.get(cache_key)
    if cached is not None:
        return cached

    logger.info("Scanner stats cache cold — computing.")
    raw = await compute_scanner_stats(
        companies=companies.get_companies(),
        stooq=stooq,
        history_cache=history_cache,
        history_cache_ttl=settings.history_cache_seconds,
        repo=repo,
        config=config,
    )
    result = [
        SignalEffectiveness(
            signal=r.signal,
            count=r.count,
            success_pct=r.success_pct,
            reward_risk=r.reward_risk,
            active_count=r.active_count,
        )
        for r in raw
    ]
    cache.set(cache_key, result, settings.history_cache_seconds)
    logger.info("Scanner stats ready: %d signal types.", len(result))
    return result


# ── Endpoint: sector heatmap ──────────────────────────────────────────────────

# One in-flight computation per heatmap cache key: a cold heatmap is the most
# expensive request in the app (full-universe history fetch), so concurrent
# misses wait for the first computation instead of each starting their own.
# Bounded by the number of distinct settings hashes seen since startup.
_heatmap_locks: dict[str, asyncio.Lock] = {}


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    response_model_by_alias=True,
    summary="Sector heatmap tiles (market cap, VSA rating, price changes)",
)
async def get_heatmap(
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)] = ...,
    stooq: Annotated[StooqClient, Depends(get_stooq_client)] = ...,
    cache: Annotated[TTLCache, Depends(get_ranking_cache)] = ...,
    history_cache: Annotated[TTLCache, Depends(get_history_cache)] = ...,
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = ...,
) -> HeatmapResponse:
    """Data behind the Sector heatmap page (Finviz-style treemap).

    One tile per stock that passes the ranking pre-filters: tile size comes
    from the market cap, tile colour from the VSA rating or from the price
    change over the selected horizon (1D / 1M / 1Y / MAX of stored history).
    """
    config = _parse_vsa_settings(vsa_settings)
    cache_key = f"heatmap{config.cache_suffix()}"
    cached: HeatmapResponse | None = cache.get(cache_key)
    if cached is not None:
        return cached

    lock = _heatmap_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        # A concurrent request may have finished computing while we waited.
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        generation = cache.generation
        logger.info("Heatmap cache cold — computing.")
        result = await compute_heatmap(
            companies=companies.get_companies(),
            stooq=stooq,
            history_cache=history_cache,
            history_cache_ttl=settings.history_cache_seconds,
            repo=repo,
            config=config,
        )
        # If the nightly ingest cleared the cache while we were computing,
        # this result was built from pre-refresh data — serve it to this
        # caller but don't cache it, or it would look fresh for hours.
        if not cache.set_if_generation(
            cache_key, result, settings.history_cache_seconds, generation
        ):
            logger.info("Heatmap cache invalidated during computation — not cached.")
        logger.info("Heatmap ready: %d tiles.", len(result.items))
        return result


# ── Endpoint: volume-surge scanner ────────────────────────────────────────────

# Same in-flight/staleness discipline as the heatmap: one computation per cache
# key at a time, and a result computed while the nightly refresh cleared the
# cache is served but not cached (unlike the ranking, nothing re-warms this
# cache after a refresh, so a stale write would look fresh for hours).
_volume_surge_locks: dict[str, asyncio.Lock] = {}

# Sortable volume-surge columns: camelCase key (as the frontend sends it) →
# the VolumeSurgeItem attribute name (same whitelist idea as the ranking).
_SURGE_SORT_KEYS: dict[str, str] = {
    "ticker": "ticker",
    "name": "name",
    "sector": "sector",
    "lastPrice": "last_price",
    "recentAvgVolume": "recent_avg_volume",
    "baselineAvgVolume": "baseline_avg_volume",
    "volumeRatio": "volume_ratio",
    "lastDayRatio": "last_day_ratio",
    "daysAboveBaseline": "days_above_baseline",
    "priceChangePct": "price_change_pct",
    "currentRating": "current_rating",
    "lastSignal": "last_signal",
}


@router.get(
    "/volume-surge",
    response_model=VolumeSurgeResponse,
    response_model_by_alias=True,
    summary="Stocks trading on unusually high volume (multi-day relative volume)",
)
async def get_volume_surge(
    recent_days: Annotated[int, Query(alias="recentDays", ge=1, le=10)] = (
        DEFAULT_RECENT_DAYS
    ),
    baseline_days: Annotated[int, Query(alias="baselineDays", ge=10, le=60)] = (
        DEFAULT_BASELINE_DAYS
    ),
    min_ratio: Annotated[float, Query(alias="minRatio", ge=1.0, le=10.0)] = (
        DEFAULT_MIN_RATIO
    ),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, alias="pageSize")] = 25,
    sort_by: Annotated[str, Query(alias="sortBy")] = "volumeRatio",
    sort_dir: Annotated[Literal["asc", "desc"], Query(alias="sortDir")] = "desc",
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)] = ...,
    stooq: Annotated[StooqClient, Depends(get_stooq_client)] = ...,
    cache: Annotated[TTLCache, Depends(get_ranking_cache)] = ...,
    history_cache: Annotated[TTLCache, Depends(get_history_cache)] = ...,
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = ...,
) -> VolumeSurgeResponse:
    """Companies whose recent trading volume is unusually high.

    Multi-day relative volume (RVOL): the average volume of the last
    ``recentDays`` sessions divided by the average of the ``baselineDays``
    sessions before them. Stocks at or above ``minRatio`` are returned, each
    with its VSA rating and verdict so the surge can be read in VSA terms
    (the price move alone is only a rough effort-vs-result cue; the verdict
    carries the bar-level reading). Server-side sorted (default: strongest
    surge first) and paginated; ``totalCount`` carries the matching-row total.
    """
    if sort_by not in _SURGE_SORT_KEYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid 'sortBy' value '{sort_by}'. "
                f"Allowed: {', '.join(_SURGE_SORT_KEYS)}."
            ),
        )

    config = _parse_vsa_settings(vsa_settings)
    cache_key = (
        f"volume-surge:{recent_days}:{baseline_days}:{min_ratio}"
        f"{config.cache_suffix()}"
    )
    full: VolumeSurgeResponse | None = cache.get(cache_key)

    if full is None:
        lock = _volume_surge_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            # A concurrent request may have finished computing while we waited.
            full = cache.get(cache_key)
            if full is None:
                generation = cache.generation
                logger.info("Volume-surge cache cold — computing.")
                full = await compute_volume_surge(
                    companies=companies.get_companies(),
                    stooq=stooq,
                    history_cache=history_cache,
                    history_cache_ttl=settings.history_cache_seconds,
                    repo=repo,
                    config=config,
                    recent_days=recent_days,
                    baseline_days=baseline_days,
                    min_ratio=min_ratio,
                )
                if not cache.set_if_generation(
                    cache_key, full, settings.history_cache_seconds, generation
                ):
                    logger.info(
                        "Volume-surge cache invalidated during computation — not cached."
                    )
                logger.info(
                    "Volume surge ready: %d of %d scanned stocks above ratio %.2f.",
                    len(full.items),
                    full.scanned_count,
                    min_ratio,
                )

    # Cheap per-request pass over the cached full scan — same split as the
    # ranking: the expensive computation stays fully cached, only this
    # in-memory sort + slice runs per request.
    attr = _SURGE_SORT_KEYS[sort_by]
    ordered = sorted(
        full.items,
        key=lambda i: _sort_value(i, attr),
        reverse=sort_dir != "asc",
    )
    start = (page - 1) * page_size
    return full.model_copy(update={"items": ordered[start : start + page_size]})


# ── Endpoint: capital-expenditure screen ─────────────────────────────────────

# Sortable capex columns: camelCase key (as the frontend sends it) → the
# CapexItem attribute name (same whitelist idea as the ranking).
_CAPEX_SORT_KEYS: dict[str, str] = {
    "ticker": "ticker",
    "name": "name",
    "sector": "sector",
    "capex": "capex",
    "capexTtm": "capex_ttm",
    "capexAnnual": "capex_annual",
    "capexGrowthYoyPct": "capex_growth_yoy_pct",
    "capexToRevenuePct": "capex_to_revenue_pct",
    "capexToOcfPct": "capex_to_ocf_pct",
    "operatingCashFlow": "operating_cash_flow",
}

_capex_lock = asyncio.Lock()


@router.get(
    "/capex",
    response_model=CapexResponse,
    response_model_by_alias=True,
    summary="How much each company invests in itself (capital expenditure)",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Stored investment data could not be read"
        },
    },
)
async def get_capex(
    q: Annotated[str | None, Query(max_length=50)] = None,
    sector: Annotated[str | None, Query()] = None,
    currency: Annotated[str, Query(max_length=8)] = "PLN",
    with_data: Annotated[bool, Query(alias="withData")] = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, alias="pageSize")] = 25,
    sort_by: Annotated[str, Query(alias="sortBy")] = "capex",
    sort_dir: Annotated[Literal["asc", "desc"], Query(alias="sortDir")] = "desc",
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)] = ...,
    cache: Annotated[TTLCache, Depends(get_ranking_cache)] = ...,
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = ...,
) -> CapexResponse:
    """Companies ranked by how much money they invest in their own business.

    Capital expenditure (capex) is the cash spent on plants, machines,
    buildings and software. Figures come from the stored Yahoo cash-flow
    statements (refreshed with the weekly fundamentals pass), never from a
    live fetch — the screen covers the whole universe at once.

    ``currency`` defaults to ``PLN`` because amounts in different currencies
    do not compare: a Hungarian issuer reporting in forint would top a
    zloty-sorted list on unit size alone. ``currency=all`` lifts the filter
    (the percentage columns stay comparable either way).

    ``withData=false`` keeps companies Yahoo has no capex for; they carry null
    figures rather than zeros, because "not reported" is not "invested
    nothing". Server-side sorted (default: biggest investor first) and
    paginated; ``totalCount`` carries the matching-row total.

    A failed database read answers 503 rather than an empty screen, so a
    momentary outage is never remembered as "this app has no capex data".
    """
    if sort_by not in _CAPEX_SORT_KEYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid 'sortBy' value '{sort_by}'. "
                f"Allowed: {', '.join(_CAPEX_SORT_KEYS)}."
            ),
        )

    full: CapexResponse | None = cache.get("capex:full")
    if full is None:
        async with _capex_lock:
            # A concurrent request may have finished computing while we waited.
            full = cache.get("capex:full")
            if full is None:
                generation = cache.generation
                loaded = await _load_capex(companies, repo)
                if loaded is None:
                    # The database read failed. Caching the empty screen here
                    # would tell every visitor for the next cache lifetime that
                    # the app has no investment data at all, and send them to a
                    # Refresh button that cannot fix a database outage. Fail
                    # loudly instead — the page shows the error and a Retry.
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=(
                            "Could not read the stored investment data. "
                            "Please try again in a moment."
                        ),
                    )
                full = loaded
                if not cache.set_if_generation(
                    "capex:full", full, settings.history_cache_seconds, generation
                ):
                    logger.info("Capex cache invalidated during load — not cached.")

    # Cheap per-request pass over the cached screen: filter → sort → slice.
    # Both text filters are stripped ONCE and the stripped value is used for
    # the "all" sentinel as well as the comparison — otherwise "%20all%20"
    # would slip past the sentinel and then match nothing.
    wanted_currency = currency.strip().upper()
    wanted_sector = (sector or "").strip().casefold()
    rows = full.items
    if with_data:
        rows = [r for r in rows if r.capex is not None]
    if wanted_currency.casefold() != "all":
        # The currency filter exists so amounts stay comparable, so it only
        # judges rows that HAVE an amount: a company with no reported capex has
        # nothing to compare and must survive into the withData=false view.
        rows = [r for r in rows if r.capex is None or r.currency == wanted_currency]
    if q and q.strip():
        needle = q.strip().casefold()
        rows = [
            r
            for r in rows
            if needle in r.ticker.casefold() or needle in r.name.casefold()
        ]
    if wanted_sector and wanted_sector != "all":
        rows = [r for r in rows if (r.sector or "").casefold() == wanted_sector]

    attr = _CAPEX_SORT_KEYS[sort_by]
    ordered = sorted(rows, key=lambda r: _sort_value(r, attr), reverse=sort_dir != "asc")
    start = (page - 1) * page_size
    return full.model_copy(
        update={
            "items": ordered[start : start + page_size],
            "total_count": len(ordered),
        }
    )


async def _load_capex(
    companies: GpwCompanyService,
    repo: QuoteRepository | None,
) -> CapexResponse | None:
    """Read stored cash-flow + revenue data and build the full screen.

    Without a database there is nothing to read: the figures only ever arrive
    through the ingest job, so the screen comes back empty (the page tells the
    user to run a refresh) rather than triggering ~200 live Yahoo calls. That
    is a stable state, so the caller may cache it.

    Returns ``None`` when the database read itself failed. "The query blew up"
    and "nobody has any capex" look identical once both are an empty screen,
    and the caller must never cache the first as if it were the second.
    """
    tracked = companies.get_companies()
    if repo is None:
        logger.info("Capex screen requested without a database — returning empty.")
        return CapexResponse(scanned_count=len(tracked))

    try:
        cashflow = await repo.get_all_cashflow()
        revenue = await repo.get_all_revenue()
    except Exception:
        logger.exception("Capex screen: DB read failed.")
        return None

    screen = build_capex_screen(tracked, cashflow, revenue)
    logger.info(
        "Capex screen ready: %d of %d companies have capex data.",
        screen.with_data_count,
        screen.scanned_count,
    )
    return screen


# ── Endpoint 4: raw EOD history ───────────────────────────────────────────────


@router.get(
    "/{ticker}/history",
    response_model=StockHistoryResponse,
    summary="End-of-day OHLCV history for a ticker",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker or date range"},
        status.HTTP_502_BAD_GATEWAY: {"description": "stooq.pl unavailable"},
    },
)
async def get_history(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    cache: Annotated[TTLCache, Depends(get_history_cache)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
) -> StockHistoryResponse:
    if not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "'from' must not be later than 'to'.")

    normalized = ticker.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,20}", normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid ticker format.")

    company = companies.find(normalized)

    # For the history endpoint, cache the full StockHistoryResponse object.
    resp_cache_key = f"resp:history:{normalized}:{from_}:{to}"
    cached_resp: StockHistoryResponse | None = cache.get(resp_cache_key)
    if cached_resp is not None:
        return cached_resp

    quotes = await _get_quotes(
        normalized,
        from_date=from_ or (date.today() - timedelta(days=365)),
        to_date=to,
        cache=cache,
        cache_ttl=settings.history_cache_seconds,
        repo=repo,
        stooq=stooq,
    )

    response = StockHistoryResponse(
        ticker=normalized.upper(),
        name=company.name if company else None,
        quotes=quotes,
    )
    cache.set(resp_cache_key, response, settings.history_cache_seconds)
    return response


# ── Endpoint 5: OHLCV + VSA signals ──────────────────────────────────────────


@router.get(
    "/{ticker}/signals",
    response_model=StockSignalsResponse,
    response_model_by_alias=True,
    summary="OHLCV history and VSA signal overlay for a ticker",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker or date range"},
        status.HTTP_502_BAD_GATEWAY: {"description": "stooq.pl unavailable"},
    },
)
async def get_signals(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    cache: Annotated[TTLCache, Depends(get_history_cache)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
) -> StockSignalsResponse:
    if not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "'fromDate' must not be later than 'toDate'."
        )

    config = _parse_vsa_settings(vsa_settings)

    normalized = ticker.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,20}", normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid ticker format.")

    effective_from = from_date or (date.today() - timedelta(days=_SIGNALS_DEFAULT_DAYS))
    effective_to = to_date

    quotes = await _get_quotes(
        normalized,
        from_date=effective_from,
        to_date=effective_to,
        cache=cache,
        cache_ttl=settings.history_cache_seconds,
        repo=repo,
        stooq=stooq,
    )

    company = companies.find(normalized)

    signals = detect_signals(quotes, config)

    # Ratings are keyed to the last session date, not the wall-clock date, so
    # identical data yields identical ratings regardless of when it is viewed;
    # ratingChange measures what the newest session changed (see ranking).
    if quotes:
        as_of = quotes[-1].date
        rating = compute_rating(signals, as_of)
        if len(quotes) >= 2:
            prior_signals = [s for s in signals if s.date < as_of]
            rating_change = rating - compute_rating(prior_signals, quotes[-2].date)
        else:
            rating_change = 0
    else:
        rating = 50
        rating_change = 0

    last_close = float(quotes[-1].close) if quotes else 0.0
    prev_close = float(quotes[-2].close) if len(quotes) >= 2 else last_close
    price_change_pct = (
        round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
    )

    history = [
        CandleBar(
            time=q.date,
            open=float(q.open),
            high=float(q.high),
            low=float(q.low),
            close=float(q.close),
            volume=q.volume,
        )
        for q in quotes
    ]

    vsa_signal_responses = [
        VsaSignalResponse(
            date=s.date,
            signal_name=s.signal_name.value,
            type=s.type.value,  # type: ignore[arg-type]
        )
        for s in signals
    ]

    return StockSignalsResponse(
        ticker=normalized.upper(),
        name=company.name if company else None,
        sector=company.sector if company else None,
        last_price=last_close,
        price_change_pct=price_change_pct,
        current_rating=rating,
        rating_change=rating_change,
        history=history,
        vsa_signals=vsa_signal_responses,
    )


# ── Endpoint: VSA rating history ─────────────────────────────────────────────


@router.get(
    "/{ticker}/rating-history",
    response_model=RatingHistoryResponse,
    response_model_by_alias=True,
    summary="Stored daily VSA rating snapshots for a ticker",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker or date range"},
    },
)
async def get_rating_history(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    cache: Annotated[TTLCache, Depends(get_history_cache)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
) -> RatingHistoryResponse:
    """How the stock's VSA rating (its "attractiveness") evolved over time.

    Primary source: the ``rating_snapshots`` table, written by the refresh
    pipeline (one point per trading day, DEFAULT engine settings). When no
    snapshots exist yet — first run, or the app has no database — the history
    is derived on-the-fly from the stored OHLCV bars instead, so the chart
    always has data.
    """
    if not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "'fromDate' must not be later than 'toDate'."
        )

    normalized = ticker.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,20}", normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid ticker format.")

    company = companies.find(normalized)
    effective_from = from_date or (date.today() - timedelta(days=_SIGNALS_DEFAULT_DAYS))

    # 1. Stored snapshots (the persisted "attractiveness" history).
    if repo is not None:
        try:
            points = await repo.get_rating_history(normalized, effective_from, to_date)
        except Exception:
            logger.exception("Rating-history DB lookup failed for %s.", normalized)
            points = []
        if points:
            return RatingHistoryResponse(
                ticker=normalized.upper(),
                name=company.name if company else None,
                points=points,
                source="db",
            )

    # 2. Fallback: derive the history from the OHLCV bars on the fly.
    quotes = await _get_quotes(
        normalized,
        from_date=effective_from,
        to_date=to_date,
        cache=cache,
        cache_ttl=settings.history_cache_seconds,
        repo=repo,
        stooq=stooq,
    )
    return RatingHistoryResponse(
        ticker=normalized.upper(),
        name=company.name if company else None,
        points=build_rating_points(quotes),
        source="computed",
    )


# ── Endpoint 6: AI second-opinion analysis ───────────────────────────────────


@router.get(
    "/{ticker}/ai-analysis",
    response_model=AiAnalysisResponse,
    response_model_by_alias=True,
    summary="AI insight analysis of the stock's VSA picture",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker"},
        status.HTTP_404_NOT_FOUND: {"description": "No price history for this ticker"},
        status.HTTP_502_BAD_GATEWAY: {"description": "stooq.pl unavailable"},
    },
)
async def get_ai_analysis(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    cache: Annotated[TTLCache, Depends(get_history_cache)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
) -> AiAnalysisResponse:
    """Chart-context second opinion on the rule-detected VSA signals.

    Computed locally by the built-in insight engine (``app/analysis/ai_insight``)
    from the same data the chart uses — no external AI services involved. The
    rule engine stays the source of truth for detection; this endpoint judges
    each signal by its follow-through, volume behaviour, trend background and
    historical track record on this stock, then explains it in plain language.
    """
    if not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")

    normalized = ticker.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,20}", normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid ticker format.")

    config = _parse_vsa_settings(vsa_settings)

    quotes = await _get_quotes(
        normalized,
        from_date=date.today() - timedelta(days=_SIGNALS_DEFAULT_DAYS),
        to_date=None,
        cache=cache,
        cache_ttl=settings.history_cache_seconds,
        repo=repo,
        stooq=stooq,
    )
    if not quotes:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No price history available for '{normalized}'.",
        )

    signals = detect_signals(quotes, config)
    # Keyed to the last session date (not the calendar day) — see /signals.
    rating = compute_rating(signals, quotes[-1].date)
    company = companies.find(normalized)

    return analyze_stock(
        ticker=normalized,
        name=company.name if company else None,
        quotes=quotes,
        signals=signals,
        rating=rating,
    )


# ── Endpoint: VSA trust score (prediction accuracy) ──────────────────────────


@router.get(
    "/{ticker}/trust-score",
    response_model=TrustScoreResponse,
    response_model_by_alias=True,
    summary="Prediction-accuracy (trust) score of the VSA engine on this stock",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker"},
        status.HTTP_404_NOT_FOUND: {"description": "No price history for this ticker"},
        status.HTTP_502_BAD_GATEWAY: {"description": "stooq.pl unavailable"},
    },
)
async def get_trust_score(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    cache: Annotated[TTLCache, Depends(get_history_cache)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
) -> TrustScoreResponse:
    """How trustworthy the VSA engine's strong calls have been on this stock.

    Runs the same signal detection as the chart, then back-tests every
    historical Strong Buy / Strong Sell verdict (forward return over the next
    10 sessions vs. the stock's own baseline move) and folds the results into
    a single 0–100 trust score. Computed locally by
    ``app/analysis/trust_score.py``; deterministic, no external services.
    """
    if not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")

    normalized = ticker.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,20}", normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid ticker format.")

    config = _parse_vsa_settings(vsa_settings)

    quotes = await _get_quotes(
        normalized,
        from_date=date.today() - timedelta(days=_SIGNALS_DEFAULT_DAYS),
        to_date=None,
        cache=cache,
        cache_ttl=settings.history_cache_seconds,
        repo=repo,
        stooq=stooq,
    )
    if not quotes:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No price history available for '{normalized}'.",
        )

    signals = detect_signals(quotes, config)
    company = companies.find(normalized)

    return compute_trust_score(
        ticker=normalized,
        name=company.name if company else None,
        quotes=quotes,
        signals=signals,
    )


# ── Endpoint 7: company fundamentals ─────────────────────────────────────────

# How far back the fundamentals endpoint asks for bars, to cover the 5-year
# price return. `_get_quotes` backfills and PERSISTS anything the DB is
# missing, so opening a stock page deepens that ticker's stored history once.
_RETURNS_HISTORY_DAYS = 5 * 365 + 30
# How long "Yahoo has no cash-flow statement for this company" is remembered.
# Roughly one GPW company in twenty is permanently in that state, and each
# check costs two network round trips, so without a marker every single view of
# such a stock's page repeats the whole fetch to learn nothing. A day is safe:
# these figures only move when a company publishes a report, and the nightly
# refresh clears this cache anyway.
_CAPEX_MISS_TTL_SECONDS = 24 * 60 * 60


@router.get(
    "/{ticker}/fundamentals",
    response_model=CompanyFundamentalsResponse,
    response_model_by_alias=True,
    summary="Company description, financial ratios and quarterly reports",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker"},
        status.HTTP_404_NOT_FOUND: {"description": "No fundamentals data stored yet"},
    },
)
async def get_fundamentals(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    cache: Annotated[TTLCache, Depends(get_history_cache)],
) -> CompanyFundamentalsResponse:
    if not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")

    normalized = ticker.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,20}", normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid ticker format.")

    company = companies.find(normalized)

    # Try DB first (populated by daily ingest).
    fundamentals: CompanyFundamentalsResponse | None = None
    if repo is not None:
        try:
            fundamentals = await repo.get_fundamentals(normalized)
        except Exception:
            logger.exception("DB fundamentals lookup failed for %s.", normalized)

    # On cache miss (DB empty or no DB), fetch live from Yahoo Finance.
    if fundamentals is None and isinstance(stooq, YahooFinanceClient):
        try:
            metrics = await stooq.get_fundamentals(normalized)
            quarterly = await stooq.get_quarterly_reports(normalized)
            fundamentals = CompanyFundamentalsResponse(
                ticker=normalized.upper(),
                metrics=metrics,
                quarterly_reports=quarterly,
            )
            # Persist so the next request is served from DB.
            if repo is not None:
                await repo.upsert_fundamentals(normalized, metrics)
                if quarterly:
                    await repo.upsert_quarterly(normalized, quarterly)
        except Exception:
            logger.exception("Live fundamentals fetch failed for %s.", normalized)

    if fundamentals is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No fundamentals data available for '{normalized}'.",
        )

    # Trailing price returns, computed from the same stored EOD bars the
    # charts use (never an external "1Y return" field), so the figures always
    # agree with what the user sees on the chart. A price-history failure must
    # not take the whole card down — the rest of the payload is still useful.
    price_returns: PriceReturns | None = None
    try:
        quotes = await _get_quotes(
            normalized,
            from_date=date.today() - timedelta(days=_RETURNS_HISTORY_DAYS),
            to_date=None,
            cache=cache,
            cache_ttl=settings.history_cache_seconds,
            repo=repo,
            stooq=stooq,
        )
        if quotes:
            price_returns = compute_price_returns(quotes)
    except Exception:
        logger.exception("Price returns unavailable for %s.", normalized)

    # Capital expenditure — how much the company invests in itself.
    ttm_revenue = sum_ttm(fundamentals.quarterly_reports, "total_revenue")
    capex = await _load_ticker_capex(
        normalized,
        repo=repo,
        stooq=stooq,
        cache=cache,
        # Prefer the summed quarters (same basis as the capex figure); fall
        # back to Yahoo's own trailing-12-month revenue when the quarterly
        # income statements are incomplete.
        ttm_revenue=ttm_revenue
        or (fundamentals.metrics.total_revenue if fundamentals.metrics else None),
    )

    # Merge static company metadata (description, industry, …) from the service.
    return CompanyFundamentalsResponse(
        ticker=fundamentals.ticker,
        name=company.name if company else fundamentals.name,
        sector=company.sector if company else fundamentals.sector,
        description=company.description if company else None,
        industry=company.industry if company else fundamentals.industry,
        employees=company.employees if company else None,
        website=company.website if company else None,
        country=company.country if company else None,
        metrics=fundamentals.metrics,
        quarterly_reports=fundamentals.quarterly_reports,
        price_returns=price_returns,
        ttm_revenue=ttm_revenue,
        ttm_net_income=sum_ttm(fundamentals.quarterly_reports, "net_income"),
        capex=capex,
    )


async def _load_ticker_capex(
    ticker: str,
    *,
    repo: QuoteRepository | None,
    stooq: StooqClient,
    cache: TTLCache,
    ttm_revenue: int | None,
) -> CapexSummary | None:
    """Capex summary for one stock: stored data first, live Yahoo as fallback.

    Unlike the whole-universe ``/capex`` screen, a single ticker is cheap
    enough to fetch on demand, so opening a stock page shows its investment
    figures even before the weekly fundamentals pass has run. Anything fetched
    is persisted, so the next request is served from the database.

    A company Yahoo simply has no cash-flow statement for persists nothing, so
    without help the fetch would repeat on every single page view forever. That
    "there is nothing to find" answer is therefore remembered in the shared
    history cache for ``_CAPEX_MISS_TTL_SECONDS``, and the nightly refresh
    clears that cache — so a statement Yahoo publishes later is still picked up.
    """
    periods: list[CashflowPeriod] = []
    if repo is not None:
        try:
            periods = await repo.get_cashflow(ticker)
        except Exception:
            logger.exception("DB cash-flow lookup failed for %s.", ticker)

    miss_key = f"capex-miss:{ticker}"
    if (
        not periods
        and isinstance(stooq, YahooFinanceClient)
        and cache.get(miss_key) is None
    ):
        try:
            periods = await stooq.get_cashflow_periods(ticker)
            if periods:
                if repo is not None:
                    await repo.upsert_cashflow(ticker, periods)
            else:
                cache.set(miss_key, True, _CAPEX_MISS_TTL_SECONDS)
        except Exception:
            logger.exception("Live cash-flow fetch failed for %s.", ticker)

    if not periods:
        return None
    return summarize_capex(periods, ttm_revenue)
