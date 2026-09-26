"""The running app never loads the AI bench (plan §14.3, "off is byte-identical").

Phase 0 ships research code only. Importing the app must not import
``app.ml`` — so the app with the package present behaves exactly as the app
without it, and a broken ML dependency can never stop the backend starting.
Checked in a fresh interpreter, because other tests import ``app.ml``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_importing_the_app_does_not_import_the_ml_package():
    code = (
        "import sys; import app.main; "
        "print(sorted(m for m in sys.modules if m == 'app.ml' or m.startswith('app.ml.')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=180,
        env={**__import__("os").environ, "STOCKPILOT_DATABASE_URL": ""},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "[]"
