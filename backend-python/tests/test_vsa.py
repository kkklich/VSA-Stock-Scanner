"""Tests for the VSA signal detection and rating engine."""

from __future__ import annotations

import math  # used for atanh in half-life decay test
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analysis.vsa import (
    SignalName,
    SignalType,
    VsaSignal,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.models import StooqDailyQuote


# ── Fixtures / helpers ────────────────────────────────────────────────────────


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


def _normal_bars(n: int = 30, base_price: float = 100.0, base_vol: int = 50_000) -> list[StooqDailyQuote]:
    """Generate ``n`` bland, statistically average bars — no signal should trigger."""
    start = date(2026, 1, 2)
    bars: list[StooqDailyQuote] = []
    price = base_price
    for i in range(n):
        d = (start + timedelta(days=i)).isoformat()
        bars.append(_bar(d, price, price + 1, price - 1, price, base_vol))
    return bars


# ── detect_signals ────────────────────────────────────────────────────────────


class TestDetectSignals:
    def test_insufficient_history_returns_empty(self) -> None:
        bars = _normal_bars(n=10)
        assert detect_signals(bars) == []

    def test_bland_bars_produce_no_signals(self) -> None:
        bars = _normal_bars(n=40)
        # Bland bars should not produce SOS, Spring, SOW, or Upthrust.
        signals = detect_signals(bars)
        names = {s.signal_name for s in signals}
        assert SignalName.SOS not in names
        assert SignalName.SPRING not in names
        assert SignalName.SOW not in names
        assert SignalName.UPTHRUST not in names

    def test_sos_detected_on_wide_up_bar_high_volume(self) -> None:
        bars = _normal_bars(n=25)

        # Inject a wide up-bar with high volume as the last bar.
        # Keep the low within the prior support range (~99) so this tests SOS
        # in isolation, without also qualifying as a Spring (which requires
        # breaking below prior support).
        bars.append(
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=120_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SOS in names

    def test_sow_detected_on_wide_down_bar_high_volume(self) -> None:
        bars = _normal_bars(n=25)

        # Keep high well within prior range so the Upthrust check (higher priority) does not fire.
        # _normal_bars: high = base_price + 1 = 101; use high=100.5 to stay below prior_high.
        bars.append(
            _bar("2026-01-27", open_=100.0, high=100.5, low=88.0, close=89.5, volume=130_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SOW in names

    def test_upthrust_detected_on_wide_spread_high_volume(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # Spikes above prior resistance (101) on a wide spread, closes back
        # below it — the "major" high-volume Upthrust variant (real supply
        # hitting the breakout).
        bars.append(
            _bar("2026-01-27", open_=100.0, high=104.0, low=99.5, close=100.3, volume=90_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.UPTHRUST in names

    def test_upthrust_detected_on_wide_spread_low_volume(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # Same shape but on unusually low volume — the "trap" Upthrust
        # variant: a hollow fake-out with no genuine buying behind it.
        bars.append(
            _bar("2026-01-27", open_=100.0, high=103.5, low=99.6, close=100.2, volume=20_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.UPTHRUST in names

    def test_upthrust_not_detected_on_average_volume(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # Same wide-spread failed-breakout shape, but volume is unremarkable
        # (neither high nor low) — no anomaly, so this should not qualify.
        bars.append(
            _bar("2026-01-27", open_=100.0, high=104.0, low=99.5, close=100.3, volume=50_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.UPTHRUST not in names

    def test_spring_detected_when_price_dips_below_support_and_recovers(self) -> None:
        # 25 normal bars at ~100 (establishing support at 99).
        bars = _normal_bars(n=25, base_price=100.0)

        # Spring (shake-out): dips to 98.5 (below 99 support) on a wide spread,
        # closes at 101.2 (above support) on high volume (absorption).
        bars.append(
            _bar("2026-01-27", open_=100.0, high=101.5, low=98.5, close=101.2, volume=75_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SPRING in names

    def test_no_demand_on_narrow_up_bar_low_volume(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0, base_vol=50_000)

        # No Demand: up bar, narrow spread, low volume.
        # Keep low well away from prior support (99) to avoid the Successful Test rule
        # (higher priority) — Successful Test triggers when low ≈ prior low.
        bars.append(
            _bar("2026-01-27", open_=103.0, high=103.3, low=102.8, close=103.1, volume=15_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.NO_DEMAND in names

    def test_signals_are_chronological(self) -> None:
        bars = _normal_bars(n=25)
        bars.append(_bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=120_000))
        bars.append(_bar("2026-01-28", open_=101.0, high=102.0, low=90.0, close=91.0, volume=130_000))

        signals = detect_signals(bars)
        dates = [s.date for s in signals]
        assert dates == sorted(dates)

    def test_bullish_signal_has_correct_type(self) -> None:
        bars = _normal_bars(n=25)
        bars.append(_bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=120_000))
        signals = detect_signals(bars)
        sos_signals = [s for s in signals if s.signal_name == SignalName.SOS]
        assert all(s.type == SignalType.BULLISH for s in sos_signals)


# ── compute_rating ────────────────────────────────────────────────────────────


class TestComputeRating:
    TODAY = date(2026, 6, 30)

    def test_no_signals_returns_50(self) -> None:
        assert compute_rating([], self.TODAY) == 50

    def test_fresh_bullish_signal_above_50(self) -> None:
        signals = [VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)]
        rating = compute_rating(signals, self.TODAY)
        assert rating > 50

    def test_fresh_bearish_signal_below_50(self) -> None:
        signals = [VsaSignal(date=self.TODAY, signal_name=SignalName.SOW, type=SignalType.BEARISH)]
        rating = compute_rating(signals, self.TODAY)
        assert rating < 50

    def test_rating_clamped_to_0_100(self) -> None:
        # Many strong bullish signals should push rating high but not exceed 100.
        signals = [
            VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)
            for _ in range(20)
        ]
        rating = compute_rating(signals, self.TODAY)
        assert 0 <= rating <= 100

    def test_older_signal_weighs_less_than_recent(self) -> None:
        recent = VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)
        old = VsaSignal(
            date=self.TODAY - timedelta(days=60),
            signal_name=SignalName.SOS,
            type=SignalType.BULLISH,
        )
        rating_recent = compute_rating([recent], self.TODAY)
        rating_old = compute_rating([old], self.TODAY)
        assert rating_recent > rating_old

    def test_future_signals_ignored(self) -> None:
        future = VsaSignal(
            date=self.TODAY + timedelta(days=1),
            signal_name=SignalName.SOS,
            type=SignalType.BULLISH,
        )
        assert compute_rating([future], self.TODAY) == 50

    def test_balanced_signals_near_50(self) -> None:
        bull = VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH, strength=1.0)
        bear = VsaSignal(date=self.TODAY, signal_name=SignalName.SOW, type=SignalType.BEARISH, strength=1.0)
        rating = compute_rating([bull, bear], self.TODAY)
        assert rating == 50

    def test_half_life_decay(self) -> None:
        half_life = 30
        old_signal = VsaSignal(
            date=self.TODAY - timedelta(days=half_life),
            signal_name=SignalName.SOS,
            type=SignalType.BULLISH,
            strength=1.0,
        )
        recent_signal = VsaSignal(
            date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH, strength=1.0
        )
        old_rating = compute_rating([old_signal], self.TODAY, half_life_days=half_life)
        recent_rating = compute_rating([recent_signal], self.TODAY, half_life_days=half_life)
        # Recover the net_score from the rating via atanh (inverse of the final tanh).
        # This tests the decay in score-space, where the relationship is exact.
        old_score = math.atanh((old_rating - 50) / 50)
        recent_score = math.atanh((recent_rating - 50) / 50)
        # recent_score should be twice old_score because the old signal's weight = 0.5.
        assert abs(recent_score / old_score - 2.0) < 0.05


# ── verdict_from_signals ──────────────────────────────────────────────────────


class TestVerdictFromSignals:
    TODAY = date(2026, 6, 30)

    def test_no_signals_returns_hold(self) -> None:
        verdict, days = verdict_from_signals([], self.TODAY)
        assert verdict == "Hold"
        assert days == 999

    def test_sos_maps_to_strong_buy(self) -> None:
        signals = [VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)]
        verdict, days = verdict_from_signals(signals, self.TODAY)
        assert verdict == "Strong Buy"
        assert days == 0

    def test_sow_maps_to_strong_sell(self) -> None:
        signals = [VsaSignal(date=self.TODAY, signal_name=SignalName.SOW, type=SignalType.BEARISH)]
        verdict, days = verdict_from_signals(signals, self.TODAY)
        assert verdict == "Strong Sell"

    def test_most_recent_signal_wins(self) -> None:
        older = VsaSignal(
            date=self.TODAY - timedelta(days=5),
            signal_name=SignalName.SOW,
            type=SignalType.BEARISH,
        )
        newer = VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)
        verdict, days = verdict_from_signals([older, newer], self.TODAY)
        assert verdict == "Strong Buy"
        assert days == 0
