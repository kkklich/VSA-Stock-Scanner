"""Tests for the multi-timeframe (weekly) VSA analysis."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analysis.weekly import (
    _MIN_WEEKLY_BARS,
    WeeklyView,
    compute_weekly_view,
    resample_weekly,
    weekly_agreement,
)
from app.models import StooqDailyQuote


def _bar(
    d: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=date.fromisoformat(d),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _daily_series(n_days: int, base_price: float = 100.0) -> list[StooqDailyQuote]:
    """Bland daily bars over ``n_days`` consecutive calendar days (no signals)."""
    start = date(2025, 1, 6)  # a Monday
    return [
        _bar(
            (start + timedelta(days=i)).isoformat(),
            base_price,
            base_price + 1,
            base_price - 1,
            base_price,
            50_000,
        )
        for i in range(n_days)
    ]


# ── resample_weekly ───────────────────────────────────────────────────────────


def test_resample_weekly_empty() -> None:
    assert resample_weekly([]) == []


def test_resample_weekly_aggregates_ohlcv_and_groups_across_year_boundary() -> None:
    # Mon 2025-12-29 → Sun 2026-01-04 is ISO week 2026-W01, so these three bars
    # (which straddle the calendar-year boundary) must collapse into ONE weekly
    # candle — a common off-by-one bug if you group by (calendar year, week).
    bars = [
        _bar("2025-12-29", 10, 12, 9, 11, 100),  # Mon
        _bar("2025-12-31", 11, 15, 10, 13, 200),  # Wed
        _bar("2026-01-02", 13, 14, 8, 9, 150),  # Fri
        _bar("2026-01-05", 9, 11, 8, 10, 50),  # next Mon (ISO 2026-W02)
    ]
    weekly = resample_weekly(bars)
    assert len(weekly) == 2

    w1 = weekly[0]
    assert w1.date == date(2026, 1, 2)  # last session of the week
    assert w1.open == Decimal("10")  # first open
    assert w1.high == Decimal("15")  # max high
    assert w1.low == Decimal("8")  # min low
    assert w1.close == Decimal("9")  # last close
    assert w1.volume == 450  # summed

    w2 = weekly[1]
    assert w2.date == date(2026, 1, 5)
    assert w2.volume == 50


def test_resample_weekly_sorts_unordered_input() -> None:
    bars = [
        _bar("2025-01-08", 11, 15, 10, 13, 200),  # Wed
        _bar("2025-01-06", 10, 12, 9, 11, 100),  # Mon (earlier)
    ]
    weekly = resample_weekly(bars)
    assert len(weekly) == 1
    # open comes from the chronologically first bar even though it was passed last
    assert weekly[0].open == Decimal("10")
    assert weekly[0].close == Decimal("13")


# ── weekly_agreement ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("daily", "weekly", "expected"),
    [
        ("Strong Buy", "Buy", "confirms"),
        ("Buy", "Strong Buy", "confirms"),
        ("Strong Sell", "Sell", "confirms"),
        ("Sell", "Strong Sell", "confirms"),
        ("Strong Buy", "Sell", "conflicts"),
        ("Buy", "Strong Sell", "conflicts"),
        ("Strong Sell", "Buy", "conflicts"),
        ("Buy", "Hold", "neutral"),
        ("Hold", "Strong Buy", "neutral"),
        ("Hold", "Hold", "neutral"),
    ],
)
def test_weekly_agreement(daily: str, weekly: str, expected: str) -> None:
    assert weekly_agreement(daily, weekly) == expected


# ── compute_weekly_view ───────────────────────────────────────────────────────


def test_weekly_view_unavailable_when_history_too_short() -> None:
    # A couple of weeks of daily bars is nowhere near _MIN_WEEKLY_BARS.
    view = compute_weekly_view(_daily_series(10))
    assert view == WeeklyView(available=False, weekly_bars=view.weekly_bars)
    assert view.available is False
    assert view.rating is None
    assert view.verdict is None
    assert view.weekly_bars < _MIN_WEEKLY_BARS


def test_weekly_view_available_on_long_bland_history() -> None:
    # ~37 ISO weeks of bland bars: enough weekly context to run the engine, but
    # no VSA structure — so a neutral (Hold / rating 50) reading.
    view = compute_weekly_view(_daily_series(260))
    assert view.available is True
    assert view.weekly_bars >= _MIN_WEEKLY_BARS
    assert view.rating == 50
    assert view.verdict == "Hold"


def test_weekly_view_empty_history() -> None:
    view = compute_weekly_view([])
    assert view.available is False
    assert view.weekly_bars == 0
