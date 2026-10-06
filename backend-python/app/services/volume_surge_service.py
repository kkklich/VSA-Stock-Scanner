"""Volume-surge scanner service.

Builds the data behind ``GET /api/stocks/volume-surge``: every tracked GPW
company whose trading volume over the last few sessions is unusually high
compared to its own recent norm.

Method — a multi-day variant of **Relative Volume (RVOL)**, the standard
"unusual volume" screen used by stock scanners (the classic form compares a
single session to an N-day average; averaging the last few sessions is a
stricter smoothing of it, and the classic single-day ratio is reported too):

    volume_ratio = avg(volume, last ``recent_days`` sessions)
                 / median(volume, the ``baseline_days`` sessions before those)

The baseline window deliberately *excludes* the recent window, so a surge
cannot inflate its own reference. The reference is the **median** — the
volume of a typical session — not the mean (changed 2026-09-26, roadmap
#15b). Daily volume is heavily skewed: in the stored GPW history 30% of
20-session baselines held one day at five times the typical volume or more,
usually a report day, and that one day lifted the mean for four weeks and hid
genuine new surges behind it. The median ignores it, and it makes a ratio of
1.0 mean what it says — a typical session (against the mean, a typical GPW
session read 0.86). Published screens typically flag ~1.5–2.0 as elevated and
~3–4 as extreme. Alongside the multi-day ratio the scan reports the classic
single-day RVOL of the latest session and how many of the recent sessions
individually beat the baseline (persistence of the surge).

Relation to VSA: volume is the raw material of the "effort" side of Volume
Spread Analysis — a surge marks professional (institutional) activity. Each
result therefore carries the price change over the surge window (a rough
proxy for the "result" of that effort) and the stock's current VSA rating and
verdict, computed on the same window and with the same settings as the
ranking page. Since that verdict can rest on a signal weeks older than the
surge, each row also says how old its latest signal is and whether it fell
inside the surge window, and it carries the bar-level facts VSA reads —
spread and close position — for the session that carried the most volume,
plus whether the surge pushed the price out of its reference-period range
(``compute_surge_context``). Finally, a row is marked when a company report
date falls in the surge window or on the session just before it
(``report_in_window``): earnings are the commonest cause of a multi-day
surge, and a surge that is simply the market digesting a report reads very
differently from one that arrived unannounced.

Pre-filters, data-source priority (cache → PostgreSQL → stooq live) and the
120-day analysis window are identical to the ranking, and the per-ticker
history cache key is shared with it, so a warm ranking makes this scan cheap.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.analysis.statistics import close_position, median_turnover, median_volume
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
from app.models import (
    GpwCompany,
    StooqDailyQuote,
    VolumeSurgeItem,
    VolumeSurgeResponse,
)
from app.services.cache import NEGATIVE_CACHE_SECONDS, TTLCache
from app.services.exceptions import StooqAccessError
from app.services.ranking_service import CONTEXT_HISTORY_DAYS
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# Same analysis window and pre-filters as the ranking (blueprint §5). The
# FETCH window is the ranking's longer CONTEXT_HISTORY_DAYS (52-week context)
# so both services keep sharing one cached per-ticker history; analysis here
# still runs on this 120-day slice.
_HISTORY_DAYS = 120
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
    # The baseline's MEDIAN volume — a typical session — since 2026-09-26.
    # The name is kept because it is the API field ``baselineAvgVolume``.
    baseline_avg_volume: int
    volume_ratio: float
    last_day_ratio: float
    days_above_baseline: int
    price_change_pct: float


@dataclass(frozen=True)
class SurgeContext:
    """Bar-level VSA context for a surge window (unit-testable, no I/O).

    VSA reads every bar by its volume, its spread and where it closed. RVOL
    covers the first; this covers the other two for the session that carried
    the surge, plus where the surge left the price relative to its range.
    """

    # First session of the surge window.
    surge_start: date
    # The session in the window with the most volume (the latest, on a tie).
    peak_date: date
    # Its volume ÷ the baseline (a typical session).
    peak_volume_ratio: float
    # Its close vs the close before it, percent: an up bar or a down bar.
    peak_change_pct: float
    # Its spread (high − low) ÷ the baseline's average spread. ``None`` when
    # the baseline has no range at all (a frozen, suspended stretch).
    peak_spread_ratio: float | None
    # Where it closed within its range: 0 = on the low, 1 = on the high.
    # ``None`` on a zero-range bar.
    peak_close_position: float | None
    # The window traded above the baseline's highest high / below its lowest
    # low — the surge pushed the price out of the range it held before.
    breaks_high: bool
    breaks_low: bool


@dataclass(frozen=True)
class _SurgeWindows:
    """The two windows every surge figure is read from, sliced once.

    ``quotes`` is the whole bar list: the price change and the peak bar's
    change both need the close from *before* the recent window.
    """

    quotes: Sequence[StooqDailyQuote]
    recent: Sequence[StooqDailyQuote]
    baseline: Sequence[StooqDailyQuote]
    # The baseline's median volume — the volume of a typical session. > 0.
    typical_volume: float


def _surge_windows(
    quotes: Sequence[StooqDailyQuote], recent_days: int, baseline_days: int
) -> _SurgeWindows | None:
    """The windows, or ``None`` when the stock cannot be scored at all.

    That is when the history is too short for both windows or the baseline's
    typical volume is zero (e.g. a long trading suspension) — different from
    "not surging". The one place those rules live, so the metrics and the
    context can never disagree about which stocks they cover.
    """
    if recent_days < 1 or baseline_days < 1:
        return None
    if len(quotes) < recent_days + baseline_days:
        return None
    baseline = quotes[-(recent_days + baseline_days) : -recent_days]
    median = median_volume(baseline, lookback=len(baseline))
    typical = float(median) if median is not None else 0.0
    if typical <= 0:
        return None
    return _SurgeWindows(quotes, quotes[-recent_days:], baseline, typical)


def _pct_change(before: StooqDailyQuote, after: StooqDailyQuote) -> float:
    """Close-to-close change, percent (0.0 when the earlier close is not positive)."""
    base = float(before.close)
    return round((float(after.close) - base) / base * 100, 2) if base > 0 else 0.0


def _metrics(w: _SurgeWindows) -> VolumeSurgeMetrics:
    typical = w.typical_volume
    recent_avg = sum(q.volume for q in w.recent) / len(w.recent)
    return VolumeSurgeMetrics(
        recent_avg_volume=int(round(recent_avg)),
        baseline_avg_volume=int(round(typical)),
        volume_ratio=recent_avg / typical,
        last_day_ratio=w.recent[-1].volume / typical,
        days_above_baseline=sum(1 for q in w.recent if q.volume > typical),
        # Close just before the surge window → last close: the price "result"
        # that accompanied the volume "effort" (VSA reads the two together).
        price_change_pct=_pct_change(w.baseline[-1], w.recent[-1]),
    )


def _context(w: _SurgeWindows) -> SurgeContext:
    recent, baseline = w.recent, w.baseline
    # Latest session on a tie: the most recent evidence is the one to read.
    peak_idx = max(range(len(recent)), key=lambda i: (recent[i].volume, i))
    peak = recent[peak_idx]
    before = recent[peak_idx - 1] if peak_idx > 0 else baseline[-1]

    avg_spread = sum(float(q.high - q.low) for q in baseline) / len(baseline)
    peak_spread = float(peak.high - peak.low)
    position = close_position(peak)

    return SurgeContext(
        surge_start=recent[0].date,
        peak_date=peak.date,
        peak_volume_ratio=round(peak.volume / w.typical_volume, 2),
        peak_change_pct=_pct_change(before, peak),
        peak_spread_ratio=round(peak_spread / avg_spread, 2) if avg_spread > 0 else None,
        peak_close_position=round(float(position), 2) if position is not None else None,
        breaks_high=max(q.high for q in recent) > max(q.high for q in baseline),
        breaks_low=min(q.low for q in recent) < min(q.low for q in baseline),
    )


def compute_surge_metrics(
    quotes: Sequence[StooqDailyQuote],
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
) -> VolumeSurgeMetrics | None:
    """Multi-day relative-volume metrics for a chronological bar list.

    ``None`` when the stock cannot be scored (see ``_surge_windows``).
    """
    w = _surge_windows(quotes, recent_days, baseline_days)
    return _metrics(w) if w is not None else None


def compute_surge_context(
    quotes: Sequence[StooqDailyQuote],
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
) -> SurgeContext | None:
    """Spread, close position and range break around a surge window.

    The same windows and ``None`` cases as ``compute_surge_metrics``. The
    spread is judged against the baseline's *average* spread because that is
    the reference the VSA engine uses for "wide" and "narrow" (``vsa.py``:
    the rolling mean spread), so a bar this calls wide is wide in the
    engine's own terms.
    """
    w = _surge_windows(quotes, recent_days, baseline_days)
    return _context(w) if w is not None else None


async def _report_dates(
    repo: QuoteRepository | None, tickers: list[str]
) -> dict[str, list[date]]:
    """Stored report dates per ticker; empty without a database or on failure.

    The flag is a hint on top of the scan, so a failed read degrades to "no
    report known" (logged) instead of failing a scan that is otherwise fine.
    """
    if repo is None or not tickers:
        return {}
    try:
        return await repo.get_report_dates(tickers)
    except Exception:  # noqa: BLE001
        logger.exception("Volume surge: could not read report dates.")
        return {}


def report_in_window(
    report_dates: Iterable[date | None],
    quotes: Sequence[StooqDailyQuote],
    recent_days: int = DEFAULT_RECENT_DAYS,
) -> date | None:
    """The latest report date that falls in the surge window, if any.

    The window reaches back to the session *before* the surge: GPW companies
    mostly publish after the close (Yahoo stamps KGHM's reports 17:05 Warsaw),
    so a report dated that session is traded — and moves volume — on the
    first session of the window. A report dated the *last* session counts
    too, although after the close it has not traded yet: a stored date has no
    time of day, and many companies (most US ones) publish before the open.
    A date after the last session cannot explain the surge.
    """
    if not quotes or recent_days < 1:
        return None
    first = quotes[-(recent_days + 1)] if len(quotes) > recent_days else quotes[0]
    last = quotes[-1]
    inside = [d for d in report_dates if d is not None and first.date <= d <= last.date]
    return max(inside, default=None)


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

    from_date = today - timedelta(days=CONTEXT_HISTORY_DAYS)
    analysis_from = today - timedelta(days=_HISTORY_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    # Separate gate for the DB reads: this scan fans out over the whole
    # universe, and ~290 simultaneous queries against a 15-connection pool
    # would time out rather than queue. See DB_SCAN_CONCURRENCY in
    # app/db/base.py for how the number ties back to the pool size.
    db_semaphore = asyncio.Semaphore(DB_SCAN_CONCURRENCY)

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote] | None:
        """Return quotes from cache → repo → stooq, in that priority order."""
        # Identical key to the ranking's fetch, so both features share one
        # cached 120-day history per ticker.
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
                logger.warning(
                    "Volume surge: skipping %s: data provider error: %s", ticker, exc
                )
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
    ) -> tuple[VolumeSurgeItem, list[StooqDailyQuote]] | None:
        nonlocal scanned

        currency = quote_currency(company)
        if below_market_cap_floor(company.market_cap, currency):
            return None

        quotes = await fetch_quotes(company.ticker)
        # Analysis runs on the ranking's 120-day slice; only the shared fetch
        # window is longer (see CONTEXT_HISTORY_DAYS), so results are
        # identical to a plain 120-day fetch.
        recent = [q for q in quotes or [] if q.date >= analysis_from]
        if len(recent) < 25:
            return None

        # Guard the analysis: one malformed stock must never 500 the scan.
        try:
            if below_liquidity_floor(median_turnover(recent), currency):
                return None

            windows = _surge_windows(recent, recent_days, baseline_days)
            if windows is None:
                return None
            metrics = _metrics(windows)
            scanned += 1
            session_dates.append(recent[-1].date)
            if metrics.volume_ratio < min_ratio:
                return None
            context = _context(windows)

            # VSA context on the same window/settings as the ranking, so the
            # numbers match across pages. As-of the last session date (not
            # the calendar day), matching the ranking.
            signals = detect_signals(recent, config)
            as_of = recent[-1].date
            rating = compute_rating(signals, as_of)
            verdict, days_since = verdict_from_signals(signals, as_of)
            # The verdict is a decayed score over months of signals; say
            # whether any of them is part of the surge, or it reads as if it
            # described the surge when it predates it.
            signal_in_window = any(s.date >= context.surge_start for s in signals)

            item = VolumeSurgeItem(
                ticker=company.ticker.upper(),
                name=company.name,
                market=market_of(company.ticker).id,
                currency=currency,
                sector=company.sector,
                last_price=float(recent[-1].close),
                recent_avg_volume=metrics.recent_avg_volume,
                baseline_avg_volume=metrics.baseline_avg_volume,
                volume_ratio=round(metrics.volume_ratio, 2),
                last_day_ratio=round(metrics.last_day_ratio, 2),
                days_above_baseline=metrics.days_above_baseline,
                price_change_pct=metrics.price_change_pct,
                current_rating=rating,
                last_signal=verdict,
                days_since_signal=days_since,
                signal_in_window=signal_in_window,
                surge_start=context.surge_start,
                peak_date=context.peak_date,
                peak_volume_ratio=context.peak_volume_ratio,
                peak_change_pct=context.peak_change_pct,
                peak_spread_ratio=context.peak_spread_ratio,
                peak_close_position=context.peak_close_position,
                breaks_high=context.breaks_high,
                breaks_low=context.breaks_low,
            )
            return item, recent
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
    for company, result in zip(companies, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Volume surge: skipping %s: %s", company.ticker, result)
    hits = [r for r in results if isinstance(r, tuple)]

    # Recency pre-filter (see _MAX_SESSION_LAG_DAYS): a "surge" on a ticker
    # whose last session lags the newest one across all scanned tickers is
    # months-old news from a suspended/stale listing — drop it. Dataset-global
    # max, not wall-clock, so cached results stay deterministic.
    latest_session = max(session_dates, default=None)
    hits = [
        (item, bars)
        for item, bars in hits
        if latest_session is None
        or (latest_session - bars[-1].date).days <= _MAX_SESSION_LAG_DAYS
    ]

    # Report dates, for the surging stocks only: one query, not one per company.
    report_dates = await _report_dates(repo, [item.ticker.lower() for item, _ in hits])
    hits = [
        (
            item.model_copy(
                update={
                    "report_date": report_in_window(
                        report_dates.get(item.ticker.lower(), ()), bars, recent_days
                    )
                }
            ),
            bars,
        )
        for item, bars in hits
    ]

    items = sorted((item for item, _ in hits), key=lambda i: -i.volume_ratio)
    as_of = max((bars[-1].date for _, bars in hits), default=None)
    return VolumeSurgeResponse(
        as_of=as_of,
        recent_days=recent_days,
        baseline_days=baseline_days,
        min_ratio=min_ratio,
        scanned_count=scanned,
        total_count=len(items),
        items=items,
    )
