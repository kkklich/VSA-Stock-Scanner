"""Chart timeframes: the bar sizes the stock chart can be viewed at.

The stock page used to show one thing only — daily candles. This module adds
the other bar sizes a VSA reader expects (30m, 1h, 4h, 1d, 1w) and knows, for
each, where its bars come from:

* ``1d``  — the stored end-of-day bars, exactly as before (the app's own data).
* ``1w``  — those same daily bars aggregated into ISO-week candles
  (``app.analysis.weekly.resample_weekly``); no new data needed.
* ``30m`` / ``1h`` — intraday bars fetched live from Yahoo Finance, which the
  app does not store. Yahoo caps how far back intraday history goes (see
  ``max_lookback_days``), so these timeframes cover weeks/months, not years.
* ``4h``  — Yahoo has no 4-hour bar, so it is aggregated from the 1h bars.

Volume Spread Analysis itself is timeframe-agnostic — Tom Williams reads the
same spread/volume relationships on any bar size — which is why the unchanged
VSA engine can be pointed at any of these series. What is *not* timeframe-
agnostic is the rest of the app: the ranking, the rating and the daily-
calibrated trading methods (Minervini's 200-*day* MA, the breakout's 50-*day*
base) are defined on daily bars and stay daily no matter what the chart shows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

TimeframeId = Literal["30m", "1h", "4h", "1d", "1w"]

DEFAULT_TIMEFRAME: TimeframeId = "1d"


@dataclass(frozen=True)
class IntradayBar:
    """One intraday OHLCV bar.

    Deliberately mirrors ``StooqDailyQuote`` field for field — including the
    name ``date`` — so it can be handed to the VSA engine (and anything else
    that reads bars) with no changes there. The one difference is that ``date``
    carries a timezone-aware *datetime*: an intraday bar is a moment, not a
    session, and two bars of the same day must stay apart.
    """

    date: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class TimeframeSpec:
    """What one selectable timeframe is made of."""

    id: TimeframeId
    #: Human label shown on the chart's timeframe buttons.
    label: str
    #: True when its bars are intraday moments rather than whole sessions.
    intraday: bool
    #: Interval requested from Yahoo (intraday only).
    yahoo_interval: str | None = None
    #: How many fetched bars are merged into one chart bar (4h = 4 × 1h).
    group: int = 1
    #: Furthest back Yahoo serves this interval — the hard ceiling on history.
    max_lookback_days: int | None = None


# Yahoo's published intraday limits: 30-minute bars reach back 60 days, hourly
# bars 730. Asking for more silently returns less, so the API clamps the
# requested window to these and reports the window it actually served.
TIMEFRAMES: tuple[TimeframeSpec, ...] = (
    TimeframeSpec("30m", "30m", True, yahoo_interval="30m", max_lookback_days=60),
    TimeframeSpec("1h", "1H", True, yahoo_interval="1h", max_lookback_days=730),
    TimeframeSpec("4h", "4H", True, yahoo_interval="1h", group=4, max_lookback_days=730),
    TimeframeSpec("1d", "1D", False),
    TimeframeSpec("1w", "1W", False),
)

_BY_ID: dict[str, TimeframeSpec] = {tf.id: tf for tf in TIMEFRAMES}


def timeframe_ids() -> tuple[str, ...]:
    """Every selectable timeframe id, in display order."""
    return tuple(tf.id for tf in TIMEFRAMES)


def get_timeframe(value: str | None) -> TimeframeSpec | None:
    """Look up a timeframe by id; ``None`` when unknown (caller decides the error)."""
    if value is None:
        return _BY_ID[DEFAULT_TIMEFRAME]
    return _BY_ID.get(value.strip().lower())


def group_intraday(bars: Sequence[IntradayBar], group: int) -> list[IntradayBar]:
    """Merge every ``group`` consecutive intraday bars into one larger bar.

    Grouping is done **within each trading day**, never across the overnight
    gap: a bar spanning Monday's close and Tuesday's open would describe a
    price range that never traded as one stretch. On a GPW session (09:00–17:00
    plus the closing auction) hourly bars therefore group into two clean 4-hour
    bars per day rather than two-and-a-stub — a trailing group shorter than half
    the requested size is folded back into the one before it.

    Each merged bar takes the first open, the highest high, the lowest low, the
    last close, the summed volume, and is stamped with its *first* bar's time,
    which is how a chart labels a candle ("the 13:00 four-hour bar").
    """
    if group <= 1 or not bars:
        return list(bars)

    ordered = sorted(bars, key=lambda b: b.date)

    # Split into trading days first, so no group ever straddles two sessions.
    days: list[list[IntradayBar]] = []
    for bar in ordered:
        if days and days[-1][-1].date.date() == bar.date.date():
            days[-1].append(bar)
        else:
            days.append([bar])

    merged: list[IntradayBar] = []
    for day in days:
        chunks = [day[i : i + group] for i in range(0, len(day), group)]
        # A stubby tail (e.g. GPW's lone 17:00 auction bar) belongs to the
        # session it closed, not to a 4-hour bar made of one print.
        if len(chunks) > 1 and len(chunks[-1]) * 2 < group:
            chunks[-2].extend(chunks.pop())
        for chunk in chunks:
            merged.append(
                IntradayBar(
                    date=chunk[0].date,
                    open=chunk[0].open,
                    high=max(b.high for b in chunk),
                    low=min(b.low for b in chunk),
                    close=chunk[-1].close,
                    volume=sum(b.volume for b in chunk),
                )
            )
    return merged


def bars_per_session(spec: TimeframeSpec) -> int:
    """Roughly how many bars of this timeframe one GPW session produces.

    Used to translate a window expressed in *days* into a bar count (and back),
    e.g. for the chart's signal-context window. GPW trades 09:00–17:00, so a
    session yields ~17 half-hour bars, ~9 hourly bars, ~2 four-hour bars.
    """
    if not spec.intraday:
        return 1
    per_hour = {"30m": 2, "1h": 1}.get(spec.yahoo_interval or "", 1)
    return max(1, round(9 * per_hour / spec.group))


def clamp_lookback_days(spec: TimeframeSpec, requested_days: int) -> int:
    """Trim a requested history window to what the source can actually serve."""
    days = max(1, requested_days)
    if spec.max_lookback_days is not None:
        days = min(days, spec.max_lookback_days)
    return days


def first_bar_date(bars: Sequence[IntradayBar]) -> date | None:
    """Calendar date of the oldest bar, or ``None`` for an empty series."""
    return bars[0].date.date() if bars else None
