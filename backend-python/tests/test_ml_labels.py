"""The AI layer's labels — L1's next-open return, L2 = the gate, L3 = the trade."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.ml.features import bars_frame
from app.ml.labels import (
    TradeCosts,
    forward_open_to_close,
    gate_baseline_pct,
    gate_forward_pct,
    triple_barrier,
)
from app.services.method_backtest_service import judge_stock
from tests.ml_synthetic import bar, random_walk_bars, weekdays

NO_COSTS = TradeCosts(commission_bps=0, slippage_bps=0)
# Entry 100, never near the stop (90) or the target (130): a time exit at 103.
SLOW_RISE = [(99, 99, 99, 99), (100, 102, 98, 101), (101, 103, 100, 102), (102, 104, 101, 103)]


def _frame(rows):
    """rows: (open, high, low, close) per weekday from 2022-01-03."""
    days = weekdays(date(2022, 1, 3), len(rows))
    return bars_frame([bar(d, o, h, lo, c) for d, (o, h, lo, c) in zip(days, rows, strict=True)])


class TestForwardOpenToClose:
    def test_enters_next_open_exits_close_n_later(self):
        df = _frame([(10, 10, 10, 10), (11, 12, 10, 11.5), (12, 13, 11, 12), (13, 14, 12, 13.2)])
        out = forward_open_to_close(df, 2)
        assert out["fwd_r"].iloc[0] == pytest.approx(12 / 11 - 1)  # open 11 → close 12
        assert out["fwd_r"].iloc[1] == pytest.approx(13.2 / 12 - 1)
        assert np.isnan(out["fwd_r"].iloc[2])  # not enough forward bars
        assert out["fwd_end"].iloc[0] == df["date"].iloc[2]

    def test_a_suspension_inside_the_window_is_not_judged(self):
        days = weekdays(date(2022, 1, 3), 3) + [date(2022, 2, 1), date(2022, 2, 2)]
        df = bars_frame([bar(d, 10, 11, 9, 10) for d in days])
        out = forward_open_to_close(df, 2)
        assert not out["fwd_valid"].iloc[1]  # window crosses the 27-day gap
        assert out["fwd_valid"].iloc[0]


class TestGateFrame:
    def test_equals_judge_stock_exactly(self):
        bars = random_walk_bars(300, seed=11)
        closes = np.array([float(b.close) for b in bars])
        signal_days = [bars[i].date for i in (40, 120, 250, 295)]
        for n in (10, 30):
            rows = judge_stock(bars, signal_days, n, bullish=True)
            pct = gate_forward_pct(closes, n)
            base = gate_baseline_pct(closes, n)
            index = {b.date: i for i, b in enumerate(bars)}
            mine = [
                (pct[index[d]], base, pct[index[d]] - base, pct[index[d]] > base)
                for d in signal_days
                if np.isfinite(pct[index[d]])
            ]
            assert len(mine) == len(rows)
            for (a, b, c, d), (w, x, y, z) in zip(mine, rows, strict=True):
                assert a == pytest.approx(w) and b == pytest.approx(x)
                assert c == pytest.approx(y) and d == z


class TestTripleBarrier:
    # Entry at the next open 100, ATR 5 → stop 90, target 130 (3R of 10).
    def test_target(self):
        df = _frame(
            [(99, 99, 99, 99), (100, 105, 99, 104), (104, 131, 103, 128), (128, 129, 127, 128)]
        )
        out = triple_barrier(df, 0, 3, 5.0, costs=NO_COSTS)
        assert out.exit_reason == "target" and out.r_net == pytest.approx(3.0)
        assert out.bars_held == 2

    def test_stop(self):
        df = _frame([(99, 99, 99, 99), (100, 101, 95, 96), (96, 97, 89, 90), (90, 91, 88, 89)])
        out = triple_barrier(df, 0, 3, 5.0, costs=NO_COSTS)
        assert out.exit_reason == "stop" and out.r_net == pytest.approx(-1.0)

    def test_stop_first_when_both_are_hit_on_one_bar(self):
        df = _frame([(99, 99, 99, 99), (100, 135, 85, 110), (110, 111, 109, 110)])
        out = triple_barrier(df, 0, 2, 5.0, costs=NO_COSTS)
        assert out.exit_reason == "stop"

    def test_a_gap_through_the_stop_fills_at_the_open(self):
        df = _frame([(99, 99, 99, 99), (100, 101, 98, 99), (80, 82, 79, 81), (81, 82, 80, 81)])
        out = triple_barrier(df, 0, 3, 5.0, costs=NO_COSTS)
        assert out.exit_reason == "stop" and out.exit == 80
        assert out.r_net == pytest.approx(-2.0)

    def test_time_exit_at_the_last_close(self):
        df = _frame(SLOW_RISE)
        out = triple_barrier(df, 0, 3, 5.0, costs=NO_COSTS)
        assert out.exit_reason == "time" and out.r_net == pytest.approx(0.3)

    def test_costs_are_charged_on_both_sides(self):
        df = _frame(SLOW_RISE)
        free = triple_barrier(df, 0, 3, 5.0, costs=NO_COSTS)
        paid = triple_barrier(df, 0, 3, 5.0)  # 0.25% a side
        assert paid.r_net == pytest.approx(free.r_net - 0.0025 * (100 + 103) / 10)

    def test_unjudgeable(self):
        df = _frame([(99, 99, 99, 99), (100, 102, 98, 101)])
        assert triple_barrier(df, 0, 3, 5.0) is None  # too few bars
        df = _frame([(99, 99, 99, 99)] * 5)
        assert triple_barrier(df, 0, 3, float("nan")) is None
        days = [date(2022, 1, 3), date(2022, 1, 4), date(2022, 1, 4) + timedelta(days=30)]
        gap = bars_frame([bar(d, 100, 101, 99, 100) for d in days])
        assert triple_barrier(gap, 0, 2, 5.0) is None  # suspension
