"""The AI layer's feature builder — point in time, formulas, robustness."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.analysis.vsa import compute_rating, detect_signals
from app.ml import features as feat
from app.ml.features import (
    AUX_COLUMNS,
    STOCK_FEATURE_COLUMNS,
    sessions_since,
    stock_features,
)
from app.ml.validation import truncation_check
from tests.ml_synthetic import bar, random_walk_bars, weekdays


@pytest.fixture(scope="module")
def series():
    return random_walk_bars(420, seed=7)


@pytest.fixture(scope="module")
def frame(series):
    return stock_features(series)


class TestShape:
    def test_every_column_present_one_row_per_session(self, series, frame):
        assert len(frame) == len(series)
        for col in ["date", *STOCK_FEATURE_COLUMNS, *AUX_COLUMNS, feat.LABEL_COLUMN]:
            assert col in frame.columns

    def test_no_infinities(self, frame):
        values = frame[STOCK_FEATURE_COLUMNS].to_numpy(dtype=float)
        assert not np.isinf(values).any()

    def test_empty_input_gives_empty_frame_with_columns(self):
        out = stock_features([])
        assert out.empty and "vsa_rating" in out.columns

    def test_duplicate_dates_are_collapsed(self, series):
        doubled = series[:80] + series[79:80]
        assert len(stock_features(doubled)) == 80

    def test_mature_rows_are_filled(self, frame):
        last = frame.iloc[-1]
        missing = [c for c in STOCK_FEATURE_COLUMNS if np.isnan(last[c])]
        # 420 weekdays span ~20 months: everything, including the 52-week
        # context and the weekly read, is available by the last row.
        assert missing == []


class TestPointInTime:
    def test_truncated_histories_give_identical_rows(self, series):
        positions = [419, 418, 417, 333, 260, 200, 120, 61]
        problems = truncation_check(series, positions, stock_features, STOCK_FEATURE_COLUMNS)
        assert problems == []

    def test_a_leaky_feature_would_be_caught(self, series):
        def leaky(bars):
            out = stock_features(bars)
            out["vol_rel20"] = out["vol_rel20"].shift(-1)  # tomorrow's value
            return out

        problems = truncation_check(series, [300], leaky, ["vol_rel20"])
        assert [p.column for p in problems] == ["vol_rel20"]


class TestFormulas:
    def _flat(self, days: int, *, volume: int = 1000):
        return [bar(d, 10, 11, 9, 10, volume) for d in weekdays(date(2021, 1, 4), days)]

    def test_close_position_and_spread(self):
        bars = self._flat(25) + [bar(date(2021, 2, 8), 10, 13, 10, 12.5, 1000)]
        out = stock_features(bars)
        last = out.iloc[-1]
        assert last["close_pos"] == pytest.approx(2.5 / 3)
        assert last["spread_rel20"] == pytest.approx(3 / 2)  # normal spread is 2

    def test_zero_spread_bar_reads_neutral(self):
        bars = self._flat(25) + [bar(date(2021, 2, 8), 10, 10, 10, 10, 1000)]
        last = stock_features(bars).iloc[-1]
        assert last["close_pos"] == 0.5
        assert last["body_pos"] == 0.0

    def test_volume_features(self):
        bars = self._flat(70) + [bar(date(2021, 4, 12), 10, 11, 9, 10, 3000)]
        last = stock_features(bars).iloc[-1]
        assert last["vol_rel20"] == pytest.approx(3.0)
        assert last["vol_rel_med20"] == pytest.approx(3.0)
        assert last["vol_new_max20"] == 1.0
        assert last["vol_pct60"] == 1.0  # above every one of the prior 60

    def test_first_row_has_no_up_bar_reading(self):
        out = stock_features(self._flat(5))
        assert np.isnan(out.iloc[0]["up_bar"])

    def test_52_week_context_blank_without_a_year_of_history(self):
        out = stock_features(random_walk_bars(200, seed=3))  # ~9 months
        assert out["dist_52w_high"].isna().all()
        assert out["new_52w_high"].isna().all()

    def test_rating_matches_the_engine_on_its_window(self, series, frame):
        # The vectorised decay must equal vsa.compute_rating over the same
        # signals: those detected on the full history, within 120 days of t.
        signals = detect_signals(series)
        for pos in (419, 350, 300):
            as_of = series[pos].date
            window = [s for s in signals if 0 <= (as_of - s.date).days <= 120]
            assert frame.iloc[pos]["vsa_rating"] == compute_rating(window, as_of)

    def test_weekly_read_needs_thirty_completed_weeks(self):
        out = stock_features(random_walk_bars(140, seed=5))  # 28 weeks
        assert out["weekly_rating"].isna().all()


class TestVsa4PointInTime:
    """VSA V4 is read as the program would have read it on each day."""

    @pytest.fixture(scope="class")
    def crossing(self):
        # Climbs from ~6 zł to well above 10 zł: the program's price tolerance
        # (sized from the last close) changes bucket half-way through.
        return random_walk_bars(360, seed=21, price=6.0, drift=0.004, vol=0.025)

    def test_the_series_really_crosses_a_tolerance_level(self, crossing):
        from app.analysis.vsa4.adapter import tick_size

        assert len({tick_size(float(b.close)) for b in crossing}) > 1

    def test_each_row_equals_the_program_run_on_data_ending_that_day(self, crossing):
        dates, rows = feat.vsa4_rows(crossing, "point_in_time")
        keys = ("long_setup_confirmation", "short_setup_confirmation", "long_setup_pending")
        for t in (45, 120, 200, 280, 359):
            _, truncated = feat.vsa4_rows(crossing[: t + 1], "last_close")
            assert {k: rows[t][k] for k in keys} == {k: truncated[t][k] for k in keys}

    def test_its_features_pass_the_truncation_check(self, crossing):
        cols = ["m_vsa4_fired1", "m_vsa4_fired5", "m_vsa4_since", "m_vsa4_bear5", "m_vsa4_watch5"]
        problems = truncation_check(crossing, [100, 180, 250, 330], stock_features, cols)
        assert problems == []

    def test_the_last_close_reading_matches_the_method_itself(self, crossing):
        from app.analysis.methods import get_method

        firings = {s.date for s in get_method("vsa4").signals(crossing) if s.type == "Bullish"}
        out = stock_features(crossing, method_ids=("vsa4",), vsa4_tick="last_close")
        assert set(out.loc[out["fire_vsa4"] > 0, "date"]) == firings


class TestSessionsSince:
    def test_counts_and_cap(self):
        ev = np.array([0, 1, 0, 0, 1, 0], dtype=bool)
        assert list(sessions_since(ev, 3)) == [3, 0, 1, 2, 0, 1]

    def test_exclusive_looks_at_earlier_rows_only(self):
        ev = np.array([1, 0, 1, 0], dtype=bool)
        assert list(sessions_since(ev, 9, exclusive=True)) == [9, 1, 2, 1]


class TestRobustness:
    def test_a_failing_method_leaves_its_columns_empty(self, series, monkeypatch):
        real = feat.get_method

        class Broken:
            def signals(self, bars, config=None):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            feat, "get_method", lambda mid: Broken() if mid == "breakout" else real(mid)
        )
        out = stock_features(series[:150])
        assert out["m_breakout_fired5"].isna().all()
        assert out["m_minervini_since"].notna().all()

    def test_method_signals_land_on_their_dates(self, series, monkeypatch):
        from app.analysis.methods.base import MethodSignal

        target = series[100].date

        class Fake:
            def signals(self, bars, config=None):
                return [
                    MethodSignal(date=target, label="Test setup", type="Bullish"),
                    MethodSignal(date=target + timedelta(days=400), label="x", type="Bullish"),
                ]

        monkeypatch.setattr(feat, "get_method", lambda mid: Fake())
        out = stock_features(series[:150], method_ids=("vsa4",))
        assert out["fire_vsa4"].sum() == 1
        assert out.iloc[100]["fire_vsa4"] == 1
        assert out.iloc[104]["m_vsa4_fired5"] == 1
        assert out.iloc[105]["m_vsa4_fired5"] == 0
        assert out.iloc[103]["m_vsa4_since"] == 3
        assert out.iloc[100][feat.LABEL_COLUMN] == "Test setup"
