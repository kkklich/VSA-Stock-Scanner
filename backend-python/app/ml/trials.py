"""The trial register — plan §6.4 / §19.6.

Every model variant, feature set, threshold or horizon that is *evaluated*
is one row here, appended by code and never edited by hand. The number of rows
is the trial count the overfitting statistics are corrected with (the Deflated
Sharpe Ratio's hurdle rises with it), so a variant that was tried and quietly
dropped still counts against the one that is finally reported.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from app.ml import AGENT_ML_DIR

TRIALS_FILE = AGENT_ML_DIR / "trials.csv"

TRIAL_FIELDS: tuple[str, ...] = (
    "trial_id",
    "recorded_at",
    "phase",
    "job",
    "horizon",
    "label",
    "model",
    "params",
    "feature_set",
    "markets",
    "folds",
    "oos_precision_gain_pp",
    "oos_expectancy_r",
    "auc",
    "brier",
    "keep_rate",
    "notes",
)


def ensure_register(path: Path = TRIALS_FILE) -> Path:
    """Create the register with its header if it does not exist yet."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=TRIAL_FIELDS).writeheader()
    return path


def trial_count(path: Path = TRIALS_FILE) -> int:
    """How many trials have been recorded (0 when the register is new)."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def append_trial(row: dict[str, object], path: Path = TRIALS_FILE) -> int:
    """Record one evaluated variant; returns its trial number (1-based).

    Unknown keys are refused rather than silently dropped, so a typo cannot
    make a field disappear from the record.
    """
    unknown = set(row) - set(TRIAL_FIELDS)
    if unknown:
        raise ValueError(f"Unknown trial fields: {sorted(unknown)}")
    ensure_register(path)
    number = trial_count(path) + 1
    record = {field: "" for field in TRIAL_FIELDS}
    record.update({k: "" if v is None else v for k, v in row.items()})
    record["trial_id"] = number
    record["recorded_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=TRIAL_FIELDS).writerow(record)
    return number
