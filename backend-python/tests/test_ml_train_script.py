"""``scripts/ml_train.py`` end to end, on synthetic datasets in a temporary folder."""

from __future__ import annotations

import pytest

from app.ml.trials import trial_count
from scripts import ml_train
from tests.test_ml_phase1 import _frame


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    frame = _frame(signal=4.0, seed=3, per_day=1)
    for job in (1, 2):
        frame.to_csv(tmp_path / f"job{job}-gpw.csv.gz", index=False, compression="gzip")
    monkeypatch.setattr(ml_train, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ml_train, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(ml_train, "TRIALS_PATH", tmp_path / "trials.csv")
    # The synthetic firings end in 2025; freeze so the holdout starts after them.
    monkeypatch.setattr(ml_train, "FREEZE_DATE", ml_train.FREEZE_DATE)
    return tmp_path


def test_writes_the_report_and_records_every_variant(workspace):
    assert ml_train.main([]) == 0
    reports = list((workspace / "reports").glob("*-phase1-logistic.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "## 1. In plain words" in text and "## 5. Corrected for how much was tried" in text
    # 2 horizons × (hand rule + 3 C values) for Job 1, 2 × 3 for Job 2.
    assert trial_count(workspace / "trials.csv") == 14


def test_a_second_run_counts_again(workspace):
    ml_train.main([])
    ml_train.main([])
    assert trial_count(workspace / "trials.csv") == 28


def test_missing_datasets_record_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_train, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ml_train, "TRIALS_PATH", tmp_path / "trials.csv")
    assert ml_train.main([]) == 1
    assert trial_count(tmp_path / "trials.csv") == 0
