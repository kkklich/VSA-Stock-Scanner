"""Phase 1's numpy logistic regression and its preprocessing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.metrics import brier, reliability, roc_auc, top_fraction_precision
from app.ml.models.logistic import LogisticRegression, Preprocessor


def _data(n=20_000, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 3))
    logits = 0.3 + 1.5 * x[:, 0] - 1.0 * x[:, 1]
    y = (rng.random(n) < 1 / (1 + np.exp(-logits))).astype(float)
    return x, y


class TestLogisticRegression:
    def test_recovers_known_weights(self):
        x, y = _data()
        model = LogisticRegression(c=1e6).fit(x, y)
        assert model.coef_ == pytest.approx([1.5, -1.0, 0.0], abs=0.08)
        assert model.intercept_ == pytest.approx(0.3, abs=0.06)

    def test_the_penalty_shrinks_weights(self):
        x, y = _data(2_000)
        loose = LogisticRegression(c=1.0).fit(x, y)
        tight = LogisticRegression(c=0.0005).fit(x, y)
        assert np.abs(tight.coef_).sum() < np.abs(loose.coef_).sum()

    def test_separable_data_stays_finite(self):
        x = np.array([[-2.0], [-1.0], [1.0], [2.0]])
        y = np.array([0.0, 0.0, 1.0, 1.0])
        model = LogisticRegression(c=0.1).fit(x, y)
        assert np.isfinite(model.coef_).all() and model.coef_[0] > 0
        assert model.n_iter_ < model.max_iter

    def test_a_weight_equals_a_duplicated_row(self):
        x, y = _data(500, seed=3)
        doubled = LogisticRegression(c=0.5).fit(np.vstack([x, x[:50]]), np.concatenate([y, y[:50]]))
        weights = np.ones(500)
        weights[:50] = 2
        weighted = LogisticRegression(c=0.5).fit(x, y, weights)
        assert weighted.coef_ == pytest.approx(doubled.coef_, abs=1e-6)

    def test_one_class_does_not_crash(self):
        model = LogisticRegression().fit(np.random.default_rng(1).normal(size=(40, 2)), np.ones(40))
        assert (model.predict_proba(np.zeros((1, 2))) > 0.99).all()

    def test_used_before_fit(self):
        with pytest.raises(RuntimeError):
            LogisticRegression().predict_proba(np.zeros((1, 1)))


class TestPreprocessor:
    def _frame(self):
        return pd.DataFrame(
            {
                "a": [1.0, 2.0, np.nan, 4.0],
                "b": [5.0, 5.0, 5.0, 5.0],  # constant → dropped
                "c": [np.nan] * 4,  # never observed → ignored
                "sector": ["Banks", "Banks", "Energy", "IT"],
            }
        )

    def test_fits_on_training_rows_only(self):
        pre = Preprocessor(numeric=["a", "b", "c"], categorical=["sector"],
                           max_levels={"sector": 1}).fit(self._frame())
        names = pre.feature_names
        assert "a" in names and "a__missing" in names
        assert "b" not in names and "c" not in names
        assert "sector=Banks" in names and "sector=__other__" in names
        # A later row on a different scale does not move the training statistics.
        later = pd.DataFrame({"a": [1000.0], "b": [5.0], "c": [1.0], "sector": ["Mining"]})
        row = pre.transform(later)[0]
        assert row[names.index("a")] > 100  # standardised with the training spread
        assert row[names.index("sector=__other__")] > 0  # unseen → other

    def test_a_gap_is_filled_with_the_training_median(self):
        pre = Preprocessor(numeric=["a"]).fit(self._frame())
        filled = pre.transform(pd.DataFrame({"a": [np.nan]}))[0]
        median_row = pre.transform(pd.DataFrame({"a": [2.0]}))[0]
        assert filled[0] == pytest.approx(median_row[0])  # median of 1, 2, 4
        assert filled[1] != median_row[1]  # but its missing flag differs

    def test_transform_before_fit(self):
        with pytest.raises(RuntimeError):
            Preprocessor(numeric=["a"]).transform(self._frame())


class TestMetrics:
    def test_auc_extremes_and_ties(self):
        y = np.array([0, 0, 1, 1])
        assert roc_auc(y, np.array([1, 2, 3, 4])) == 1.0
        assert roc_auc(y, np.array([4, 3, 2, 1])) == 0.0
        assert roc_auc(y, np.array([1, 1, 1, 1])) == 0.5
        assert np.isnan(roc_auc(np.ones(4), np.arange(4)))

    def test_auc_equals_the_pairwise_definition(self):
        rng = np.random.default_rng(5)
        y = (rng.random(300) < 0.4).astype(float)
        s = np.round(rng.normal(size=300) + y, 1)  # rounded → ties
        pos, neg = s[y == 1], s[y == 0]
        pairwise = ((pos[:, None] > neg[None, :]) + 0.5 * (pos[:, None] == neg[None, :])).mean()
        assert roc_auc(y, s) == pytest.approx(pairwise)

    def test_brier_and_top_fraction(self):
        y = np.array([1, 0, 1, 0])
        assert brier(y, np.full(4, 0.5)) == 0.25
        assert top_fraction_precision(y, np.array([0.9, 0.1, 0.8, 0.2]), 0.5) == 1.0

    def test_reliability_covers_every_row(self):
        rng = np.random.default_rng(2)
        p = rng.random(500)
        y = (rng.random(500) < p).astype(float)
        table = reliability(y, p)
        assert sum(r[2] for r in table) == 500
