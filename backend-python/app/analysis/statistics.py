"""Descriptive statistics over OHLCV bars.

These are the building blocks the VSA detector and the ranking pre-filters rely
on. They operate on plain sequences of ``StooqDailyQuote`` so they stay easy to
unit-test, free of any web or database concerns.

Stub module — implementations land with the ingestion/ranking workflow
(see agent/DOCUMENTATION.md §5, §7). The signatures below define the intended
contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.models import StooqDailyQuote


def close_position(bar: StooqDailyQuote) -> Decimal | None:
    """Where the close sits within the bar's range, as a fraction 0.0–1.0.

    0.0 = closed on the low, 1.0 = closed on the high. Returns ``None`` for a
    zero-range bar (high == low). VSA reads a high close as strength, a low close
    as weakness.
    """
    spread = bar.high - bar.low
    if spread <= 0:
        return None
    return (bar.close - bar.low) / spread


def relative_volume(bars: Sequence[StooqDailyQuote], lookback: int = 20) -> Decimal | None:
    """Latest bar's volume divided by the average volume of the prior ``lookback`` bars.

    A value > 1 means above-average participation. Returns ``None`` when there is
    not enough history. Not yet implemented.
    """
    raise NotImplementedError


def median_volume(bars: Sequence[StooqDailyQuote], lookback: int = 20) -> Decimal | None:
    """Median volume over the trailing ``lookback`` sessions.

    Feeds the liquidity pre-filter (20-session median volume > 100,000 PLN).
    Not yet implemented.
    """
    raise NotImplementedError
