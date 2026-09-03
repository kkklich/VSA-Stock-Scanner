"""Tests for the VSA signal detection and rating engine."""

from __future__ import annotations

import math  # used for atanh in half-life decay test
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analysis.vsa import (
    DEFAULT_SIGNAL_PARAMS,
    SignalName,
    SignalParams,
    SignalType,
    VsaConfig,
    VsaSignal,
    compute_rating,
    config_from_settings,
    detect_signals,
    verdict_from_signals,
)
from app.models import StooqDailyQuote, VsaSettings, VsaSignalSettings

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


_START = date(2026, 1, 2)
# Gate turned off, for A/B comparisons that isolate the trend-context effect.
GATE_OFF = VsaConfig(use_trend_context=False)


def _sloped_bars(n: int, first: float, step: float, vol: int = 50_000) -> list[StooqDailyQuote]:
    """``n`` bars whose close moves ``step`` per session from ``first`` (spread 2)."""
    out: list[StooqDailyQuote] = []
    for i in range(n):
        p = first + i * step
        out.append(_bar((_START + timedelta(days=i)).isoformat(), p, p + 1, p - 1, p, vol))
    return out


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

    def test_spring_detected_on_low_volume_no_supply_variant(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # Low-volume spring: barely breaks support (99) on light volume and
        # closes back above it near the high — the "no supply" spring, which
        # per the Wyckoff literature is the highest-probability variant.
        bars.append(
            _bar("2026-01-27", open_=99.5, high=100.0, low=98.6, close=99.9, volume=20_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SPRING in names

    def test_successful_test_detected_on_low_volume_dip(self) -> None:
        # Older, deeper support zone at ~97 so the dip below the *previous*
        # bar's low does not also break the 20-day low (that would be a Spring).
        start = date(2026, 1, 2)
        bars: list[StooqDailyQuote] = []
        for i in range(10):
            d = (start + timedelta(days=i)).isoformat()
            bars.append(_bar(d, 97.0, 98.0, 96.0, 97.0, 50_000))
        for i in range(10, 25):
            d = (start + timedelta(days=i)).isoformat()
            bars.append(_bar(d, 100.0, 101.0, 99.0, 100.0, 50_000))

        # Test bar: dips below the previous bar's low (99) into the old selling
        # area near the bottom of the recent range (low 97.0, well inside the
        # lower quartile of the 96–101 lookback range), regains to close near
        # its high, on volume well below both of the previous two bars — a
        # Successful Test ("no supply"). The low stays above the 20-day low
        # (96), so this is not a Spring.
        bars.append(
            _bar("2026-01-27", open_=100.0, high=100.5, low=97.0, close=100.4, volume=18_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SUCCESSFUL_TEST in names

    def test_successful_test_requires_dip_into_lower_range(self) -> None:
        # Same setup, but the dip only reaches 98.7 — below the previous bar's
        # low, yet still in the upper part of the 96–101 range, far from the
        # old selling area. Master the Markets p.35 requires the dip to enter
        # "an area of previous selling (previous high volume level)", so a
        # shallow dip high in the range must NOT qualify as a Test.
        start = date(2026, 1, 2)
        bars: list[StooqDailyQuote] = []
        for i in range(10):
            d = (start + timedelta(days=i)).isoformat()
            bars.append(_bar(d, 97.0, 98.0, 96.0, 97.0, 50_000))
        for i in range(10, 25):
            d = (start + timedelta(days=i)).isoformat()
            bars.append(_bar(d, 100.0, 101.0, 99.0, 100.0, 50_000))
        bars.append(
            _bar("2026-01-27", open_=100.0, high=100.5, low=98.7, close=100.4, volume=18_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SUCCESSFUL_TEST not in names

    def test_sos_not_detected_on_excessive_volume(self) -> None:
        bars = _normal_bars(n=25)

        # Same wide up-bar shape as the SOS fixture, but volume is 5× the
        # average (> _EXCESSIVE_VOL_MULT = 4×). Master the Markets: volume on
        # an up-bar "should not be excessive, as this is indicative of supply
        # in the background" — a potential buying climax, not an SOS.
        bars.append(
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=250_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SOS not in names

    def test_spring_not_detected_on_excessive_volume(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # The known-good high-volume Spring shape, but with climactic volume
        # (5× average > the 4× cap) — the same "not excessive" rule applies.
        bars.append(
            _bar("2026-01-27", open_=100.0, high=101.5, low=98.5, close=101.2, volume=250_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SPRING not in names

    def test_low_volume_spring_requires_shallow_penetration(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # Low volume, but the dip goes 1.5 below support (avg spread is 2.0,
        # so the shallow-penetration cap is 0.5 × 2.0 = 1.0). The canonical
        # low-volume Wyckoff spring penetrates support only shallowly — this
        # deep break on no volume is not a Spring.
        bars.append(
            _bar("2026-01-27", open_=99.5, high=100.0, low=97.5, close=99.9, volume=20_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.SPRING not in names
        # ...and the rejected Spring must not fall through to any other
        # bullish reading either — the Successful Test shares the same
        # shallow-penetration limit, so a deep low-volume break below
        # support yields no bullish signal at all.
        assert not any(s.type == SignalType.BULLISH for s in signals)

    def test_deep_low_volume_break_is_not_read_as_bullish(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # Collapses 5 points below the whole 20-day range (support at 99) on
        # low volume, then closes back inside it. Far too deep for a Spring
        # AND for a Successful Test (both share _SHALLOW_PENETRATION_SPREADS):
        # a collapsing low-volume breakdown is not a bullish test of supply.
        bars.append(
            _bar("2026-01-27", open_=99.5, high=100.0, low=94.0, close=99.8, volume=20_000)
        )

        signals = detect_signals(bars)
        assert not any(s.type == SignalType.BULLISH for s in signals)

    def test_climax_cap_boundary_is_inclusive(self) -> None:
        # Volume at exactly _EXCESSIVE_VOL_MULT × average (4 × 50k) is the
        # last value that still qualifies as an SOS (the cap is <=, not <);
        # one share more crosses into climax territory.
        bars = _normal_bars(n=25)
        at_cap = bars + [
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=200_000)
        ]
        names = [s.signal_name for s in detect_signals(at_cap)]
        assert SignalName.SOS in names

        above_cap = bars + [
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=200_001)
        ]
        names = [s.signal_name for s in detect_signals(above_cap)]
        assert SignalName.SOS not in names

    def test_climax_cap_adapts_to_high_vol_mult(self) -> None:
        # With the SOS volume slider raised to 5.0× a fixed 4.0× cap would
        # make the rule unsatisfiable (vol > 5×avg and vol <= 4×avg never
        # holds) and SOS would silently disappear. The cap adapts to
        # 1.5 × vol_mult, so a 6×-average-volume SOS bar still fires.
        bars = _normal_bars(n=25)
        bars.append(
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=300_000)
        )
        params = dict(DEFAULT_SIGNAL_PARAMS)
        params[SignalName.SOS] = SignalParams(spread_mult=1.5, vol_mult=5.0, close_pos=0.65)
        signals = detect_signals(bars, VsaConfig(params=params))
        assert SignalName.SOS in {s.signal_name for s in signals}

    def test_sow_not_detected_on_excessive_volume(self) -> None:
        # Mirror of the SOS cap: a 6×-average-volume wide down bar closing on
        # its low is potential "stopping volume" (climactic selling being
        # absorbed by professional money), not a clean SOW — while the same
        # bar on merely high volume still is one.
        bars = _normal_bars(n=25)
        climactic = bars + [
            _bar("2026-01-27", open_=100.0, high=100.5, low=88.0, close=89.5, volume=300_000)
        ]
        names = [s.signal_name for s in detect_signals(climactic)]
        assert SignalName.SOW not in names

        normal_high = bars + [
            _bar("2026-01-27", open_=100.0, high=100.5, low=88.0, close=89.5, volume=130_000)
        ]
        names = [s.signal_name for s in detect_signals(normal_high)]
        assert SignalName.SOW in names

    def test_zero_spread_bar_emits_no_signal(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0)

        # A frozen bar (high == low == close) above the previous close on low
        # volume. close_pos is undefined (NaN) on a zero-spread bar, so no
        # rule — in particular No Demand — may fire.
        bars.append(
            _bar("2026-01-27", open_=100.5, high=100.5, low=100.5, close=100.5, volume=15_000)
        )

        signals = detect_signals(bars)
        assert signals == []

    def test_frozen_history_then_wide_bar_emits_no_signal(self) -> None:
        # 30 zero-spread bars (e.g. a trading suspension): the average spread
        # is 0, so a wide resumption bar must not trivially satisfy the
        # wide-spread conditions and fire a false Spring/Upthrust.
        start = date(2026, 1, 2)
        bars = [
            _bar((start + timedelta(days=i)).isoformat(), 100.0, 100.0, 100.0, 100.0, 50_000)
            for i in range(30)
        ]
        bars.append(
            _bar("2026-02-01", open_=100.0, high=103.0, low=97.0, close=102.5, volume=60_000)
        )

        signals = detect_signals(bars)
        assert signals == []

    def test_no_demand_on_narrow_up_bar_low_volume(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0, base_vol=50_000)

        # No Demand: up bar (close above previous close), narrow spread, low
        # volume (below both of the previous two bars), close mid-or-low.
        # Keep the low above the previous bar's low to avoid the Successful
        # Test rule (higher priority), which triggers on a dip below it.
        bars.append(
            _bar("2026-01-27", open_=103.0, high=103.3, low=102.8, close=103.1, volume=15_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.NO_DEMAND in names

    def test_no_demand_requires_close_above_previous_close(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0, base_vol=50_000)

        # Narrow, quiet bar with close above its *open* (99.6 > 99.3) but
        # below the previous bar's *close* (100). VSA defines an up-bar
        # against the previous close, so this is not a No Demand bar.
        bars.append(
            _bar("2026-01-27", open_=99.3, high=99.9, low=99.3, close=99.6, volume=15_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.NO_DEMAND not in names

    def test_no_demand_requires_volume_below_previous_two_bars(self) -> None:
        bars = _normal_bars(n=25, base_price=100.0, base_vol=50_000)
        # Make the immediately preceding bar even quieter than the candidate.
        bars[24] = _bar("2026-01-26", open_=100.0, high=101.0, low=99.0, close=100.0, volume=10_000)

        # Candidate is narrow, quiet vs the 20-bar average (12k < 0.7 × ~48k),
        # but NOT below both of the previous two bars (12k > 10k) — per the
        # TradeGuider criterion this is not a No Demand bar.
        bars.append(
            _bar("2026-01-27", open_=103.0, high=103.3, low=102.8, close=103.1, volume=12_000)
        )

        signals = detect_signals(bars)
        names = [s.signal_name for s in signals]
        assert SignalName.NO_DEMAND not in names

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
        # Recover a value proportional to the net score via atanh (inverse of
        # the final tanh; the /2 scaling inside cancels out in the ratio).
        # This tests the decay in score-space, where the relationship is exact.
        old_score = math.atanh((old_rating - 50) / 50)
        recent_score = math.atanh((recent_rating - 50) / 50)
        # recent_score should be twice old_score because the old signal's weight = 0.5.
        assert abs(recent_score / old_score - 2.0) < 0.05


# ── verdict_from_signals ──────────────────────────────────────────────────────


class TestVerdictFromSignals:
    """The verdict comes from the same decayed net score as the rating."""

    TODAY = date(2026, 6, 30)

    def test_no_signals_returns_hold(self) -> None:
        verdict, days = verdict_from_signals([], self.TODAY)
        assert verdict == "Hold"
        assert days == 999

    def test_single_fresh_sos_maps_to_buy(self) -> None:
        # One fresh SOS (strength 1.0) → net 1.0: a Buy lean, not yet a
        # Strong Buy — a single signal needs confirmation in VSA.
        signals = [VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)]
        verdict, days = verdict_from_signals(signals, self.TODAY)
        assert verdict == "Buy"
        assert days == 0

    def test_single_fresh_sow_maps_to_sell(self) -> None:
        signals = [VsaSignal(date=self.TODAY, signal_name=SignalName.SOW, type=SignalType.BEARISH)]
        verdict, days = verdict_from_signals(signals, self.TODAY)
        assert verdict == "Sell"

    def test_confirming_cluster_maps_to_strong_buy(self) -> None:
        signals = [
            VsaSignal(
                date=self.TODAY - timedelta(days=i),
                signal_name=SignalName.SOS,
                type=SignalType.BULLISH,
            )
            for i in range(3)
        ]
        verdict, days = verdict_from_signals(signals, self.TODAY)
        assert verdict == "Strong Buy"
        assert days == 0

    def test_opposing_recent_signals_net_out_to_hold(self) -> None:
        # A fresh SOS against a 5-day-old SOW nearly cancel: the verdict must
        # reflect the balance of evidence, not just the most recent signal.
        older = VsaSignal(
            date=self.TODAY - timedelta(days=5),
            signal_name=SignalName.SOW,
            type=SignalType.BEARISH,
        )
        newer = VsaSignal(date=self.TODAY, signal_name=SignalName.SOS, type=SignalType.BULLISH)
        verdict, days = verdict_from_signals([older, newer], self.TODAY)
        assert verdict == "Hold"
        assert days == 0

    def test_custom_half_life_keeps_verdict_in_sync_with_rating(self) -> None:
        # Two strong bullish signals 30 days old: at the default 30-day
        # half-life they have decayed to net 1.0 → "Buy"; a caller computing
        # the rating with a 90-day half-life must be able to pass the same
        # value here (net ≈ 1.59 → "Strong Buy"), or rating and verdict
        # would silently drift apart again.
        signals = [
            VsaSignal(
                date=self.TODAY - timedelta(days=30),
                signal_name=SignalName.SOS,
                type=SignalType.BULLISH,
            )
            for _ in range(2)
        ]
        assert verdict_from_signals(signals, self.TODAY)[0] == "Buy"
        assert (
            verdict_from_signals(signals, self.TODAY, half_life_days=90)[0]
            == "Strong Buy"
        )

    def test_verdict_consistent_with_rating(self) -> None:
        # The audit's contradiction case: 5 recent SOS + 1 No Demand
        # yesterday used to yield rating ≈ 97 (deep green) with a "Sell"
        # badge. The verdict must now agree with the bullish rating.
        signals = [
            VsaSignal(
                date=self.TODAY - timedelta(days=2 + i),
                signal_name=SignalName.SOS,
                type=SignalType.BULLISH,
            )
            for i in range(5)
        ]
        signals.append(
            VsaSignal(
                date=self.TODAY - timedelta(days=1),
                signal_name=SignalName.NO_DEMAND,
                type=SignalType.BEARISH,
                strength=0.6,
            )
        )
        rating = compute_rating(signals, self.TODAY)
        verdict, _ = verdict_from_signals(signals, self.TODAY)
        assert rating > 70
        assert verdict == "Strong Buy"


# ── VsaConfig: configurable detection ────────────────────────────────────────


class TestVsaConfig:
    """The Scanner page settings must actually change what the engine detects."""

    def _sos_bars(self) -> list[StooqDailyQuote]:
        """25 bland bars + the known-good SOS bar from TestDetectSignals."""
        bars = _normal_bars(n=25)
        bars.append(
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=120_000)
        )
        return bars

    def test_default_config_matches_no_config(self) -> None:
        bars = self._sos_bars()
        assert detect_signals(bars) == detect_signals(bars, VsaConfig.default())

    def test_disabling_a_signal_suppresses_it(self) -> None:
        bars = self._sos_bars()
        params = dict(DEFAULT_SIGNAL_PARAMS)
        params[SignalName.SOS] = SignalParams(enabled=False)
        signals = detect_signals(bars, VsaConfig(params=params))
        assert SignalName.SOS not in {s.signal_name for s in signals}

    def test_all_signals_disabled_returns_empty(self) -> None:
        bars = self._sos_bars()
        params = {name: SignalParams(enabled=False) for name in SignalName}
        assert detect_signals(bars, VsaConfig(params=params)) == []

    def test_stricter_volume_threshold_suppresses_sos(self) -> None:
        bars = self._sos_bars()
        # The SOS bar has volume 120k vs. 50k average (2.4×). Requiring 3×
        # average volume must make the same bar fail the SOS rule.
        params = dict(DEFAULT_SIGNAL_PARAMS)
        params[SignalName.SOS] = SignalParams(spread_mult=1.5, vol_mult=3.0, close_pos=0.65)
        signals = detect_signals(bars, VsaConfig(params=params))
        assert SignalName.SOS not in {s.signal_name for s in signals}

    def test_looser_volume_threshold_keeps_sos(self) -> None:
        bars = self._sos_bars()
        params = dict(DEFAULT_SIGNAL_PARAMS)
        params[SignalName.SOS] = SignalParams(spread_mult=1.5, vol_mult=1.1, close_pos=0.65)
        signals = detect_signals(bars, VsaConfig(params=params))
        assert SignalName.SOS in {s.signal_name for s in signals}

    def test_custom_lookback_is_respected(self) -> None:
        # With lookback 40 there is not enough history (26 bars) for SOS
        # context, so nothing should fire; lookback 10 still detects it.
        bars = self._sos_bars()
        params = dict(DEFAULT_SIGNAL_PARAMS)
        params[SignalName.SOS] = SignalParams(
            spread_mult=1.5, vol_mult=1.5, close_pos=0.65, lookback=40
        )
        long_lb = detect_signals(bars, VsaConfig(params=params))
        assert SignalName.SOS not in {s.signal_name for s in long_lb}

        params[SignalName.SOS] = SignalParams(
            spread_mult=1.5, vol_mult=1.5, close_pos=0.65, lookback=10
        )
        short_lb = detect_signals(bars, VsaConfig(params=params))
        assert SignalName.SOS in {s.signal_name for s in short_lb}

    def test_cache_suffix_empty_for_default(self) -> None:
        assert VsaConfig.default().cache_suffix() == ""

    def test_cache_suffix_stable_and_distinct(self) -> None:
        params = dict(DEFAULT_SIGNAL_PARAMS)
        params[SignalName.SOS] = SignalParams(vol_mult=2.0)
        a = VsaConfig(params=dict(params))
        b = VsaConfig(params=dict(params))
        assert a.cache_suffix() == b.cache_suffix() != ""

        params[SignalName.SOS] = SignalParams(vol_mult=2.5)
        c = VsaConfig(params=dict(params))
        assert c.cache_suffix() != a.cache_suffix()


# ── config_from_settings: API payload → engine config ────────────────────────


class TestConfigFromSettings:
    def test_none_yields_default(self) -> None:
        assert config_from_settings(None).is_default()

    def test_partial_payload_overrides_only_named_signal(self) -> None:
        payload = VsaSettings(sos=VsaSignalSettings(volMult=2.0))
        cfg = config_from_settings(payload)
        assert cfg.for_signal(SignalName.SOS).vol_mult == 2.0
        # Untouched fields fall back to the SOS defaults.
        assert cfg.for_signal(SignalName.SOS).spread_mult == 1.5
        # Other signals keep their full defaults.
        assert cfg.for_signal(SignalName.SPRING) == DEFAULT_SIGNAL_PARAMS[SignalName.SPRING]

    def test_close_pos_percent_converted_to_fraction(self) -> None:
        payload = VsaSettings(spring=VsaSignalSettings(closePos=75))
        cfg = config_from_settings(payload)
        assert cfg.for_signal(SignalName.SPRING).close_pos == pytest.approx(0.75)

    def test_disabled_flag_maps_through(self) -> None:
        payload = VsaSettings(nodemand=VsaSignalSettings(enabled=False))
        cfg = config_from_settings(payload)
        assert cfg.for_signal(SignalName.NO_DEMAND).enabled is False


# ── Trend-context / background gate (2a, 2b, 2c) ──────────────────────────────


class TestTrendContextConfig:
    """The ``use_trend_context`` flag defaults on and hashes as the default."""

    def test_default_config_has_trend_context_on(self) -> None:
        assert VsaConfig.default().use_trend_context is True

    def test_default_still_hashes_as_default(self) -> None:
        # A defaulted config (gate on) must keep the empty cache suffix so the
        # nightly pre-warmed ranking keys are unchanged.
        assert VsaConfig.default().is_default() is True
        assert VsaConfig.default().cache_suffix() == ""

    def test_disabling_the_gate_is_non_default(self) -> None:
        cfg = VsaConfig(use_trend_context=False)
        assert cfg.is_default() is False
        assert cfg.cache_suffix() != ""


class TestTrendContextGate:
    """Signals are read against their background (Master the Markets)."""

    def test_bullish_signal_suppressed_in_bearish_background(self) -> None:
        # A Spring-shaped bar (dips below recent support, recovers to close near
        # its high on high volume) inside a clear downtrend. With the gate on it
        # is suppressed (a break in a downtrend is a breakdown, not a spring);
        # with the gate off the old behaviour fires the Spring.
        bars = _sloped_bars(35, first=140.0, step=-1.0)
        recent_low = min(float(b.low) for b in bars[-20:])
        spring = _bar(
            (_START + timedelta(days=35)).isoformat(),
            recent_low, recent_low + 3.0, recent_low - 1.5, recent_low + 2.7, 120_000,
        )
        seq = bars + [spring]
        assert SignalName.SPRING not in {s.signal_name for s in detect_signals(seq)}
        assert SignalName.SPRING in {s.signal_name for s in detect_signals(seq, GATE_OFF)}

    def test_bearish_signal_suppressed_in_bullish_background(self) -> None:
        # A No Demand bar (narrow, quiet up-bar) during a strong advance is an
        # unremarkable pause, not a warning — suppressed with the gate on.
        bars = _sloped_bars(35, first=70.0, step=1.0)
        lastc = 70.0 + 34 * 1.0
        nd = _bar(
            (_START + timedelta(days=35)).isoformat(),
            lastc + 0.4, lastc + 0.6, lastc + 0.1, lastc + 0.3, 12_000,
        )
        seq = bars + [nd]
        assert SignalName.NO_DEMAND not in {s.signal_name for s in detect_signals(seq)}
        assert SignalName.NO_DEMAND in {s.signal_name for s in detect_signals(seq, GATE_OFF)}

    def test_sos_requires_breaking_resistance(self) -> None:
        # An old tall bar sets prior resistance at 106. A wide, strong, high-
        # volume up-bar that closes at 103.5 (below 106) does NOT push through
        # supply, so it is no longer an SOS; the same shape closing at 107.5
        # (through resistance) still is.
        bars = _normal_bars(25, base_price=100.0, base_vol=50_000)
        bars[5] = _bar((_START + timedelta(days=5)).isoformat(), 100, 106, 99, 101, 60_000)
        below = bars + [
            _bar((_START + timedelta(days=25)).isoformat(), 100, 104, 100, 103.5, 120_000)
        ]
        through = bars + [
            _bar((_START + timedelta(days=25)).isoformat(), 100, 108, 100, 107.5, 120_000)
        ]
        assert SignalName.SOS not in {s.signal_name for s in detect_signals(below)}
        assert SignalName.SOS in {s.signal_name for s in detect_signals(through)}

    def test_excessive_volume_up_bar_in_new_high_ground_is_a_climax(self) -> None:
        # Ultra-high volume (6x average) on a wide, strong up-bar breaking to new
        # highs while the background is already extended (a steady advance) is a
        # BUYING CLIMAX — reclassified bearish (reusing the Upthrust structure).
        # With the gate off, the old engine simply silenced it (excessive-volume
        # cap) — no signal at all.
        bars = _sloped_bars(35, first=80.0, step=1.0)
        lastc = 80.0 + 34 * 1.0
        climax = _bar(
            (_START + timedelta(days=35)).isoformat(),
            lastc, lastc + 6, lastc - 0.5, lastc + 5.5, 50_000 * 6,
        )
        seq = bars + [climax]
        names_on = {s.signal_name for s in detect_signals(seq)}
        assert SignalName.UPTHRUST in names_on
        assert SignalName.SOS not in names_on
        # Confirm the reclassified signal is bearish.
        climax_sig = [s for s in detect_signals(seq) if s.date == climax.date]
        assert climax_sig and climax_sig[0].type == SignalType.BEARISH
        assert detect_signals(seq, GATE_OFF) == []

    def test_excessive_volume_breakout_out_of_a_range_stays_sos(self) -> None:
        # The same ultra-high volume breakout, but out of a flat base (the
        # background is NOT extended) — this is a range breakout on a volume
        # surge, so the climax cap is lifted and it remains a valid SOS. With the
        # gate off it is silenced by the fixed excessive-volume cap.
        bars = _normal_bars(35, base_price=100.0, base_vol=50_000)
        brk = _bar(
            (_START + timedelta(days=35)).isoformat(), 100, 108, 99.5, 107.5, 50_000 * 6
        )
        seq = bars + [brk]
        assert SignalName.SOS in {s.signal_name for s in detect_signals(seq)}
        assert detect_signals(seq, GATE_OFF) == []

    def test_short_history_leaves_signals_unchanged(self) -> None:
        # With fewer than the trend lookback of prior bars the background is
        # unknown, so the gate never suppresses — the classic SOS fixture still
        # fires exactly as before.
        bars = _normal_bars(25)
        bars.append(
            _bar("2026-01-27", open_=99.5, high=108.0, low=99.2, close=107.5, volume=120_000)
        )
        assert SignalName.SOS in {s.signal_name for s in detect_signals(bars)}
