"""Session-wide pytest configuration.

Sets STOCKPILOT_DATABASE_URL to "" before any app module is imported so
that the FastAPI lifespan skips the DB / scheduler block entirely.
Tests that need persistence use InMemoryQuoteRepository directly.
"""

import os

# Must be set before app.config is imported (i.e. before test files are collected).
os.environ["STOCKPILOT_DATABASE_URL"] = ""

# The action log would otherwise write a real logs/actions.jsonl next to the
# backend on every test run. The middleware still runs (and its in-memory
# buffer is still exercised) — only the file is off. tests/test_action_log.py
# turns it back on against a tmp_path.
os.environ.setdefault("STOCKPILOT_ACTION_LOG_TO_FILE", "false")
