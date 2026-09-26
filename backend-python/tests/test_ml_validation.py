"""The AI layer's validation toolkit — splits, benchmarks, overfitting statistics."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.ml.validation import (
    deflated_sharpe_probability,
    expected_max_sharpe,
    holdout_start,
    pbo_cscv,
    random_filter_precisions,
    walk_forward_folds,
    week_block_bootstrap,
    wilson_interval,
)


def _daily(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class TestWalkForward:
    @pytest.fixture(scope="class")
    def data(self):
        dates = _daily(date(2015, 1, 1), date(2022, 12, 31))
        ends = [d + timedelta(days=42) for d in dates]  # a 30-session label
        return dates, ends

    def test_train_is_past_purged_and_embargoed(self, data):
        dates, ends = data
        folds = walk_forward_folds(dates, ends)
        assert [f.test_year for f in folds][0] == 2018  # three training years first
        for f in folds:
            start = date(f.test_year, 1, 1)
            assert all(dates[i] < start - timedelta(days=45) for i in f.train_idx)
            assert all(ends[i] < start for i in f.train_idx)
            assert all(dates[i].year == f.test_year for i in f.test_idx)
            assert set(f.fit_idx) | set(f.inner_idx) <= set(f.train_idx)
            assert not set(f.fit_idx) & set(f.inner_idx)
            assert all(dates[i].year == f.test_year - 1 for i in f.inner_idx)

    def test_the_holdout_is_never_in_a_fold(self, data):
        dates, ends = data
        cut = holdout_start(date(2022, 12, 31))
        folds = walk_forward_folds(dates, ends, holdout_from=cut)
        used = {i for f in folds for i in (*f.train_idx, *f.test_idx)}
        assert all(dates[i] < cut and ends[i] < cut for i in used)

    def test_rows_without_a_label_are_skipped(self, data):
        dates, ends = data
        ends = [None if i % 2 else e for i, e in enumerate(ends)]
        folds = walk_forward_folds(dates, ends)
        used = {i for f in folds for i in (*f.train_idx, *f.test_idx)}
        assert all(i % 2 == 0 for i in used)


class TestPrecisionTools:
    def test_wilson(self):
        lo, hi = wilson_interval(50, 100)
        assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
        assert wilson_interval(0, 0) == (0.0, 1.0)

    def test_random_filter_centres_on_the_base_rate(self):
        y = np.array([1.0] * 520 + [0.0] * 480)
        draws = random_filter_precisions(y, 0.4)
        assert draws.mean() == pytest.approx(0.52, abs=0.005)
        assert np.quantile(draws, 0.95) > 0.52
        assert np.array_equal(draws, random_filter_precisions(y, 0.4))  # seeded

    def test_week_block_bootstrap(self):
        dates = _daily(date(2021, 1, 4), date(2021, 12, 31))
        values = np.random.default_rng(3).normal(0.1, 1.0, len(dates))

        def weighted_mean(v, w):
            return float(np.sum(v * w) / np.sum(w))

        est, lo, hi = week_block_bootstrap(dates, values, weighted_mean, n_boot=500)
        assert lo < est < hi
        assert est == pytest.approx(values.mean())


class TestOverfittingStatistics:
    def test_hurdle_rises_with_trials(self):
        assert expected_max_sharpe(1, 0.01) == 0.0
        assert expected_max_sharpe(10, 0.01) < expected_max_sharpe(100, 0.01)

    def test_more_trials_less_confidence(self):
        one = deflated_sharpe_probability(0.1, 500, 1, 0.002)
        many = deflated_sharpe_probability(0.1, 500, 200, 0.002)
        assert one > many
        assert 0 < many < one < 1

    def test_pbo_on_noise_is_middling(self):
        noise = np.random.default_rng(1).normal(0, 1, (320, 20))
        pbo, logits = pbo_cscv(noise)
        assert 0.25 < pbo < 0.75
        assert len(logits) == 12870  # C(16, 8)

    def test_pbo_with_a_genuinely_better_strategy_is_low(self):
        rng = np.random.default_rng(2)
        perf = rng.normal(0, 1, (320, 20))
        perf[:, 0] += 0.8
        pbo, _ = pbo_cscv(perf)
        assert pbo < 0.05

    def test_pbo_refuses_bad_shapes(self):
        assert np.isnan(pbo_cscv(np.zeros((10, 1)))[0])
