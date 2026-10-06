"""Phase 1's walk-forward runner — finds a planted signal, not noise, and never peeks."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml.dataset import FEATURE_COLUMNS, JOB1_FEATURE_COLUMNS
from app.ml.phase1 import (
    MIN_KEPT_INNER,
    choose_keep_rate,
    method_weights,
    run_hand_rule,
    run_job1,
    run_job2,
    summarise_filter,
    summarise_score,
)
from tests.ml_synthetic import weekdays

HOLDOUT = date(2025, 1, 1)
METHODS = ("vsa4", "weinstein", "glinicki", "breakout")


def _frame(signal: float, seed: int = 0, per_day: int = 2) -> pd.DataFrame:
    """Firings 2019–2025 with random features; ``signal`` plants a real effect.

    With ``signal`` > 0 a firing beats its market when relative strength
    (plus noise) is high, and its trade result follows — the filter should
    find that. With 0 there is nothing to find.
    """
    rng = np.random.default_rng(seed)
    days = [d for d in weekdays(date(2019, 1, 7), 1650) for _ in range(per_day)]
    n = len(days)
    data = {col: rng.normal(size=n) for col in set(JOB1_FEATURE_COLUMNS) | set(FEATURE_COLUMNS)}
    data["rs_pct"] = rng.random(n)
    data["weekly_agree"] = rng.choice([-1.0, 0.0, 1.0], n)
    data["vsa_rating"] = rng.uniform(0, 100, n)
    y = (signal * (data["rs_pct"] - 0.5) + rng.normal(0, 0.3, n) > 0).astype(float)
    frame = pd.DataFrame(data)
    frame["date"] = [d.isoformat() for d in days]
    frame["ticker"] = [f"s{i % 40}" for i in range(n)]
    frame["market"] = "gpw"
    frame["sector"] = rng.choice(["Banks", "Energy", "IT"], n)
    frame["method"] = rng.choice(METHODS, n, p=[0.4, 0.1, 0.35, 0.15])
    frame["setup"] = np.where(frame["method"] == "vsa4", "Shakeout → Test", frame["method"])
    for h in (10, 30):
        frame[f"l1_y_{h}"] = y
        frame[f"fwd_end_{h}"] = [(d + timedelta(days=h + 4)).isoformat() for d in days]
        frame[f"l3_r_{h}"] = np.where(y == 1, 0.8, -0.6) + rng.normal(0, 0.2, n)
    return frame


@pytest.fixture(scope="module")
def planted():
    return _frame(signal=4.0)


@pytest.fixture(scope="module")
def noise():
    return _frame(signal=0.0, seed=1)


class TestJob1:
    def test_finds_a_planted_signal(self, planted):
        run = run_job1(planted, 10, 0.1, holdout_from=HOLDOUT)
        assert [f.test_year for f in run.folds] == [2022, 2023, 2024]
        s = summarise_filter(run.oos)
        assert s.beats_random and s.auc > 0.75
        assert s.r_kept > s.r_unfiltered
        assert set(run.oos["method"]) <= {"vsa4", "weinstein"}  # judged on primaries

    def test_finds_nothing_in_noise(self, noise):
        s = summarise_filter(run_job1(noise, 10, 0.1, holdout_from=HOLDOUT).oos)
        assert abs(s.auc - 0.5) < 0.08

    def test_shuffled_labels_learn_nothing(self, planted):
        run = run_job1(planted, 10, 0.1, holdout_from=HOLDOUT, shuffle_labels=True)
        assert abs(summarise_filter(run.oos).auc - 0.5) < 0.1

    def test_test_year_answers_cannot_change_its_predictions(self, planted):
        # Flip every label and trade result in 2024: the 2024 predictions must
        # not move, because nothing from the test year enters the fit.
        flipped = planted.copy()
        in_2024 = flipped["date"].str.startswith("2024")
        for h in (10, 30):
            flipped.loc[in_2024, f"l1_y_{h}"] = 1 - flipped.loc[in_2024, f"l1_y_{h}"]
            flipped.loc[in_2024, f"l3_r_{h}"] = -flipped.loc[in_2024, f"l3_r_{h}"]
        a = run_job1(planted, 10, 0.1, holdout_from=HOLDOUT).oos
        b = run_job1(flipped, 10, 0.1, holdout_from=HOLDOUT).oos
        a24, b24 = a[a["test_year"] == 2024], b[b["test_year"] == 2024]
        assert np.allclose(a24["score"], b24["score"])

    def test_the_holdout_is_never_scored(self, planted):
        run = run_job1(planted, 30, 0.1, holdout_from=HOLDOUT)
        assert all(d < HOLDOUT for d in run.oos["date"])

    def test_hand_rule_keeps_what_it_says(self, planted):
        run = run_hand_rule(planted, 10, holdout_from=HOLDOUT)
        judged = planted.set_index(["date", "ticker"])
        for row in run.oos.head(50).itertuples():
            src = judged.loc[(row.date.isoformat(), row.ticker)]
            src = src.iloc[0] if isinstance(src, pd.DataFrame) else src
            assert row.kept == (src["weekly_agree"] == 1 and src["rs_pct"] >= 0.5)


class TestJob2:
    def test_ranks_by_the_planted_signal(self, planted):
        run = run_job2(planted, 10, 0.1, holdout_from=HOLDOUT)
        s = summarise_score(run.oos)
        assert s.auc > 0.75 and s.auc_ci[0] > 0.5
        assert s.top10 > s.base_rate
        assert s.auc_rs_pct > 0.75  # the baseline sees it too — it is the signal


class TestHelpers:
    def test_method_weights_cap_a_dominant_method(self):
        methods = np.array(["a"] * 80 + ["b"] * 20)
        w = method_weights(methods)
        share_a = w[methods == "a"].sum() / w.sum()
        assert share_a == pytest.approx(0.5)
        assert (method_weights(np.array(["a"] * 10)) == 1).all()

    def test_keep_rate_picks_the_best_inner_result(self):
        scores = np.linspace(0, 1, 200)
        r = np.where(scores > 0.6, 1.0, -1.0)  # only the top 40% pay
        keep, cut, how = choose_keep_rate(scores, r, np.ones(200, dtype=bool))
        assert keep == pytest.approx(0.3) or keep == pytest.approx(0.4)
        assert how == "best inner-year R" and cut > 0.55

    def test_keep_rate_needs_enough_inner_firings(self):
        few = MIN_KEPT_INNER  # 30% of these is under the minimum
        keep, _, how = choose_keep_rate(np.linspace(0, 1, few), np.ones(few),
                                        np.ones(few, dtype=bool))
        assert keep >= 0.7 or how.startswith("default")
