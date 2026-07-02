"""Descriptive statistics over OHLCV bars.

These are the building blocks the VSA detector and the ranking pre-filters rely
on. They operate on plain sequences of ``StooqDailyQuote`` so they stay easy to
unit-test, free of any web or database concerns.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.models import StooqDailyQuote


def close_position(bar: StooqDailyQuote) -> Decimal | None:
    """Where the close sits within the bar's range, as a fraction 0.0–1.0.

    0.0 = closed on the low, 1.0 = closed on the high. Returns ``None`` for a
    zero-range bar (high == low). VSA reads a high close as strength, a low
    close as weakness.
    """
    spread = bar.high - bar.low
    if spread <= 0:
        return None
    return (bar.close - bar.low) / spread


def median_volume(bars: Sequence[StooqDailyQuote], lookback: int = 20) -> Decimal | None:
    """Median volume over the trailing ``lookback`` sessions.

    Feeds the liquidity pre-filter (20-session median volume × close > 100,000 PLN).
    Returns ``None`` when there is not enough history.
    """
    if not bars:
        return None
    sample = [b.volume for b in bars[-lookback:]]
    if not sample:
        return None
    n = len(sample)
    sorted_vols = sorted(sample)
    if n % 2 == 0:
        mid = (sorted_vols[n // 2 - 1] + sorted_vols[n // 2]) / 2
    else:
        mid = sorted_vols[n // 2]
    return Decimal(str(mid))


def relative_volume(bars: Sequence[StooqDailyQuote], lookback: int = 20) -> Decimal | None:
    """Latest bar's volume divided by the mean volume of the prior ``lookback`` bars.

    A value > 1 means above-average participation. Returns ``None`` when there is
    not enough history or average volume is zero.
    """
    if len(bars) < lookback + 1:
        return None
    prior = bars[-(lookback + 1):-1]
    avg = sum(b.volume for b in prior) / len(prior)
    if avg == 0:
        return None
    return Decimal(str(bars[-1].volume / avg))


def median_volume_pln(bars: Sequence[StooqDailyQuote], lookback: int = 20) -> float:
    """Median of (volume × close) over the trailing ``lookback`` sessions, in PLN.

    Used to enforce the liquidity pre-filter: > 100,000 PLN median daily turnover.
    Returns 0.0 when there is not enough history.
    """
    sample = [float(b.volume) * float(b.close) for b in bars[-lookback:]]
    if not sample:
        return 0.0
    n = len(sample)
    sorted_vals = sorted(sample)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    return sorted_vals[n // 2]
