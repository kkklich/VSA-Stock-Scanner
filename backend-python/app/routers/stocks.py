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

import logging
import re
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError

from app.analysis.ai_insight import analyze_stock
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
    CompanyFundamentalsResponse,
    GpwCompany,
    RatingHistoryResponse,
    RefreshStatusResponse,
    SignalEffectiveness,
    StockHistoryResponse,
    StockRankingItem,
    StockSignalsResponse,
    StooqDailyQuote,
    VsaSettings,
    VsaSignalResponse,
)
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.gpw_company_service import GpwCompanyService
from app.services.ranking_service import compute_ranking
from app.services.refresh_service import RefreshService, build_rating_points
from app.services.scanner_service import compute_scanner_stats
from app.services.stooq_client import StooqClient
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


def _sort_value(item: StockRankingItem, attr: str) -> object:
    """Return a type-consistent, comparable key for one column."""
    if attr == "last_signal":
        return _SIGNAL_RANK.get(item.last_signal, 0)
    value = getattr(item, attr)
    if value is None:  # e.g. sector may be missing
        return ""
    if isinstance(value, str):
        return value.casefold()
    return value


def _query_ranking(
    items: list[StockRankingItem],
    *,
    q: str | None,
    min_rating: int,
    signal: str | None,
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
    if signal and signal.casefold() != "all":
        rows = [r for r in rows if r.last_signal == signal]

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


async def _get_quotes(
    ticker: str,
    from_date: date,
    to_date: date | None,
    cache: TTLCache,
    cache_ttl: int,
    repo: QuoteRepository | None,
    stooq: StooqClient,
) -> list[StooqDailyQuote]:
    """Fetch OHLCV for a single ticker using the cache → repo → stooq priority."""
    cache_key = f"history:{ticker}:{from_date}:{to_date}"
    quotes: list[StooqDailyQuote] | None = cache.get(cache_key)
    if quotes is not None:
        return quotes

    if repo is not None:
        quotes = await repo.get_quotes(ticker, from_date, to_date)
        if quotes:
            cache.set(cache_key, quotes, cache_ttl)
            return quotes

    try:
        quotes = await stooq.get_daily_history(ticker, from_date, to_date)
    except StooqAccessError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream data provider (stooq.pl) unavailable: {exc}",
        ) from exc

    if repo is not None and quotes:
        try:
            await repo.upsert_quotes(ticker, quotes)
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
    signal: Annotated[str | None, Query(max_length=32)] = None,
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
        signal=signal,
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
    today = date.today()
    rating = compute_rating(signals, today)
    rating_change = rating - compute_rating(signals, today - timedelta(days=1))

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
    rating = compute_rating(signals, date.today())
    company = companies.find(normalized)

    return analyze_stock(
        ticker=normalized,
        name=company.name if company else None,
        quotes=quotes,
        signals=signals,
        rating=rating,
    )


# ── Endpoint 7: company fundamentals ─────────────────────────────────────────


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
    )
