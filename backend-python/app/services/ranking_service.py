"""Ranking computation service.

Builds the VSA ranking for all tracked GPW companies.

Data source priority:
  1. In-memory ``history_cache`` (fastest, ~ms).
  2. ``QuoteRepository`` (PostgreSQL, ~ms if warm).
  3. stooq.pl live fetch (slow, ~30 s for 30 tickers; also persists result).

When ``repo`` is ``None`` (DB not configured), the service falls directly to
the stooq live fetch — identical to the pre-DB behaviour.
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
from app.models import GpwCompany, StockRankingItem, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

_HISTORY_DAYS = 120
_MIN_MEDIAN_VOLUME_PLN = 100_000.0
_MIN_MARKET_CAP_PLN = 100_000_000
_MAX_CONCURRENT = 4
_SPARKLINE_BARS = 10


async def compute_ranking(
    companies: list[GpwCompany],
    stooq: StooqClient,
    history_cache: TTLCache,
    history_cache_ttl: int,
    repo: QuoteRepository | None = None,
    today: date | None = None,
    config: VsaConfig | None = None,
) -> list[StockRankingItem]:
    """Fetch history for all companies, run VSA analysis, apply pre-filters, rank.

    Args:
        companies:          All tracked GPW companies.
        stooq:              stooq.pl client (fallback data source).
        history_cache:      In-memory TTL cache for per-ticker OHLCV lists.
        history_cache_ttl:  Seconds before cache entries expire.
        repo:               Persistent quote repository; ``None`` = no DB.
        today:              Override "today" (used in tests).
        config:             VSA detection settings; ``None`` = defaults.
    """
    if today is None:
        today = date.today()

    from_date = today - timedelta(days=_HISTORY_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote] | None:
        """Return quotes from cache → repo → stooq, in that priority order."""
        cache_key = f"history:{ticker}:{from_date}:None"
        quotes: list[StooqDailyQuote] | None = history_cache.get(cache_key)
        if quotes is not None:
            return quotes

        # Try the DB.
        if repo is not None:
            quotes = await repo.get_quotes(ticker, from_date)
            if quotes:
                history_cache.set(cache_key, quotes, history_cache_ttl)
                return quotes

        # Fall back to stooq.pl.
        async with semaphore:
            try:
                quotes = await stooq.get_daily_history(ticker, from_date=from_date)
            except StooqAccessError as exc:
                logger.warning("Skipping %s: stooq error: %s", ticker, exc)
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error("Skipping %s: unexpected error: %s", ticker, exc)
                return None

            # Persist inside the semaphore so at most _MAX_CONCURRENT DB writes
            # are in flight simultaneously (prevents connection pool exhaustion).
            if repo is not None and quotes:
                try:
                    await repo.upsert_quotes(ticker, quotes)
                except Exception:
                    logger.exception("Failed to persist %s quotes to DB.", ticker)

        history_cache.set(cache_key, quotes or [], history_cache_ttl)
        return quotes or []

    async def fetch_and_analyse(company: GpwCompany) -> StockRankingItem | None:
        # Capitalisation floor (blueprint §5): market cap must exceed 100M PLN.
        # Applied only when the value is known, so missing metadata never
        # silently hides a company from the ranking.
        if company.market_cap is not None and company.market_cap < _MIN_MARKET_CAP_PLN:
            logger.debug("Skipping %s: market cap below floor.", company.ticker)
            return None

        quotes = await fetch_quotes(company.ticker)
        if not quotes or len(quotes) < 25:
            logger.debug("Skipping %s: insufficient history (%d bars).",
                         company.ticker, len(quotes) if quotes else 0)
            return None

        # Guard the analysis + model construction: a single company with
        # malformed data must never 500 the whole ranking — skip it instead.
        try:
            if median_volume_pln(quotes) < _MIN_MEDIAN_VOLUME_PLN:
                logger.debug("Skipping %s: below liquidity threshold.", company.ticker)
                return None

            signals = detect_signals(quotes, config)
            rating_today = compute_rating(signals, today)
            rating_yesterday = compute_rating(signals, today - timedelta(days=1))
            rating_change = rating_today - rating_yesterday

            verdict, days_since = verdict_from_signals(signals, today)

            last_close = float(quotes[-1].close)
            prev_close = float(quotes[-2].close) if len(quotes) >= 2 else last_close
            price_change_pct = (
                round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
            )

            sparkline = [float(q.close) for q in quotes[-_SPARKLINE_BARS:]]

            med_vol_list = sorted(q.volume for q in quotes[-20:])
            n = len(med_vol_list)
            median_vol_shares = int(
                (med_vol_list[n // 2 - 1] + med_vol_list[n // 2]) / 2
                if n % 2 == 0
                else med_vol_list[n // 2]
            )

            return StockRankingItem(
                ticker=company.ticker.upper(),
                name=company.name,
                sector=company.sector,
                last_price=last_close,
                price_change_pct=price_change_pct,
                current_rating=rating_today,
                rating_change=rating_change,
                last_signal=verdict,
                days_since_signal=days_since,
                sparkline=sparkline,
                volume=median_vol_shares,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Skipping %s: analysis failed.", company.ticker)
            return None

    # return_exceptions=True so one failed task can never abort the whole gather.
    results = await asyncio.gather(
        *(fetch_and_analyse(c) for c in companies), return_exceptions=True
    )
    ranking = [r for r in results if isinstance(r, StockRankingItem)]
    ranking.sort(key=lambda r: r.current_rating, reverse=True)
    return ranking
