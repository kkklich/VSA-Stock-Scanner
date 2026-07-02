"""Tests for app/analysis/statistics.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.analysis.statistics import (
    close_position,
    median_volume,
    median_volume_pln,
    relative_volume,
)
from app.models import StooqDailyQuote


def _bar(
    close: float = 100.0,
    open_: float = 99.0,
    high: float = 101.0,
    low: float = 98.0,
    volume: int = 10_000,
    d: str = "2026-01-01",
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=date.fromisoformat(d),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


class TestClosePosition:
    def test_closes_at_high(self) -> None:
        bar = _bar(close=101.0, high=101.0, low=98.0)
        assert close_position(bar) == Decimal("1")

    def test_closes_at_low(self) -> None:
        bar = _bar(close=98.0, high=101.0, low=98.0)
        assert close_position(bar) == Decimal("0")

    def test_closes_at_midpoint(self) -> None:
        bar = _bar(close=99.5, high=101.0, low=98.0)
        assert close_position(bar) == Decimal("0.5")

    def test_zero_range_returns_none(self) -> None:
        bar = _bar(close=100.0, high=100.0, low=100.0)
        assert close_position(bar) is None


class TestMedianVolume:
    def test_odd_count(self) -> None:
        bars = [_bar(volume=v) for v in [10, 30, 20]]
        result = median_volume(bars, lookback=3)
        assert result == Decimal("20")

    def test_even_count(self) -> None:
        bars = [_bar(volume=v) for v in [10, 20, 30, 40]]
        result = median_volume(bars, lookback=4)
        assert result == Decimal("25")

    def test_uses_trailing_lookback(self) -> None:
        # First bar (volume 1_000) is outside the lookback=2 window.
        bars = [_bar(volume=1_000), _bar(volume=100), _bar(volume=200)]
        result = median_volume(bars, lookback=2)
        assert result == Decimal("150")

    def test_empty_returns_none(self) -> None:
        assert median_volume([]) is None


class TestRelativeVolume:
    def test_above_average(self) -> None:
        bars = [_bar(volume=100)] * 20 + [_bar(volume=200)]
        result = relative_volume(bars, lookback=20)
        assert result is not None
        assert float(result) == pytest.approx(2.0)

    def test_insufficient_history_returns_none(self) -> None:
        bars = [_bar(volume=100)] * 10
        assert relative_volume(bars, lookback=20) is None

    def test_zero_average_returns_none(self) -> None:
        bars = [_bar(volume=0)] * 21
        assert relative_volume(bars, lookback=20) is None


class TestMedianVolumePln:
    def test_returns_volume_times_close(self) -> None:
        bars = [_bar(volume=1_000, close=200.0)] * 20
        result = median_volume_pln(bars, lookback=20)
        assert result == pytest.approx(200_000.0)

    def test_empty_returns_zero(self) -> None:
        assert median_volume_pln([]) == 0.0
