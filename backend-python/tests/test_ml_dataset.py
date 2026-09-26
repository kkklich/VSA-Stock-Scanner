"""The AI layer's dataset assembly — cross-sectional features, L1, both jobs."""

from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from app.analysis.methods.base import MethodSignal
from app.ml import features as feat
from app.ml.dataset import (
    FEATURE_COLUMNS,
    MIN_STOCKS_PER_DAY,
    StockInput,
    build_panel,
    job1_rows,
    job2_rows,
    write_dataset,
)
from tests.ml_synthetic import random_walk_bars

FIRING_POSITIONS = (150, 180, 220)


class _FakeVsa4:
    """Fires at fixed positions, so the Job-1 rows are known in advance."""

    def signals(self, bars, config=None):
        ordered = sorted(bars, key=lambda b: b.date)
        return [
            MethodSignal(date=ordered[i].date, label="Strength → Test", type="Bullish")
            for i in FIRING_POSITIONS
            if i < len(ordered)
        ]


@pytest.fixture(autouse=True)
def only_fake_methods(monkeypatch):
    # Real methods are exercised in test_ml_features; here they would only slow
    # 25 stocks down. Every other method id resolves to "not registered".
    monkeypatch.setattr(feat, "get_method", lambda mid: _FakeVsa4() if mid == "vsa4" else None)


def _stocks(count: int, bars: int = 260) -> list[StockInput]:
    return [
        StockInput(
            ticker=f"t{i:02d}",
            market="gpw",
            currency="PLN",
            sector="Banks" if i % 2 else "Energy",
            bars=random_walk_bars(bars, seed=100 + i),
        )
        for i in range(count)
    ]


@pytest.fixture(scope="module")
def panel():
    mp = pytest.MonkeyPatch()
    mp.setattr(feat, "get_method", lambda mid: _FakeVsa4() if mid == "vsa4" else None)
    try:
        yield build_panel(_stocks(MIN_STOCKS_PER_DAY + 5))
    finally:
        mp.undo()


class TestPanel:
    def test_one_row_per_stock_session_with_every_feature(self, panel):
        assert len(panel) == (MIN_STOCKS_PER_DAY + 5) * 260
        for col in FEATURE_COLUMNS:
            assert col in panel.columns

    def test_percentiles_are_within_the_market_day(self, panel):
        pct = panel["turnover_pct"].dropna()
        assert pct.between(0, 1).all()
        # Every day's percentiles are a full ranking of that day's stocks.
        day = panel.loc[panel["position"] == 200, "turnover_pct"]
        assert day.max() == 1.0 and day.nunique() == len(day)

    def test_regime_is_one_value_per_market_day(self, panel):
        per_day = panel.groupby("date")["reg_breadth50"].nunique(dropna=False)
        assert (per_day == 1).all()
        assert panel.loc[panel["position"] == 250, "reg_mkt_ret20"].notna().all()

    def test_l1_splits_each_day_about_in_half(self, panel):
        for n in (10, 30):
            valid = panel.dropna(subset=[f"l1_y_{n}"])
            share = valid.groupby("date")[f"l1_y_{n}"].mean()
            # With 25 stocks, strictly above the median is 12 of 25.
            assert share.between(0.4, 0.6).all()

    def test_labels_stop_where_the_future_ends(self, panel):
        last = panel.loc[panel["position"] == 259]
        assert last["l1_y_10"].isna().all() and last["fwd_r_10"].isna().all()


class TestThinMarket:
    def test_too_few_stocks_means_no_regime_and_no_l1(self):
        thin = build_panel(_stocks(5, bars=120))
        assert thin["reg_breadth50"].isna().all()
        assert thin["l1_y_10"].isna().all()
        assert thin["l2_y_10"].notna().any()  # the stock's own frame still works


class TestJobs:
    def test_job2_samples_every_fifth_session_with_a_label(self, panel):
        rows = job2_rows(panel)
        assert (rows["position"] % 5 == 0).all()
        assert (rows["l1_y_10"].notna() | rows["l1_y_30"].notna()).all()

    def test_job1_one_row_per_firing(self, panel):
        rows = job1_rows(panel)
        assert set(rows["method"]) == {"vsa4"}
        assert len(rows) == (MIN_STOCKS_PER_DAY + 5) * len(FIRING_POSITIONS)
        assert set(rows["position"]) == set(FIRING_POSITIONS)
        assert (rows["setup"] == "Strength → Test").all()

    def test_firing_features(self, panel):
        rows = job1_rows(panel).sort_values(["ticker", "position"])
        first = rows.groupby("ticker").head(1)
        assert (first["h_since_prev"] == 250).all()  # nothing before it
        assert (first["h_prior_firings60"] == 0).all()
        second = rows[rows["position"] == 180]
        assert (second["h_since_prev"] == 30).all()
        assert (second["h_prior_firings60"] == 1).all()

    def test_trade_labels_exist_on_firings(self, panel):
        rows = job1_rows(panel)
        assert rows["l3_r_10"].notna().all()
        assert set(rows["l3_exit_10"]) <= {"stop", "target", "time"}


class TestWrite:
    def test_writes_gzip_csv_and_metadata(self, panel, tmp_path):
        rows = job1_rows(panel)
        path = tmp_path / "job1.csv.gz"
        info = write_dataset(rows, path, {"markets": ["gpw"]})
        meta = json.loads((tmp_path / "job1.csv.gz.meta.json").read_text(encoding="utf-8"))
        assert meta["rows"] == len(rows) == info["rows"]
        assert meta["markets"] == ["gpw"] and len(meta["sha256"]) == 64
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            back = pd.read_csv(handle)
        assert len(back) == len(rows)
        assert np.allclose(back["vsa_rating"], rows["vsa_rating"])
