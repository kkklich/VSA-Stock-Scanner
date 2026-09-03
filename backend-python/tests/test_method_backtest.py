"""Tests for the generic GPW back-test gate (method_backtest_service).

Covers the pure forward-return judging, the pass/fail grading thresholds, and
the end-to-end aggregation over a stub method + fake price feed.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.analysis.methods.base import (
    MethodResult,
    MethodSignal,
    TradingMethod,
)
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.method_backtest_service import (
    _MIN_SAMPLES,
    _grade,
    compute_method_backtest,
    judge_stock,
)


def _quote(d: date, close: float, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(closes: list[float], end: date | None = None) -> list[StooqDailyQuote]:
    if end is None:
        end = date.today()
    n = len(closes)
    return [_quote(end - timedelta(days=n - 1 - i), closes[i]) for i in range(n)]


# ── judge_stock (pure forward-return judging) ─────────────────────────────────


class TestJudgeStock:
    def test_mechanics_and_recency_cutoff(self) -> None:
        bars = _series([100.0 + (i % 5) for i in range(60)])
        # Two judgeable firings (idx 10, 20) + one too recent to judge (idx 55,
        # since 55 + 10 >= 60 has no forward bar).
        sig_dates = [bars[10].date, bars[20].date, bars[55].date]
        rows = judge_stock(bars, sig_dates, forward_sessions=10, bullish=True)
        assert rows is not None
        assert len(rows) == 2
        for pct, base, excess, success in rows:
            # excess and success are internally consistent with pct vs baseline.
            assert abs(excess - (pct - base)) < 1e-9
            assert success == (pct > base)

    def test_bearish_flips_the_success_test(self) -> None:
        # Flat series with a single bump 10 bars after the firing: the firing's
        # forward return is clearly positive (+10%) while the baseline is ~0, so
        # the long side wins and the short side loses on the same bar.
        closes = [100.0] * 60
        closes[20] = 110.0
        bars = _series(closes)
        rows_bull = judge_stock(bars, [bars[10].date], 10, bullish=True)
        rows_bear = judge_stock(bars, [bars[10].date], 10, bullish=False)
        assert rows_bull and rows_bear
        assert rows_bull[0][3] is True  # +10% beats the ~0 baseline the long way
        assert rows_bear[0][3] is False

    def test_none_when_too_short_for_forward_window(self) -> None:
        bars = _series([100.0] * 8)
        assert judge_stock(bars, [bars[0].date], forward_sessions=10, bullish=True) is None


# ── _grade (the gate thresholds) ──────────────────────────────────────────────


class TestGrade:
    def test_insufficient_below_min_samples(self) -> None:
        passes, grade, _ = _grade(_MIN_SAMPLES - 1, 80.0, 5.0, 2.0)
        assert passes is None
        assert grade == "insufficient"

    def test_strong_when_clearly_beats_baseline(self) -> None:
        passes, grade, _ = _grade(120, 60.0, 1.5, 1.5)
        assert passes is True
        assert grade == "strong"

    def test_pass_when_marginally_positive(self) -> None:
        passes, grade, _ = _grade(120, 52.0, 0.3, 1.0)
        assert passes is True
        assert grade == "pass"

    def test_fail_when_no_edge(self) -> None:
        passes, grade, _ = _grade(120, 40.0, -0.5, 0.8)
        assert passes is False
        assert grade == "fail"


# ── compute_method_backtest (end-to-end aggregation) ──────────────────────────


class _Client:
    def __init__(self, by: dict[str, list[StooqDailyQuote]]) -> None:
        self._by = by

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        rows = self._by.get(ticker, [])
        if from_date is not None:
            rows = [q for q in rows if q.date >= from_date]
        return rows


class _EveryThirdBar(TradingMethod):
    """Stub method that fires (bullishly) on every third bar — enough firings to
    exercise the aggregation and clear the minimum-sample gate."""

    id = "stub"
    order = 999
    name = "Stub"
    description = "test stub"
    source = "test"

    def evaluate(self, bars, config=None) -> MethodResult:
        return MethodResult.unavailable()

    def signals(self, bars, config=None) -> list[MethodSignal]:
        return [
            MethodSignal(date=b.date, label="x", type="Bullish")
            for i, b in enumerate(bars)
            if i % 3 == 0
        ]


class TestComputeBacktest:
    def test_plumbing_and_excess_frame(self) -> None:
        company = GpwCompany(ticker="t", name="T", sector="X", market_cap=None)
        client = _Client({"t": _series([100.0 + (i % 7) for i in range(400)])})
        stats = asyncio.run(
            compute_method_backtest(
                method=_EveryThirdBar(),
                companies=[company],
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )
        assert stats.scanned_count == 1
        assert stats.signal_count > 0
        # ~130 firings judgeable → well past the minimum-sample gate.
        assert stats.evaluated_count >= _MIN_SAMPLES
        assert stats.grade in {"pass", "fail", "strong"}
        assert stats.win_rate_pct is not None
        assert stats.passes is not None
        # Edge == mean firing return − mean baseline (within rounding).
        assert (
            abs(
                stats.avg_excess_return_pct
                - (stats.avg_forward_return_pct - stats.baseline_return_pct)
            )
            < 0.05
        )

    def test_no_signals_is_insufficient(self) -> None:
        # A method that never fires → nothing to judge → insufficient, not a pass.
        class _NeverFires(_EveryThirdBar):
            def signals(self, bars, config=None):
                return []

        company = GpwCompany(ticker="t", name="T", sector="X", market_cap=None)
        client = _Client({"t": _series([100.0] * 200)})
        stats = asyncio.run(
            compute_method_backtest(
                method=_NeverFires(),
                companies=[company],
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )
        assert stats.scanned_count == 1
        assert stats.evaluated_count == 0
        assert stats.passes is None
        assert stats.grade == "insufficient"
