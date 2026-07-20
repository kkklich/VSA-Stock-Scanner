"""Volume-surge scanner service.

Builds the data behind ``GET /api/stocks/volume-surge``: every tracked GPW
company whose trading volume over the last few sessions is unusually high
compared to its own recent norm.

Method — a multi-day variant of **Relative Volume (RVOL)**, the standard
"unusual volume" screen used by stock scanners (the classic form compares a
single session to an N-day average; averaging the last few sessions is a
stricter smoothing of it, and the classic single-day ratio is reported too):

    volume_ratio = avg(volume, last ``recent_days`` sessions)
                 / avg(volume, the ``baseline_days`` sessions before those)

The baseline window deliberately *excludes* the recent window, so a surge
cannot inflate its own reference average. A ratio of 1.0 means "normal
activity"; published screens typically flag ~1.5–2.0 as elevated and ~3–4 as
extreme. Alongside the multi-day ratio the scan reports the classic
single-day RVOL of the latest session and how many of the recent sessions
individually beat the baseline average (persistence of the surge).

Relation to VSA: volume is the raw material of the "effort" side of Volume
Spread Analysis — a surge marks professional (institutional) activity. Each
result therefore carries the price change over the surge window (a rough
proxy for the "result" of that effort — the full VSA reading also needs each
bar's spread and close position, which is why the row carries the stock's
current VSA rating and verdict, computed on the same window and with the
same settings as the ranking page).

Pre-filters, data-source priority (cache → PostgreSQL → stooq live) and the
120-day analysis window are identical to the ranking, and the per-ticker
history cache key is shared with it, so a warm ranking makes this scan cheap.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.analysis.statistics import median_volume_pln
from app.analysis.vsa import (
    VsaConfig,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.db.repository import QuoteRepository
from app.models import (
    GpwCompany,
    StooqDailyQuote,
    VolumeSurgeItem,
    VolumeSurgeResponse,
)
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# Same analysis window and pre-filters as the ranking (blueprint §5).
_HISTORY_DAYS = 120
_MIN_MEDIAN_VOLUME_PLN = 100_000.0
_MIN_MARKET_CAP_PLN = 100_000_000
_MAX_CONCURRENT = 4
# Recency pre-filter, same as the ranking: drop tickers whose last bar lags
# the newest session across the scan by more than this many calendar days
# (suspended/stale listings), while tolerating holidays and long weekends.
_MAX_SESSION_LAG_DAYS = 10

# Screen defaults: last 3 sessions vs the 20 sessions before them, flagged
# when the recent average is at least 50 % above the baseline average.
DEFAULT_RECENT_DAYS = 3
DEFAULT_BASELINE_DAYS = 20
DEFAULT_MIN_RATIO = 1.5


@dataclass(frozen=True)
class VolumeSurgeMetrics:
    """Pure volume/price arithmetic for one stock (unit-testable, no I/O).

    The ratios are kept at full precision so the ``min_ratio`` threshold is
    applied exactly; they are rounded only when building the API payload.
    """

    recent_avg_volume: int
    baseline_avg_volume: int
    volume_ratio: float
    last_day_ratio: float
    days_above_baseline: int
    price_change_pct: float


def compute_surge_metrics(
    quotes: Sequence[StooqDailyQuote],
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
) -> VolumeSurgeMetrics | None:
    """Multi-day relative-volume metrics for a chronological bar list.

    Returns ``None`` when the history is too short for both windows or the
    baseline average volume is zero (e.g. a long trading suspension) — such a
    stock cannot be scored, which is different from "not surging".
    """
    if recent_days < 1 or baseline_days < 1:
        return None
    if len(quotes) < recent_days + baseline_days:
        return None

    recent = quotes[-recent_days:]
    baseline = quotes[-(recent_days + baseline_days) : -recent_days]

    baseline_avg = sum(q.volume for q in baseline) / len(baseline)
    if baseline_avg <= 0:
        return None
    recent_avg = sum(q.volume for q in recent) / len(recent)

    # Close just before the surge window → last close: the price "result"
    # that accompanied the volume "effort" (VSA reads the two together).
    entry_close = float(quotes[-(recent_days + 1)].close)
    last_close = float(recent[-1].close)
    price_change_pct = (
        round((last_close - entry_close) / entry_close * 100, 2)
        if entry_close > 0
        else 0.0
    )

    return VolumeSurgeMetrics(
        recent_avg_volume=int(round(recent_avg)),
        baseline_avg_volume=int(round(baseline_avg)),
        volume_ratio=recent_avg / baseline_avg,
        last_day_ratio=recent[-1].volume / baseline_avg,
        days_above_baseline=sum(1 for q in recent if q.volume > baseline_avg),
        price_change_pct=price_change_pct,
    )


async def compute_volume_surge(
    companies: list[GpwCompany],
    stooq: StooqClient,
    history_cache: TTLCache,
    history_cache_ttl: int,
    repo: QuoteRepository | None = None,
    today: date | None = None,
    config: VsaConfig | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> VolumeSurgeResponse:
    """Scan every company passing the ranking pre-filters for a volume surge.

    Args mirror ``ranking_service.compute_ranking`` plus the screen knobs.
    Results are sorted by ``volume_ratio`` descending (strongest surge first);
    ``as_of`` is the newest bar date across the surging stocks.
    """
    if today is None:
        today = date.today()

    from_date = today - timedelta(days=_HISTORY_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote] | None:
        """Return quotes from cache → repo → stooq, in that priority order."""
        # Identical key to the ranking's fetch, so both features share one
        # cached 120-day history per ticker.
        cache_key = f"history:{ticker}:{from_date}:None"
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
                logger.warning("Volume surge: skipping %s: stooq error: %s", ticker, exc)
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Volume surge: skipping %s: unexpected error: %s", ticker, exc
                )
                return None

            if repo is not None and quotes:
                try:
                    await repo.upsert_quotes(ticker, quotes)
                except Exception:
                    logger.exception("Failed to persist %s quotes to DB.", ticker)

        history_cache.set(cache_key, quotes or [], history_cache_ttl)
        return quotes or []

    scanned = 0
    # Last session date of every scored ticker — the recency pre-filter needs
    # the dataset-global maximum, not just the max over the surging subset
    # (otherwise a lone stale "surge" would define its own reference date).
    session_dates: list[date] = []

    async def scan_company(
        company: GpwCompany,
    ) -> tuple[VolumeSurgeItem, date] | None:
        nonlocal scanned

        if company.market_cap is not None and company.market_cap < _MIN_MARKET_CAP_PLN:
            return None

        quotes = await fetch_quotes(company.ticker)
        if not quotes or len(quotes) < 25:
            return None

        # Guard the analysis: one malformed stock must never 500 the scan.
        try:
            if median_volume_pln(quotes) < _MIN_MEDIAN_VOLUME_PLN:
                return None

            metrics = compute_surge_metrics(quotes, recent_days, baseline_days)
            if metrics is None:
                return None
            scanned += 1
            session_dates.append(quotes[-1].date)
            if metrics.volume_ratio < min_ratio:
                return None

            # VSA context on the same window/settings as the ranking, so the
            # numbers match across pages. As-of the last session date (not
            # the calendar day), matching the ranking.
            signals = detect_signals(quotes, config)
            as_of = quotes[-1].date
            rating = compute_rating(signals, as_of)
            verdict, _ = verdict_from_signals(signals, as_of)

            item = VolumeSurgeItem(
                ticker=company.ticker.upper(),
                name=company.name,
                sector=company.sector,
                last_price=float(quotes[-1].close),
                recent_avg_volume=metrics.recent_avg_volume,
                baseline_avg_volume=metrics.baseline_avg_volume,
                volume_ratio=round(metrics.volume_ratio, 2),
                last_day_ratio=round(metrics.last_day_ratio, 2),
                days_above_baseline=metrics.days_above_baseline,
                price_change_pct=metrics.price_change_pct,
                current_rating=rating,
                last_signal=verdict,
            )
            return item, quotes[-1].date
        except Exception:  # noqa: BLE001
            logger.exception("Volume surge: skipping %s: analysis failed.", company.ticker)
            return None

    results = await asyncio.gather(
        *(scan_company(c) for c in companies), return_exceptions=True
    )
    # scan_company returns tuple | None, so the isinstance filter below drops
    # nothing legitimate — but an exception that escaped its guard (e.g. the
    # DB dying inside fetch_quotes) must be logged, or a broken scan would
    # come back as an empty 200 that looks like a quiet market.
    for company, result in zip(companies, results):
        if isinstance(result, BaseException):
            logger.error("Volume surge: skipping %s: %s", company.ticker, result)
    hits = [r for r in results if isinstance(r, tuple)]

    # Recency pre-filter (see _MAX_SESSION_LAG_DAYS): a "surge" on a ticker
    # whose last session lags the newest one across all scanned tickers is
    # months-old news from a suspended/stale listing — drop it. Dataset-global
    # max, not wall-clock, so cached results stay deterministic.
    latest_session = max(session_dates, default=None)
    hits = [
        (item, last_bar)
        for item, last_bar in hits
        if latest_session is None
        or (latest_session - last_bar).days <= _MAX_SESSION_LAG_DAYS
    ]
    items = sorted((item for item, _ in hits), key=lambda i: -i.volume_ratio)
    as_of = max((d for _, d in hits), default=None)
    return VolumeSurgeResponse(
        as_of=as_of,
        recent_days=recent_days,
        baseline_days=baseline_days,
        min_ratio=min_ratio,
        scanned_count=scanned,
        total_count=len(items),
        items=items,
    )
