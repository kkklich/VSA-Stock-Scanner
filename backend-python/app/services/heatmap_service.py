"""Sector-heatmap computation service.

Builds the data behind ``GET /api/stocks/heatmap``: one tile per tracked GPW
company that passes the same pre-filters as the ranking (liquidity + market-cap
floor, both evaluated on the ranking's 120-day window so stale/suspended stocks
are excluded here exactly as they are there), carrying the tile size (market
cap), the tile colour inputs (VSA rating) and the price change over several
horizons (1 day / 1 month / 1 year / MAX).

The bars come from the ranking's own fetch window (``CONTEXT_HISTORY_DAYS``,
~17 months) and its cached per-ticker history, which is long enough for the
1-year change. "MAX" means the full *stored* history, and needs only the oldest
stored close — read for the whole market in one query rather than by holding
years of bars per stock in memory, which at a thousand tracked companies would
not fit on the server. Without a database, MAX falls back to the oldest bar of
the fetch window. Data source priority is identical to the ranking: in-memory
cache → PostgreSQL → live Yahoo fetch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from app.analysis.returns import baseline_close as _baseline_close
from app.analysis.returns import pct_change as _pct_change
from app.analysis.statistics import median_turnover
from app.analysis.vsa import (
    VsaConfig,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.db.base import DB_SCAN_CONCURRENCY
from app.db.repository import QuoteRepository
from app.markets import (
    below_liquidity_floor,
    below_market_cap_floor,
    market_of,
    quote_currency,
)
from app.models import GpwCompany, HeatmapItem, HeatmapResponse, StooqDailyQuote
from app.services.cache import NEGATIVE_CACHE_SECONDS, TTLCache
from app.services.exceptions import StooqAccessError
from app.services.ranking_service import CONTEXT_HISTORY_DAYS
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# How far back to request history: the ranking's window, so both scans share
# one cached history per stock (the 1-year change fits inside it).
_HISTORY_DAYS = CONTEXT_HISTORY_DAYS
# The VSA rating must match the ranking page, which analyses the last 120
# calendar days — so the rating here is computed on the same slice.
_RATING_WINDOW_DAYS = 120
# Same pre-filters as the ranking (blueprint §5) — turnover and market cap
# floors in złoty, applied per market by app/markets.py.
_MAX_CONCURRENT = 4
# Recency pre-filter, same as the ranking: drop tickers whose last bar lags
# the newest session across the scan by more than this many calendar days
# (suspended/stale listings), while tolerating holidays and long weekends.
_MAX_SESSION_LAG_DAYS = 10


def compute_changes(
    quotes: list[StooqDailyQuote],
    first_close: float | None = None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (1D, 1M, 1Y, MAX) percentage changes for a chronological bar list.

    A horizon is ``None`` when the history does not reach back far enough —
    except MAX, which uses ``first_close`` (the oldest *stored* close) when
    given, and the oldest bar of ``quotes`` otherwise.
    """
    if len(quotes) < 2:
        return None, None, None, None

    last = quotes[-1]
    last_close = float(last.close)

    change_1d = _pct_change(last_close, float(quotes[-2].close))

    # A baseline bar may be at most twice the horizon old (tolerance for
    # holidays and short listing gaps); anything older yields None rather
    # than a change mislabelled as "1M"/"1Y".
    baseline_1m = _baseline_close(
        quotes[:-1], last.date - timedelta(days=30), last.date - timedelta(days=60)
    )
    change_1m = _pct_change(last_close, baseline_1m) if baseline_1m else None

    baseline_1y = _baseline_close(
        quotes[:-1], last.date - timedelta(days=365), last.date - timedelta(days=730)
    )
    change_1y = _pct_change(last_close, baseline_1y) if baseline_1y else None

    change_max = _pct_change(
        last_close, first_close if first_close else float(quotes[0].close)
    )

    return change_1d, change_1m, change_1y, change_max


async def compute_heatmap(
    companies: list[GpwCompany],
    stooq: StooqClient,
    history_cache: TTLCache,
    history_cache_ttl: int,
    repo: QuoteRepository | None = None,
    today: date | None = None,
    config: VsaConfig | None = None,
) -> HeatmapResponse:
    """Build heatmap tiles for every company that passes the ranking pre-filters.

    Args mirror ``ranking_service.compute_ranking``; tiles are sorted by
    market cap descending (unknown caps last) so the frontend can lay them out
    without re-sorting. ``as_of`` is the newest bar date across all tiles.
    """
    if today is None:
        today = date.today()

    from_date = today - timedelta(days=_HISTORY_DAYS)
    rating_from = today - timedelta(days=_RATING_WINDOW_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    # Separate gate for the DB reads: this scan fans out over the whole
    # universe, and ~290 simultaneous queries against a 15-connection pool
    # would time out rather than queue. See DB_SCAN_CONCURRENCY in
    # app/db/base.py for how the number ties back to the pool size.
    db_semaphore = asyncio.Semaphore(DB_SCAN_CONCURRENCY)

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote] | None:
        """Return quotes from cache → repo → stooq, in that priority order."""
        # The ranking's key for the same window, so the two scans share it.
        cache_key = f"history:{ticker}:{from_date}:None"
        quotes: list[StooqDailyQuote] | None = history_cache.get(cache_key)
        if quotes is not None:
            return quotes

        if repo is not None:
            async with db_semaphore:
                quotes = await repo.get_quotes(ticker, from_date)
            if quotes:
                history_cache.set(cache_key, quotes, history_cache_ttl)
                return quotes

        async with semaphore:
            try:
                quotes = await stooq.get_daily_history(ticker, from_date=from_date)
            except StooqAccessError as exc:
                logger.warning("Heatmap: skipping %s: data provider error: %s", ticker, exc)
                # A provider that answers "I have nothing for this ticker"
                # is remembered for a while, so a listing renamed or delisted
                # on the GPW is not re-requested — and re-logged as an error —
                # by every scan for the rest of the day. The window is short on
                # purpose; see NEGATIVE_CACHE_SECONDS.
                history_cache.set(
                    cache_key,
                    [],
                    min(history_cache_ttl, NEGATIVE_CACHE_SECONDS),
                )
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error("Heatmap: skipping %s: unexpected error: %s", ticker, exc)
                return None

            if repo is not None and quotes:
                try:
                    await repo.upsert_quotes(ticker, quotes)
                except Exception:
                    logger.exception("Failed to persist %s quotes to DB.", ticker)

        history_cache.set(cache_key, quotes or [], history_cache_ttl)
        return quotes or []

    # The oldest stored close of every company, for MAX — one query.
    first_closes: dict[str, float] = {}
    if repo is not None:
        try:
            async with db_semaphore:
                found = await repo.get_first_closes([c.ticker for c in companies])
            first_closes = {t: float(close) for t, (_day, close) in found.items()}
        except Exception:  # noqa: BLE001 — MAX then falls back to the window
            logger.exception("Heatmap: could not read the oldest stored closes.")

    async def build_tile(
        company: GpwCompany,
    ) -> tuple[HeatmapItem, date] | None:
        currency = quote_currency(company)
        if below_market_cap_floor(company.market_cap, currency):
            return None

        quotes = await fetch_quotes(company.ticker)
        if not quotes:
            return None

        # Pre-filters must run on the same 120-day window the ranking uses.
        # Judged on the full 5-year history, a stock suspended months ago
        # (plenty of old bars, no recent ones) would pass and get a tile
        # showing its stale price as current — while being absent from the
        # ranking. The long history is used only for the 1M/1Y/MAX changes.
        recent = [q for q in quotes if q.date >= rating_from]
        if len(recent) < 25:
            return None

        try:
            if below_liquidity_floor(median_turnover(recent), currency):
                return None

            # Rating on the same 120-day slice the ranking uses, so both pages
            # show identical numbers for the same stock. As-of the last
            # session date (not the calendar day), matching the ranking.
            signals = detect_signals(recent, config)
            as_of = recent[-1].date
            rating = compute_rating(signals, as_of)
            verdict, _ = verdict_from_signals(signals, as_of)

            change_1d, change_1m, change_1y, change_max = compute_changes(
                quotes, first_closes.get(company.ticker)
            )

            item = HeatmapItem(
                ticker=company.ticker.upper(),
                name=company.name,
                market=market_of(company.ticker).id,
                currency=currency,
                sector=company.sector,
                market_cap=company.market_cap,
                last_price=float(quotes[-1].close),
                current_rating=rating,
                last_signal=verdict,
                change_1d=change_1d,
                change_1m=change_1m,
                change_1y=change_1y,
                change_max=change_max,
            )
            return item, quotes[-1].date
        except Exception:  # noqa: BLE001
            logger.exception("Heatmap: skipping %s: analysis failed.", company.ticker)
            return None

    results = await asyncio.gather(
        *(build_tile(c) for c in companies), return_exceptions=True
    )
    # An exception that escaped build_tile's guard (e.g. the DB dying
    # mid-scan) must be logged, or a broken run would look like an empty map.
    for company, result in zip(companies, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Heatmap: skipping %s: %s", company.ticker, result)
    tiles = [r for r in results if isinstance(r, tuple)]

    # Recency pre-filter (see _MAX_SESSION_LAG_DAYS): no tile for a ticker
    # whose last session lags the newest one in this run — its "current"
    # price and rating would be months stale. Dataset-global max, not
    # wall-clock, so cached results stay deterministic.
    as_of = max((d for _, d in tiles), default=None)
    items = [
        item
        for item, last_bar in tiles
        if as_of is None or (as_of - last_bar).days <= _MAX_SESSION_LAG_DAYS
    ]
    items.sort(key=lambda i: (i.market_cap is None, -(i.market_cap or 0)))
    return HeatmapResponse(as_of=as_of, items=items)
