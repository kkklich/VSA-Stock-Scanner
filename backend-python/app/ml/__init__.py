"""The AI layer's research bench (roadmap #31, ``agent/AI-ALGORITHMS-PLAN.md``).

Phase 0 of the plan: the honest test bench that every later model is judged
on — point-in-time features (``features``), labels (``labels``), walk-forward
validation and overfitting statistics (``validation``), dataset assembly
(``dataset``) and the trial register (``trials``).

**Nothing in the running app imports this package** — no endpoint, no job, no
cache. It is used only by the offline scripts in ``backend-python/scripts/``
(``ml_*.py``), which run on the owner's PC. ``tests/test_ml_isolation.py``
pins that importing ``app.main`` never loads it, so the app with this package
present is exactly the app without it (the plan's "off" guarantee, §14.3).
"""

from __future__ import annotations

from pathlib import Path

#: Bumped whenever a feature's definition changes; stamped into every dataset.
FEATURES_VERSION = "v1"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

#: Local, gitignored datasets and back-fill progress.
ML_DATA_DIR = BACKEND_DIR / "ml_data"
#: Research documentation: reports, the trial register, the research log.
AGENT_ML_DIR = REPO_ROOT / "agent" / "ml"

__all__ = ["AGENT_ML_DIR", "BACKEND_DIR", "FEATURES_VERSION", "ML_DATA_DIR", "REPO_ROOT"]
