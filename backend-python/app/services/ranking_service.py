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

from app.analysis.ai_insight import analyze_stock
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
# Recency pre-filter: exclude suspended/stale listings, whose last bar keeps
# falling further behind the rest of the market while their rating (keyed to
# their own last session) stays frozen. A ticker is dropped when its last bar
# is more than this many calendar days older than the newest session across
# the whole scan — dataset-global, not wall-clock, so cached results stay
# deterministic; 10 days tolerates holidays and long weekends.
_MAX_SESSION_LAG_DAYS = 10


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

    async def fetch_and_analyse(
        company: GpwCompany,
    ) -> tuple[StockRankingItem, date] | None:
        """Analyse one company; returns (item, its last session date) or None."""
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

            # Ratings are keyed to the last SESSION date, not the wall-clock
            # date: identical data must yield identical ratings whether the
            # ranking runs on Friday evening or Sunday (no weekend decay).
            last_bar_date = quotes[-1].date
            rating_today = compute_rating(signals, last_bar_date)

            # ratingChange = how the newest session changed the rating: the
            # rating as of the last bar minus the rating as it stood after
            # the previous bar (excluding any signal fired on the last bar).
            if len(quotes) >= 2:
                prev_bar_date = quotes[-2].date
                prior_signals = [s for s in signals if s.date < last_bar_date]
                rating_change = rating_today - compute_rating(
                    prior_signals, prev_bar_date
                )
            else:
                rating_change = 0

            verdict, days_since = verdict_from_signals(signals, last_bar_date)

            # Local AI-insight second opinion — reuses the quotes/signals/rating
            # already computed above (no extra I/O). We only surface its
            # confidence here; the full narrative lives on the detail endpoint.
            ai = analyze_stock(
                ticker=company.ticker,
                name=company.name,
                quotes=quotes,
                signals=signals,
                rating=rating_today,
            )

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

            item = StockRankingItem(
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
                ai_confidence=ai.confidence,
            )
            return item, last_bar_date
        except Exception:  # noqa: BLE001
            logger.exception("Skipping %s: analysis failed.", company.ticker)
            return None

    # return_exceptions=True so one failed task can never abort the whole gather.
    results = await asyncio.gather(
        *(fetch_and_analyse(c) for c in companies), return_exceptions=True
    )
    # An exception that escaped fetch_and_analyse's guard (e.g. the DB dying
    # mid-scan) must be logged, or a broken run would look like an empty market.
    for company, result in zip(companies, results):
        if isinstance(result, BaseException):
            logger.error("Ranking: skipping %s: %s", company.ticker, result)
    pairs = [r for r in results if isinstance(r, tuple)]

    # Recency pre-filter (see _MAX_SESSION_LAG_DAYS): a ticker whose last bar
    # lags the newest session in this run by more than the tolerance has
    # stopped trading — drop it instead of ranking its frozen rating.
    latest_session = max((d for _, d in pairs), default=None)
    ranking = [
        item
        for item, last_bar in pairs
        if latest_session is None
        or (latest_session - last_bar).days <= _MAX_SESSION_LAG_DAYS
    ]
    ranking.sort(key=lambda r: r.current_rating, reverse=True)
    return ranking
