"""Session-wide pytest configuration.

Sets STOCKPILOT_DATABASE_URL to "" before any app module is imported so
that the FastAPI lifespan skips the DB / scheduler block entirely.
Tests that need persistence use InMemoryQuoteRepository directly.
"""

import os

# Must be set before app.config is imported (i.e. before test files are collected).
os.environ["STOCKPILOT_DATABASE_URL"] = ""
