"""Multi-timeframe (weekly) VSA analysis.

VSA analysts confirm a daily signal by checking that the weekly chart tells the
same story — strength on the daily that also shows on the weekly is far more
trustworthy than strength the higher timeframe contradicts (Master the Markets
stresses reading a signal against the larger background). This module resamples
a stock's stored daily bars into weekly candles and runs the *same* VSA engine
on them, then reports whether the weekly verdict confirms, conflicts with, or is
neutral toward the daily one.

No new data source is needed: the weekly bars are aggregated from the daily
OHLCV the app already stores.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.vsa import (
    VsaConfig,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.models import StooqDailyQuote

# Minimum number of weekly bars before a weekly reading is trusted. The VSA
# engine needs a full rolling context (default lookback 20) plus a warm-up
# buffer, so ~25 weekly bars is the floor; 30 (≈ seven months of trading) leaves
# a little scanning room beyond that. Below this the stock is a recent listing —
# or the DB has too little history — and no weekly badge is shown rather than a
# misleading "neutral" read from three weekly candles. The ranking fetches ~54
# weeks per ticker (CONTEXT_HISTORY_DAYS), so an established stock clears this.
_MIN_WEEKLY_BARS = 30

# Verdict → direction, shared with the agreement logic below.
_BULLISH_VERDICTS = frozenset({"Strong Buy", "Buy"})
_BEARISH_VERDICTS = frozenset({"Strong Sell", "Sell"})


@dataclass(frozen=True)
class WeeklyView:
    """The weekly-timeframe VSA read of one stock.

    ``available`` is False when the stored history is too short to form enough
    weekly bars to analyse; ``rating``/``verdict`` are then None.
    """

    available: bool
    rating: int | None = None
    verdict: str | None = None
    # How many weekly bars the daily history resampled to (diagnostic).
    weekly_bars: int = 0


def resample_weekly(bars: Sequence[StooqDailyQuote]) -> list[StooqDailyQuote]:
    """Aggregate chronological daily OHLCV bars into weekly candles.

    Bars are grouped by ISO (year, week) — Monday-to-Sunday weeks, so a week
    that straddles a year boundary stays one bar. Each weekly candle takes the
    week's first open, the max high, the min low, the last close, the summed
    volume, and is dated to the week's last trading session. The most recent
    week may be partial (the week still in progress); that is the correct
    "forming" weekly bar and is kept.

    The input need not be pre-sorted — it is sorted by date defensively — but
    Decimal/int types are preserved so the result feeds the VSA engine exactly
    like real daily bars.
    """
    if not bars:
        return []

    ordered = sorted(bars, key=lambda b: b.date)
    groups: dict[tuple[int, int], list[StooqDailyQuote]] = {}
    order: list[tuple[int, int]] = []
    for b in ordered:
        iso = b.date.isocalendar()
        key = (iso.year, iso.week)
        bucket = groups.get(key)
        if bucket is None:
            groups[key] = [b]
            order.append(key)
        else:
            bucket.append(b)

    weekly: list[StooqDailyQuote] = []
    for key in order:
        week = groups[key]  # chronological within the week (input was sorted)
        weekly.append(
            StooqDailyQuote(
                date=week[-1].date,
                open=week[0].open,
                high=max(q.high for q in week),
                low=min(q.low for q in week),
                close=week[-1].close,
                volume=sum(q.volume for q in week),
            )
        )
    return weekly


def compute_weekly_view(
    quotes: Sequence[StooqDailyQuote],
    config: VsaConfig | None = None,
) -> WeeklyView:
    """Run the VSA engine on the weekly resampling of ``quotes``.

    Uses the same ``config`` (the user's Scanner settings) as the daily scan, so
    the higher timeframe is judged by identical rules — the lookback of 20 simply
    becomes 20 *weeks*. The rating and verdict are keyed to the last weekly bar's
    date (no wall-clock decay), mirroring the daily path.
    """
    weekly = resample_weekly(quotes)
    if len(weekly) < _MIN_WEEKLY_BARS:
        return WeeklyView(available=False, weekly_bars=len(weekly))

    signals = detect_signals(weekly, config)
    as_of = weekly[-1].date
    rating = compute_rating(signals, as_of)
    verdict, _ = verdict_from_signals(signals, as_of)
    return WeeklyView(
        available=True, rating=rating, verdict=verdict, weekly_bars=len(weekly)
    )


def _direction(verdict: str) -> int:
    """+1 bullish, -1 bearish, 0 neutral (Hold / unknown)."""
    if verdict in _BULLISH_VERDICTS:
        return 1
    if verdict in _BEARISH_VERDICTS:
        return -1
    return 0


def weekly_agreement(daily_verdict: str, weekly_verdict: str) -> str:
    """How the weekly verdict relates to the daily one.

    ``"confirms"`` when both lean the same non-neutral way (both bullish or both
    bearish — the case a VSA trader wants to see before acting), ``"conflicts"``
    when they lean opposite ways, and ``"neutral"`` when either side is Hold (the
    higher timeframe neither backs nor contradicts the daily call).
    """
    d = _direction(daily_verdict)
    w = _direction(weekly_verdict)
    if d != 0 and w != 0:
        return "confirms" if d == w else "conflicts"
    return "neutral"
