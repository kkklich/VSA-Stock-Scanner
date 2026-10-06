"""The AI layer's research bench (roadmap #31, ``agent/AI-ALGORITHMS-PLAN.md``).

Phase 0 of the plan: the honest test bench that every later model is judged
on — point-in-time features (``features``), labels (``labels``), walk-forward
validation and overfitting statistics (``validation``), dataset assembly
(``dataset``) and the trial register (``trials``). Phase 1 added the first
model (``models.logistic``, ``phase1``).

**Nothing in the running app imports this package** — no endpoint, no job, no
cache. It is used only by the offline scripts in ``backend-python/scripts/``
(``ml_*.py``). Since 2026-09-26 those run **on the server**, in their own
capped container (``docker-compose.prod.yml`` service ``ml``, started with
``deploy/ml-run.sh``) — decision D6. ``tests/test_ml_isolation.py`` pins that
importing ``app.main`` never loads this package, so the app with it present is
exactly the app without it (the plan's "off" guarantee, §14.3).

**Where files go.** On a laptop, datasets go to ``backend-python/ml_data/`` and
reports plus the trial register to ``agent/ml/`` (the documentation folder).
On the server there is no documentation folder, so ``STOCKPILOT_ML_DIR`` names
one folder for everything — ``/app/ml`` in the container, bind-mounted to
``~/stockpilot/ml`` on the VPS, where it survives rebuilds and deploys:

    <STOCKPILOT_ML_DIR>/data/      datasets and back-fill progress
    <STOCKPILOT_ML_DIR>/reports/   the reports
    <STOCKPILOT_ML_DIR>/trials.csv the trial register
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bumped whenever a feature's definition changes; stamped into every dataset.
FEATURES_VERSION = "v1"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

_ML_DIR = os.environ.get("STOCKPILOT_ML_DIR", "").strip()

#: Datasets and back-fill progress (local and gitignored, or the server folder).
ML_DATA_DIR = Path(_ML_DIR) / "data" if _ML_DIR else BACKEND_DIR / "ml_data"
#: Reports, the trial register — ``agent/ml`` locally, the server folder there.
AGENT_ML_DIR = Path(_ML_DIR) if _ML_DIR else REPO_ROOT / "agent" / "ml"

__all__ = ["AGENT_ML_DIR", "BACKEND_DIR", "FEATURES_VERSION", "ML_DATA_DIR", "REPO_ROOT"]
