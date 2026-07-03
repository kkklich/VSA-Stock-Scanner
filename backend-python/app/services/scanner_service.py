"""Scanner back-test statistics.

For each VSA signal type, computes across all tracked GPW stocks over the
last 120 sessions:

- ``count``        — total signal occurrences (excluding the most recent
                     *_FORWARD_SESSIONS* bars, which cannot yet be evaluated).
- ``success_pct``  — % of occurrences where price moved in the expected
                     direction over the next *_FORWARD_SESSIONS* trading days
                     (up for bullish signals, down for bearish ones).
- ``reward_risk``  — average winner magnitude ÷ average loser magnitude.
- ``active_count`` — stocks whose most recent signal is this type right now.

These stats are computed entirely from the same OHLCV history the ranking
uses, so no extra network calls are needed after a warm-cache ranking run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.analysis.vsa import SignalType, VsaConfig, detect_signals
from app.db.repository import QuoteRepository
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

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
    reward_risk: float = 0.0
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

    from_date = today - timedelta(days=_HISTORY_DAYS)
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
        quotes = await fetch_quotes(company.ticker)
        if not quotes or len(quotes) < 25:
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
            success = pct > 0 if bullish else pct < 0
            magnitude = abs(pct)

            bucket = acc[display]
            bucket.total += 1
            if success:
                bucket.wins += 1
                bucket.win_mag.append(magnitude)
            else:
                bucket.loss_mag.append(magnitude)

    await asyncio.gather(*(process(c) for c in companies), return_exceptions=True)

    result: list[SignalEffStats] = []
    for display_name, bucket in acc.items():
        if bucket.total == 0:
            result.append(SignalEffStats(signal=display_name, active_count=bucket.active))
            continue

        success_pct = round(bucket.wins / bucket.total * 100, 1)
        avg_win = (sum(bucket.win_mag) / len(bucket.win_mag)) if bucket.win_mag else 0.0
        avg_loss = (sum(bucket.loss_mag) / len(bucket.loss_mag)) if bucket.loss_mag else 0.0
        rr = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

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
