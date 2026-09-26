"""Tests for the Wyckoff/VSA background phase analysis (roadmap #15a).

Each test builds a background the source text names — absorption after a
decline, high volume on up-bars near a top, quiet drift — and pins the phase it
must read as, plus what that phase does to a signal detected inside it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.analysis.phase import (
    Phase,
    add_phase_columns,
    classify_bars,
    classify_row,
    stance,
    strength_multiplier,
)
from app.models import StooqDailyQuote

_START = date(2026, 1, 2)


def _bar(
    d: date,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _flat(n: int, price: float = 100.0, vol: int = 50_000) -> list[StooqDailyQuote]:
    """``n`` featureless bars — no direction, no volume story."""
    return [
        _bar(_START + timedelta(days=i), price, price + 1, price - 1, price, vol)
        for i in range(n)
    ]


def _decline(
    n: int, start_price: float = 100.0, step: float = 1.0, vol: int = 50_000
) -> list[StooqDailyQuote]:
    """A steady fall on ordinary volume."""
    bars: list[StooqDailyQuote] = []
    price = start_price
    for i in range(n):
        nxt = price - step
        bars.append(_bar(_START + timedelta(days=i), price, price + 0.5, nxt - 0.5, nxt, vol))
        price = nxt
    return bars


def _advance(
    n: int, start_price: float = 100.0, step: float = 1.0, vol: int = 50_000
) -> list[StooqDailyQuote]:
    """A steady rise on ordinary volume."""
    bars: list[StooqDailyQuote] = []
    price = start_price
    for i in range(n):
        nxt = price + step
        bars.append(_bar(_START + timedelta(days=i), price, nxt + 0.5, price - 0.5, nxt, vol))
        price = nxt
    return bars


def _redate(bars: list[StooqDailyQuote]) -> list[StooqDailyQuote]:
    """Re-stamp a concatenated series with consecutive dates."""
    return [
        StooqDailyQuote(
            date=_START + timedelta(days=i),
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for i, b in enumerate(bars)
    ]


class TestInsufficientHistory:
    def test_too_few_bars_is_neutral(self) -> None:
        """A handful of bars cannot show a campaign — abstain, never guess."""
        assert classify_bars(_flat(5)) is Phase.NEUTRAL

    def test_empty_series_is_neutral(self) -> None:
        assert classify_bars([]) is Phase.NEUTRAL

    def test_featureless_history_is_neutral(self) -> None:
        """Enough bars, but no story in them: still neutral, not a phase."""
        assert classify_bars(_flat(40)) is Phase.NEUTRAL


class TestAccumulation:
    def test_absorption_after_a_decline_reads_as_accumulation(self) -> None:
        """Master the Markets p.42: a high-volume DOWN-bar closing on its highs
        is demand overcoming supply. Several of them, low in the range after a
        bear move, is the accumulation the book describes (p.20)."""
        bars = _decline(20, start_price=120.0, step=1.0)
        # A sideways range at the low, punctuated by high-volume DOWN-bars that
        # close in the upper part of their own range: selling met by buying.
        price = 100.0
        absorb: list[StooqDailyQuote] = []
        for i in range(12):
            heavy = i % 3 == 0
            if heavy:
                close = price - 0.5  # a down-bar ...
                low, high = price - 3.0, price + 0.2
                # ... that nonetheless closes near its high: close_pos ≈ 0.78
                absorb.append(_bar(_START, price, high, low, close, 200_000))
            else:
                close = price + 0.2
                absorb.append(_bar(_START, price, price + 0.6, price - 0.6, close, 25_000))
            price = close
        assert classify_bars(_redate(bars + absorb)) is Phase.ACCUMULATION

    def test_a_decline_without_absorption_is_not_accumulation(self) -> None:
        """Falling on supply with nothing absorbing it is mark-down, not the
        start of a campaign — the distinction the whole module exists for."""
        assert classify_bars(_decline(40, start_price=140.0)) is not Phase.ACCUMULATION


class TestDistribution:
    def test_high_volume_up_bars_near_a_top_read_as_distribution(self) -> None:
        """The book's own definition (the shake-out chart, p.~90): a
        distribution phase is "normally indicated by high volume on up-bars
        near a market top"."""
        bars = _advance(20, start_price=100.0, step=1.0)
        price = 120.0
        top: list[StooqDailyQuote] = []
        for i in range(12):
            heavy = i % 3 == 0
            if heavy:
                close = price + 0.5  # an up-bar ...
                low, high = price - 0.2, price + 3.0
                # ... on heavy volume that closes POORLY: close_pos ≈ 0.22.
                # Supply met the buying — the book's market-top signature.
                top.append(_bar(_START, price, high, low, close, 220_000))
            else:
                close = price - 0.2
                top.append(_bar(_START, price, price + 0.6, price - 0.6, close, 25_000))
            price = close
        assert classify_bars(_redate(bars + top)) is Phase.DISTRIBUTION

    def test_a_clean_advance_is_not_distribution(self) -> None:
        """A rise with volume behind it is mark-up. Calling every advance
        'distribution' would reintroduce the bug this module fixes."""
        assert classify_bars(_advance(40, start_price=80.0)) is not Phase.DISTRIBUTION


class TestStanceTable:
    def test_bullish_signal_is_contradicted_by_distribution(self) -> None:
        assert stance(Phase.DISTRIBUTION, bullish=True) == "contradicts"

    def test_bearish_signal_is_contradicted_by_accumulation(self) -> None:
        assert stance(Phase.ACCUMULATION, bullish=False) == "contradicts"

    def test_a_contradicted_signal_is_discounted_but_never_erased(self) -> None:
        """A contradicting background must not delete the pattern: it stays on
        the chart and loses weight in the rating. Measured on GPW history,
        deleting them outright also removed the better-performing half."""
        for phase, bullish in ((Phase.DISTRIBUTION, True), (Phase.ACCUMULATION, False)):
            mult = strength_multiplier(phase, bullish=bullish)
            assert 0.0 < mult < strength_multiplier(Phase.NEUTRAL, bullish=bullish)

    def test_accumulation_confirms_a_bullish_signal_at_full_strength(self) -> None:
        """"Testing is a good sign of strength (as long as you have strength in
        the background)" (p.34)."""
        assert stance(Phase.ACCUMULATION, bullish=True) == "confirms"
        assert strength_multiplier(Phase.ACCUMULATION, bullish=True) == 1.0

    def test_distribution_confirms_a_bearish_signal_at_full_strength(self) -> None:
        """Up-thrusts are "usually seen after a rise ... and there is weakness
        in the background" — the case a price-only gate got backwards."""
        assert stance(Phase.DISTRIBUTION, bullish=False) == "confirms"
        assert strength_multiplier(Phase.DISTRIBUTION, bullish=False) == 1.0

    def test_neutral_allows_at_reduced_weight(self) -> None:
        """An unconfirmed pattern is not worthless, just not the strong version
        ("taken in isolation ... mean little"), so it keeps most of its weight."""
        for bullish in (True, False):
            assert stance(Phase.NEUTRAL, bullish=bullish) == "allows"
            mult = strength_multiplier(Phase.NEUTRAL, bullish=bullish)
            assert 0.0 < mult < 1.0

    def test_every_phase_has_a_stance_both_ways(self) -> None:
        for ph in Phase:
            for bullish in (True, False):
                assert stance(ph, bullish=bullish) in {"confirms", "allows", "contradicts"}
                assert 0.0 < strength_multiplier(ph, bullish=bullish) <= 1.0


class TestNoLookAhead:
    def test_a_bar_never_sees_itself_or_the_future(self) -> None:
        """The phase on bar i must be identical whether or not the bars after i
        exist — the property that makes the back-test honest."""
        import pandas as pd

        full = _redate(_decline(20, start_price=120.0) + _advance(20, start_price=100.0))

        def _frame(bars: list[StooqDailyQuote]) -> pd.DataFrame:
            df = pd.DataFrame(
                [
                    {
                        "high": float(b.high),
                        "low": float(b.low),
                        "close": float(b.close),
                        "volume": float(b.volume),
                        "date": b.date,
                    }
                    for b in bars
                ]
            )
            df["spread"] = df["high"] - df["low"]
            df["close_pos"] = ((df["close"] - df["low"]) / df["spread"]).where(df["spread"] > 0)
            add_phase_columns(df)
            return df

        whole = _frame(full)
        for cut in range(25, len(full) + 1):
            truncated = _frame(full[:cut])
            assert classify_row(truncated.iloc[-1]) == classify_row(whole.iloc[cut - 1]), (
                f"phase at bar {cut - 1} changed when later bars were removed"
            )


class TestFrozenSeries:
    def test_zero_spread_and_zero_volume_bars_do_not_crash_or_invent_a_phase(self) -> None:
        """A suspended listing (frozen price, no volume) must read neutral
        rather than producing a phase out of division by zero."""
        frozen = [
            _bar(_START + timedelta(days=i), 100.0, 100.0, 100.0, 100.0, 0)
            for i in range(40)
        ]
        assert classify_bars(frozen) is Phase.NEUTRAL


class TestEngineIntegration:
    """How the gate plugs into the VSA engine (app/analysis/vsa.py)."""

    def test_it_is_off_by_default(self) -> None:
        """Measured on GPW history it did not reliably improve the rating, so
        it ships off. See agent/VSA-PHASE-ANALYSIS.md for the numbers."""
        from app.analysis.vsa import VsaConfig

        assert VsaConfig.default().use_phase_analysis is False

    def test_the_default_config_still_hashes_as_default(self) -> None:
        """An empty cache suffix is what keeps every existing cache key — and
        the nightly pre-warmed ranking — working unchanged."""
        from app.analysis.vsa import VsaConfig

        assert VsaConfig.default().is_default() is True
        assert VsaConfig.default().cache_suffix() == ""

    def test_turning_it_on_changes_the_cache_key(self) -> None:
        """Otherwise a phase-weighted scan could be served from — or overwrite
        — the unweighted ranking's cache entry."""
        from app.analysis.vsa import VsaConfig

        on = VsaConfig(use_phase_analysis=True)
        assert on.is_default() is False
        assert on.cache_suffix() != ""

    def test_it_only_reweights_and_never_removes_a_signal(self) -> None:
        """The gate must not change WHICH bars are signals — only how much
        each one counts — so a chart cannot lose markers by enabling it."""
        from app.analysis.vsa import VsaConfig, detect_signals

        bars = _redate(
            _decline(40, start_price=140.0, step=1.2)
            + _advance(40, start_price=92.0, step=1.2)
        )
        off = detect_signals(bars, VsaConfig(use_phase_analysis=False))
        on = detect_signals(bars, VsaConfig(use_phase_analysis=True))
        assert [(s.date, s.signal_name) for s in off] == [
            (s.date, s.signal_name) for s in on
        ]
        for a, b in zip(off, on, strict=True):
            assert b.strength <= a.strength
