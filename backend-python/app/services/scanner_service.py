"""Scanner back-test statistics.

For each VSA signal type, computes across all tracked GPW stocks over the
last 120 sessions:

- ``count``        — total signal occurrences (excluding the most recent
                     *_FORWARD_SESSIONS* bars, which cannot yet be evaluated).
- ``success_pct``  — % of occurrences where the forward return over the next
                     *_FORWARD_SESSIONS* trading days beat the stock's own
                     baseline (its median forward return over the same
                     horizon) in the signal's direction. Comparing against
                     the stock's baseline rather than zero means the stat
                     measures signal skill, not overall market drift.
- ``reward_risk``  — average winner magnitude ÷ average loser magnitude,
                     where magnitude is the excess over the baseline (the
                     same frame the win/loss classification uses). ``None``
                     when the ratio is undefined: wins but no losses, or no
                     judged occurrences at all.
- ``active_count`` — stocks whose most recent signal is this type right now.

These stats are computed entirely from the same OHLCV history the ranking
uses, so no extra network calls are needed after a warm-cache ranking run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from app.analysis.vsa import SignalType, VsaConfig, detect_signals
from app.db.repository import QuoteRepository
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.ranking_service import CONTEXT_HISTORY_DAYS
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# Analysis window — identical to the ranking's, so the back-test judges the
# same signals the ranking shows. The FETCH window is the ranking's longer
# CONTEXT_HISTORY_DAYS (52-week context) so both keep sharing one cached
# per-ticker history.
_HISTORY_DAYS = 120
_FORWARD_SESSIONS = 10  # look-ahead window for the back-test
_MAX_CONCURRENT = 4

# Map backend SignalName enum values to the display names used by the UI.
SIGNAL_DISPLAY: dict[str, str] = {
    "Spring": "Spring",
    "SOS": "Sign of Strength",
    "Successful Test": "Successful Test",
    "Upthrust": "Upthrust",
    "No Demand": "No Demand",
    "SOW": "Sign of Weakness",
}


@dataclass
class SignalEffStats:
    """Aggregated back-test result for one signal type."""

    signal: str
    count: int = 0
    success_pct: float = 0.0
    # None when the ratio is undefined: no judged occurrences at all, or
    # wins but no losses (division by zero is not "the worst score").
    reward_risk: float | None = None
    active_count: int = 0


@dataclass
class _Acc:
    """Running accumulator — not exported."""

    wins: int = 0
    total: int = 0
    active: int = 0
    win_mag: list[float] = field(default_factory=list)
    loss_mag: list[float] = field(default_factory=list)


async def compute_scanner_stats(
    companies: list[GpwCompany],
    stooq: StooqClient,
    history_cache: TTLCache,
    history_cache_ttl: int,
    repo: QuoteRepository | None = None,
    today: date | None = None,
    config: VsaConfig | None = None,
) -> list[SignalEffStats]:
    """Back-test all VSA signals across tracked companies and return per-signal stats."""
    if today is None:
        today = date.today()

    from_date = today - timedelta(days=CONTEXT_HISTORY_DAYS)
    analysis_from = today - timedelta(days=_HISTORY_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    acc: dict[str, _Acc] = {name: _Acc() for name in SIGNAL_DISPLAY.values()}

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote]:
        cache_key = f"history:{ticker}:{from_date}:None"
        cached: list[StooqDailyQuote] | None = history_cache.get(cache_key)
        if cached is not None:
            return cached

        if repo is not None:
            rows = await repo.get_quotes(ticker, from_date)
            if rows:
                history_cache.set(cache_key, rows, history_cache_ttl)
                return rows

        async with semaphore:
            try:
                rows = await stooq.get_daily_history(ticker, from_date=from_date)
            except Exception as exc:  # noqa: BLE001 — includes StooqAccessError
                logger.debug("Scanner: skip %s — %s", ticker, exc)
                rows = []
            if repo is not None and rows:
                try:
                    await repo.upsert_quotes(ticker, rows)
                except Exception:
                    logger.exception("Scanner: DB write failed for %s.", ticker)

        history_cache.set(cache_key, rows or [], history_cache_ttl)
        return rows or []

    async def process(company: GpwCompany) -> None:
        fetched = await fetch_quotes(company.ticker)
        # Analysis runs on the ranking's 120-day slice; only the shared fetch
        # window is longer (see CONTEXT_HISTORY_DAYS), so the stats are
        # identical to a plain 120-day fetch.
        quotes = [q for q in fetched if q.date >= analysis_from]
        if len(quotes) < 25:
            return

        signals = detect_signals(quotes, config)
        if not signals:
            return

        # active_count: this company currently shows this signal as its latest.
        latest = max(signals, key=lambda s: s.date)
        display = SIGNAL_DISPLAY.get(latest.signal_name.value)
        if display and display in acc:
            acc[display].active += 1

        # Back-test: evaluate signals fired early enough to have forward data.
        eval_cutoff = today - timedelta(days=_FORWARD_SESSIONS + 1)

        # Build a date → close lookup for fast forward-price lookup.
        quotes_sorted = sorted(quotes, key=lambda q: q.date)
        dates = [q.date for q in quotes_sorted]
        closes = [float(q.close) for q in quotes_sorted]

        # Baseline: this stock's own typical (median) forward return over the
        # horizon, measured from every bar in the window — what a random-day
        # entry would have done. Success must beat this baseline in the
        # signal's direction, otherwise the stat just measures market drift
        # (same idea as the trust-score back-test).
        forward_returns = [
            (closes[i + _FORWARD_SESSIONS] - closes[i]) / closes[i] * 100
            for i in range(len(closes) - _FORWARD_SESSIONS)
            if closes[i] > 0
        ]
        if not forward_returns:
            return
        baseline = median(forward_returns)

        for sig in signals:
            if sig.date > eval_cutoff:
                continue  # not enough future data

            display = SIGNAL_DISPLAY.get(sig.signal_name.value)
            if not display or display not in acc:
                continue

            # Find index of signal bar.
            try:
                idx = dates.index(sig.date)
            except ValueError:
                continue

            # Need at least _FORWARD_SESSIONS bars after the signal.
            if idx + _FORWARD_SESSIONS >= len(quotes_sorted):
                continue

            entry = closes[idx]
            exit_ = closes[idx + _FORWARD_SESSIONS]
            if entry <= 0:
                continue

            pct = (exit_ - entry) / entry * 100
            bullish = sig.type == SignalType.BULLISH
            # Beat the stock's own baseline drift, not just zero.
            success = pct > baseline if bullish else pct < baseline
            # Magnitude in the same baseline-excess frame the classification
            # uses: |pct| would credit a bearish "win" at +2.9% vs a +3.0%
            # baseline with 2.9pp of reward although the short barely edged
            # out the drift (and mirror-image for bullish "losses").
            magnitude = abs(pct - baseline)

            bucket = acc[display]
            bucket.total += 1
            if success:
                bucket.wins += 1
                bucket.win_mag.append(magnitude)
            else:
                bucket.loss_mag.append(magnitude)

    results = await asyncio.gather(
        *(process(c) for c in companies), return_exceptions=True
    )
    # A ticker whose task raised (e.g. the DB dying mid-scan) silently
    # contributes nothing to the stats — log it so the gap is visible.
    for company, result in zip(companies, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Scanner stats: skipping %s: %s", company.ticker, result)

    result: list[SignalEffStats] = []
    for display_name, bucket in acc.items():
        if bucket.total == 0:
            result.append(SignalEffStats(signal=display_name, active_count=bucket.active))
            continue

        success_pct = round(bucket.wins / bucket.total * 100, 1)
        avg_win = (sum(bucket.win_mag) / len(bucket.win_mag)) if bucket.win_mag else 0.0
        avg_loss = (sum(bucket.loss_mag) / len(bucket.loss_mag)) if bucket.loss_mag else 0.0
        if avg_loss > 0:
            rr: float | None = round(avg_win / avg_loss, 2)
        elif bucket.win_mag:
            # Wins but zero losses: the ratio is undefined (division by
            # zero), not 0 — report None instead of the worst possible score.
            rr = None
        else:
            # No wins either: all judged occurrences were losses of zero
            # baseline-excess magnitude — a defined (and worst) ratio of 0.
            rr = 0.0

        result.append(SignalEffStats(
            signal=display_name,
            count=bucket.total,
            success_pct=success_pct,
            reward_risk=rr,
            active_count=bucket.active,
        ))

    # Return in canonical signal order.
    order = list(SIGNAL_DISPLAY.values())
    result.sort(key=lambda r: order.index(r.signal) if r.signal in order else 99)
    return result
