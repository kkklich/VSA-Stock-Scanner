"""The trial register counts every evaluated variant and cannot lose a field."""

from __future__ import annotations

import csv

import pytest

from app.ml.trials import TRIAL_FIELDS, append_trial, ensure_register, trial_count


def test_new_register_has_a_header_and_no_trials(tmp_path):
    path = ensure_register(tmp_path / "trials.csv")
    with path.open(encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == list(TRIAL_FIELDS)
    assert trial_count(path) == 0


def test_trials_are_numbered_in_order(tmp_path):
    path = tmp_path / "trials.csv"
    assert append_trial({"model": "logistic", "horizon": 30}, path) == 1
    assert append_trial({"model": "lightgbm", "horizon": 30, "notes": None}, path) == 2
    assert trial_count(path) == 2
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["model"] for r in rows] == ["logistic", "lightgbm"]
    assert rows[1]["recorded_at"]


def test_an_unknown_field_is_refused(tmp_path):
    with pytest.raises(ValueError):
        append_trial({"modle": "typo"}, tmp_path / "trials.csv")
    assert trial_count(tmp_path / "trials.csv") == 0
