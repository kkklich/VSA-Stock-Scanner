"""The owner's own tests for the VSA program, run against the vendored copy.

Ported from the "VSA - kompendium i program Python" package supplied on
2026-09-24: ``python/test_vsa.py`` (14 unit + regression tests, below as-is
apart from the imports) and ``python/verify_independent.py`` (8 independent
causality / execution checks, turned into test functions at the bottom). They
passing here is what shows ``app/analysis/vsa4`` still behaves exactly like the
program the owner verified — including after the ``[StockPilot]`` lines that
report the sequence state.
"""
import random
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.analysis.vsa4.backtest import _close_execution_price, run_backtest
from app.analysis.vsa4.engine import (
    SIGNAL_NAMES, Bar, Config, VSAError, add_confirmation_and_setup_events,
    analyze, build_features, load_ohlcv_text,
)


def bar(i, o=100.0, h=101.0, l=99.0, c=100.0, v=100.0):
    stamp = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
    return Bar(stamp.isoformat().replace("+00:00", "Z"), o, h, l, c, v)


def cfg(**extra):
    values = dict(baseline_window=4, atr_window=2, trend_window=3,
                  structure_window=3, test_window=12, sequence_window=12,
                  confirmation_window=3, pivot_left_bars=1,
                  pivot_right_bars=1, max_pivot_gap=12, min_tick=0.01,
                  stop_buffer_atr=0.0, reward_risk=1.0,
                  commission_bps=0.0, slippage_bps=0.0)
    values.update(extra)
    return Config.from_mapping(values)


def flat(n=8):
    return [bar(i, 100+i*.1, 100.6+i*.1, 99.6+i*.1,
                100.1+i*.1, 100) for i in range(n)]


def flags(n):
    return [{name: False for name in SIGNAL_NAMES} for _ in range(n)]


def event_rows(n):
    return [dict(long_setup_confirmation=False, short_setup_confirmation=False,
                 setup_stop_level=None, setup_reference_signal="", entry_status="")
            for _ in range(n)]


class InputTests(unittest.TestCase):
    def test_csv_accepts_zero_volume_and_zero_range(self):
        b = load_ohlcv_text("timestamp,open,high,low,close,volume\n2025-01-01T00:00:00Z,10,10,10,10,0\n")
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].volume, 0)

    def test_csv_rejects_empty_order_nan_price_negative_volume_and_bad_ohlc(self):
        invalid = [
            "timestamp,open,high,low,close,volume\n",
            "timestamp,open,high,low,close,volume\n2025-01-01,10,11,9,10,1\n2025-01-01,10,11,9,10,1\n",
            "timestamp,open,high,low,close,volume\n2025-01-01T00:00:00Z,NaN,11,9,10,1\n",
            "timestamp,open,high,low,close,volume\n2025-01-01T00:00:00Z,0,11,9,10,1\n",
            "timestamp,open,high,low,close,volume\n2025-01-01T00:00:00Z,10,11,9,10,-1\n",
            "timestamp,open,high,low,close,volume\n2025-01-01T00:00:00Z,10,9,8,10,1\n",
        ]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(VSAError):
                load_ohlcv_text(text)

    def test_config_rejects_bad_type_and_ranges(self):
        for data in ({"baseline_window": 0}, {"close_high_threshold": "x"},
                     {"slippage_bps": 10000}, {"test_volume_ratio": 1},
                     {"unknown": 1}):
            with self.subTest(data=data), self.assertRaises(VSAError):
                Config.from_mapping(data)


class SignalTests(unittest.TestCase):
    def test_ns_nd_pink_and_zero_data_are_not_signals(self):
        b = flat(6)
        b += [bar(6, 100.75, 100.80, 100.30, 100.45, 50),
              bar(7, 100.44, 100.56, 100.40, 100.50, 45),
              bar(8, 100.5, 100.9, 100.2, 100.3, 0),
              bar(9, 100.3, 100.3, 100.3, 100.3, 20)]
        r = analyze(b, cfg())
        self.assertTrue(r[6]["candidate_no_supply"])
        self.assertTrue(r[6]["down_bar"])
        self.assertTrue(r[7]["candidate_no_demand"])
        self.assertTrue(r[7]["up_bar"])
        for i in (8, 9):
            self.assertFalse(r[i]["candidate_no_supply"])
            self.assertFalse(r[i]["candidate_no_demand"])
            self.assertFalse(r[i]["candidate_test"])
        self.assertIsNone(r[9]["close_position"])

    def test_test_retests_strength_zone_and_does_not_require_pink(self):
        b = flat(5)
        b += [bar(5, 100.75, 100.90, 99.20, 100.40, 300),
              bar(6, 100.35, 100.50, 99.25, 100.30, 110)]
        r = analyze(b, cfg())
        self.assertTrue(r[5]["candidate_shakeout"])
        self.assertFalse(r[6]["pink_volume"])
        self.assertTrue(r[6]["candidate_test"])

    def test_climax_requires_record_volume(self):
        b = [bar(0,102.1,102.6,101.6,102,100), bar(1,101.8,102.3,101.3,101.7,100),
             bar(2,101.5,102,101,101.4,100), bar(3,101.2,101.7,100.7,101.1,100),
             bar(4,100.9,101.4,100.4,100.8,100), bar(5,100.8,101.2,100.2,101,200),
             bar(6,101,101.1,99.2,99.9,180), bar(7,99.9,100,98.1,98.8,220)]
        r = analyze(b, cfg(baseline_window=5, trend_window=2))
        self.assertFalse(r[6]["candidate_selling_climax"])
        self.assertTrue(r[7]["candidate_selling_climax"])
        self.assertIn("record volume", r[7]["candidate_reasons"])

    def test_wfo_is_emitted_on_detection_bar_with_source_timestamp(self):
        highs = [103,104,102,103,106,103,102,101,107,100]
        vols = [100,100,100,100,300,40,45,50,80,100]
        b = [bar(i,100,float(highs[i]),99,100,float(vols[i])) for i in range(len(highs))]
        r = analyze(b, cfg())
        self.assertFalse(r[8]["candidate_wfo_bearish"])
        self.assertTrue(r[9]["candidate_wfo_bearish"])
        self.assertEqual(r[9]["wfo_pivot_timestamp"], b[8].timestamp)
        self.assertEqual(r[9]["wfo_detection_timestamp"], b[9].timestamp)

    def test_confirmation_is_only_added_at_later_observation(self):
        b = flat(6)
        b[5] = bar(5,100.6,100.75,100.2,100.35,50)
        b.append(bar(6,100.35,101,100.25,100.8,55))
        r = analyze(b, cfg())
        self.assertTrue(r[5]["candidate_no_supply"])
        self.assertEqual(r[5]["price_confirmed_bullish_signals"], "")
        self.assertIn("no_supply@", r[6]["price_confirmed_bullish_signals"])

    def test_prefix_causality(self):
        b = flat(6) + [bar(6,100.75,100.8,100.3,100.45,50),
                       bar(7,100.44,100.56,100.4,100.5,45),
                       bar(8,100.5,100.9,100.2,100.3,0)]
        full = analyze(b, cfg())
        for end in range(1, len(b)+1):
            self.assertEqual(analyze(b[:end], cfg()), full[:end], f"prefix {end}")

    def test_invalidated_primary_and_secondary_do_not_confirm(self):
        b = flat(6)
        b[1] = bar(1,100,101,99,100,100)
        b[3] = bar(3,100,101,98.5,100.2,100)
        b[4] = bar(4,100.2,101,99.5,100.8,50)
        b[5] = bar(5,100.8,102,100,101.8,150)
        f = flags(len(b)); f[1]["shakeout"] = True; f[4]["no_supply"] = True
        c = cfg(stop_buffer_atr=.05); r = add_confirmation_and_setup_events(b, build_features(b,c), f,
                                                         [[] for _ in b], [[] for _ in b], c)
        self.assertFalse(r[5]["long_setup_confirmation"])

        b[3] = bar(3,100,101,99.2,100.2,50)
        b[4] = bar(4,100.2,102,98,101,100)
        b[5] = bar(5,101,103,100,102.5,150)
        f = flags(len(b)); f[1]["shakeout"] = True; f[3]["no_supply"] = True
        r = add_confirmation_and_setup_events(b, build_features(b,c), f,
                                              [[] for _ in b], [[] for _ in b], c)
        self.assertFalse(r[5]["long_setup_confirmation"])

    def test_two_bar_primary_first_extreme_is_in_setup_stop(self):
        b = flat(5)
        b[1] = bar(1,100,101,89,99.5,100)
        b[2] = bar(2,99.5,101,95,100.5,100)
        b[3] = bar(3,100.4,100.8,95.5,100.2,50)
        b[4] = bar(4,100.2,101.5,99.8,101.2,150)
        f = flags(len(b)); f[2]["strength_two_bar_reversal"] = True; f[3]["no_supply"] = True
        c = cfg(stop_buffer_atr=.05); r = add_confirmation_and_setup_events(b, build_features(b,c), f,
                                                         [[] for _ in b], [[] for _ in b], c)
        self.assertTrue(r[4]["long_setup_confirmation"])
        self.assertLess(float(r[4]["setup_stop_level"]), 89)


class BacktestTests(unittest.TestCase):
    def rows(self, direction, stop):
        r = event_rows(3)
        r[0][f"{direction}_setup_confirmation"] = True
        r[0]["setup_stop_level"] = stop
        r[0]["setup_reference_signal"] = "test"
        return r

    def test_entry_bar_stop_first_when_stop_and_target_both_hit(self):
        for direction, stop in (("long",95), ("short",105)):
            with self.subTest(direction=direction):
                b = [bar(0), bar(1,100,106,94,100,100), bar(2)]
                trades, _, _ = run_backtest(b, self.rows(direction,stop), cfg())
                self.assertEqual(trades[0]["exit_reason"], "stop_same_bar_both_hit")
                self.assertEqual(trades[0]["exit_bar_index"], 1)

    def test_gap_through_entry_stop_skips_trade(self):
        b = [bar(0),bar(1,94,96,93,95,100),bar(2)]
        trades, _, summary = run_backtest(b,self.rows("long",95),cfg())
        self.assertEqual(trades, [])
        self.assertEqual(summary["skipped_entries"],1)

    def test_short_size_respects_risk_after_slippage_and_both_fees(self):
        c = cfg(risk_fraction=.02,max_notional_fraction=1,commission_bps=50,slippage_bps=80)
        b = [bar(0),bar(1,100,100.2,99.5,100,100),bar(2,100,110,99,108,100)]
        trades,equity,summary = run_backtest(b,self.rows("short",110),c)
        t=trades[0]; entry=float(t["entry_price"])
        exit_fill=_close_execution_price(110,-1,c)
        per_unit=exit_fill-entry+(entry+exit_fill)*c.commission_bps/10000
        self.assertEqual(t["exit_reason"],"stop")
        self.assertGreater(per_unit,0)
        self.assertLessEqual(float(t["quantity"])*per_unit,c.initial_capital*c.risk_fraction+1e-9)
        self.assertAlmostEqual(summary["final_equity"],c.initial_capital+float(t["net_pnl"]))
        self.assertAlmostEqual(equity[-1]["equity"],summary["final_equity"])


# ── python/verify_independent.py, as test functions ──────────────────────────
# The original is a script that asserts in sequence and prints a JSON summary;
# each of its eight checks is one test below, with its assertions unchanged.


def _stamp(i):
    return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)).isoformat()


def _b(i, o, h, l, c, v=100):
    return Bar(_stamp(i), o, h, l, c, v)


def _rows_for(bars, side="long", stop=95):
    rows = [dict(long_setup_confirmation=False, short_setup_confirmation=False,
                 setup_stop_level=None, setup_reference_signal="", entry_status="")
            for _ in bars]
    rows[0].update({side + "_setup_confirmation": True, "setup_stop_level": stop,
                    "setup_reference_signal": "manual_execution_fixture"})
    return rows


def _random_walk():
    rng = random.Random(917)
    bars = []
    close = 100.0
    for i in range(180):
        o = close + rng.uniform(-.5, .5)
        close = max(10, o + rng.uniform(-2, 2))
        h = max(o, close) + rng.uniform(.05, 1.8)
        l = min(o, close) - rng.uniform(.05, 1.8)
        bars.append(_b(i, o, h, l, close, 0 if i in (51, 89) else rng.randrange(10, 900)))
    return bars


_NO_COSTS = replace(Config(), commission_bps=0, slippage_bps=0)


def test_independent_causal_analysis_prefixes_match_full_history():
    bars = _random_walk()
    full = analyze(bars, Config())
    for n in (1, 2, 19, 20, 21, 31, 59, 100, 179):
        assert analyze(bars[:n], Config()) == full[:n], f"Future data changed prefix {n}"


def test_independent_zero_volume_is_not_a_signal():
    full = analyze(_random_walk(), Config())
    assert not any(full[51]["candidate_" + s] for s in ("no_supply", "no_demand", "test"))


def test_independent_long_stop_first_exact_planned_loss():
    longbars = [_b(0, 100, 101, 99, 100), _b(1, 100, 116, 94, 101)]
    t, e, s = run_backtest(longbars, _rows_for(longbars), _NO_COSTS)
    assert len(t) == 1 and t[0]["exit_reason"] == "stop_same_bar_both_hit"
    assert abs(s["final_equity"] - 9900) < 1e-8


def test_independent_short_stop_first_exact_planned_loss():
    shortbars = [_b(0, 100, 101, 99, 100), _b(1, 100, 106, 84, 99)]
    t, e, s = run_backtest(shortbars, _rows_for(shortbars, "short", 105), _NO_COSTS)
    assert len(t) == 1 and t[0]["exit_reason"] == "stop_same_bar_both_hit"
    assert abs(s["final_equity"] - 9900) < 1e-8


def test_independent_entry_gap_through_stop_means_no_trade():
    gapbars = [_b(0, 100, 101, 99, 100), _b(1, 90, 92, 89, 91)]
    t, e, s = run_backtest(gapbars, _rows_for(gapbars), _NO_COSTS)
    assert not t and s["final_equity"] == 10000


def test_independent_held_position_gap_fills_at_open():
    gapbars = [_b(0, 100, 101, 99, 100), _b(1, 100, 104, 96, 102), _b(2, 90, 92, 89, 91)]
    t, e, s = run_backtest(gapbars, _rows_for(gapbars), _NO_COSTS)
    assert t[0]["exit_reason"] == "stop_gap_open" and t[0]["exit_price"] == 90
    assert abs(s["final_equity"] - 9800) < 1e-8


def test_independent_equity_reconciles_with_net_pnl_after_costs():
    longbars = [_b(0, 100, 101, 99, 100), _b(1, 100, 116, 94, 101)]
    costcfg = replace(_NO_COSTS, commission_bps=10, slippage_bps=5)
    t, e, s = run_backtest(longbars, _rows_for(longbars), costcfg)
    net = sum(x["net_pnl"] for x in t)
    assert abs(s["final_equity"] - (10000 + net)) < 1e-8
    assert t[0]["entry_commission"] > 0 and t[0]["exit_commission"] > 0


def test_independent_cost_adjusted_sizing_respects_risk_budget():
    stresscfg = replace(_NO_COSTS, commission_bps=250, slippage_bps=500)
    stressbars = [_b(0, 100, 101, 99, 100), _b(1, 100, 200, 1, 100)]
    for side, stop in [("long", 95), ("short", 105)]:
        t, e, s = run_backtest(stressbars, _rows_for(stressbars, side, stop), stresscfg)
        assert len(t) == 1
        assert -t[0]["net_pnl"] <= _NO_COSTS.initial_capital * _NO_COSTS.risk_fraction + 1e-8, (
            f"{side}: costs exceeded risk budget without gap"
        )
