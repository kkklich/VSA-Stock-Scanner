"""Sector-heatmap computation service.

Builds the data behind ``GET /api/stocks/heatmap``: one tile per tracked GPW
company that passes the same pre-filters as the ranking (liquidity + market-cap
floor, both evaluated on the ranking's 120-day window so stale/suspended stocks
are excluded here exactly as they are there), carrying the tile size (market
cap), the tile colour inputs (VSA rating) and the price change over several
horizons (1 day / 1 month / 1 year / MAX).

The history window is longer than the ranking's 120 days because the 1-year and
MAX changes need older bars. Data source priority is identical to the ranking:
in-memory cache → PostgreSQL → live stooq/Yahoo fetch. "MAX" always means the
full *stored* history (the bootstrap ingest loads ~400 days, and the database
keeps growing one day at a time from there).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from app.analysis.statistics import median_volume_pln
from app.analysis.vsa import (
    VsaConfig,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.db.repository import QuoteRepository
from app.models import GpwCompany, HeatmapItem, HeatmapResponse, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# How far back to request history. 5 years comfortably covers the 1-year change
# and lets "MAX" grow as the database accumulates bars over time.
_HISTORY_DAYS = 5 * 365
# The VSA rating must match the ranking page, which analyses the last 120
# calendar days — so the rating here is computed on the same slice.
_RATING_WINDOW_DAYS = 120
# Same pre-filters as the ranking (blueprint §5).
_MIN_MEDIAN_VOLUME_PLN = 100_000.0
_MIN_MARKET_CAP_PLN = 100_000_000
_MAX_CONCURRENT = 4


def _pct_change(last_close: float, baseline: float) -> float | None:
    """Percentage change from ``baseline`` to ``last_close`` (2 decimals)."""
    if baseline <= 0:
        return None
    return round((last_close - baseline) / baseline * 100, 2)


def _baseline_close(
    quotes: list[StooqDailyQuote], cutoff: date, oldest: date
) -> float | None:
    """Close of the newest bar dated within ``[oldest, cutoff]`` (else None).

    The ``oldest`` floor keeps gappy histories honest: without it a "1M"
    change could silently be computed against a bar from many months ago.
    """
    for q in reversed(quotes):
        if q.date <= cutoff:
            return float(q.close) if q.date >= oldest else None
    return None


def compute_changes(
    quotes: list[StooqDailyQuote],
) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (1D, 1M, 1Y, MAX) percentage changes for a chronological bar list.

    A horizon is ``None`` when the history does not reach back far enough —
    except MAX, which always uses the oldest available bar.
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

    change_max = _pct_change(last_close, float(quotes[0].close))

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

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote] | None:
        """Return quotes from cache → repo → stooq, in that priority order."""
        # No date in the key: a moving from_date would strand yesterday's
        # entries forever in no-DB mode (nothing sweeps this cache there).
        # The TTL alone keeps the entry fresh; the nightly ingest still
        # clears everything in DB mode.
        cache_key = f"history:{ticker}:heatmap:{_HISTORY_DAYS}d"
        quotes: list[StooqDailyQuote] | None = history_cache.get(cache_key)
        if quotes is not None:
            return quotes

        if repo is not None:
            quotes = await repo.get_quotes(ticker, from_date)
            if quotes:
                history_cache.set(cache_key, quotes, history_cache_ttl)
                return quotes

        async with semaphore:
            try:
                quotes = await stooq.get_daily_history(ticker, from_date=from_date)
            except StooqAccessError as exc:
                logger.warning("Heatmap: skipping %s: stooq error: %s", ticker, exc)
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

    async def build_tile(
        company: GpwCompany,
    ) -> tuple[HeatmapItem, date] | None:
        if company.market_cap is not None and company.market_cap < _MIN_MARKET_CAP_PLN:
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
            if median_volume_pln(recent) < _MIN_MEDIAN_VOLUME_PLN:
                return None

            # Rating on the same 120-day slice the ranking uses, so both pages
            # show identical numbers for the same stock.
            signals = detect_signals(recent, config)
            rating = compute_rating(signals, today)
            verdict, _ = verdict_from_signals(signals, today)

            change_1d, change_1m, change_1y, change_max = compute_changes(quotes)

            item = HeatmapItem(
                ticker=company.ticker.upper(),
                name=company.name,
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
    tiles = [r for r in results if isinstance(r, tuple)]
    items = [item for item, _ in tiles]
    items.sort(key=lambda i: (i.market_cap is None, -(i.market_cap or 0)))
    as_of = max((d for _, d in tiles), default=None)
    return HeatmapResponse(as_of=as_of, items=items)
