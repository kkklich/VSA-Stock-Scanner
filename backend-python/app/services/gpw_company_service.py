"""Loads and caches the tracked GPW company list.

stooq.pl does not expose a reliable, free "all GPW companies" endpoint, so the
canonical list is maintained as a seed JSON file (``app/data/gpw-companies.json``).
The list is read once and cached for the lifetime of the process; the daily
ingestion workflow can later replace or extend this source.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.models import GpwCompany

logger = logging.getLogger(__name__)

# The seed file lives next to this package, so it resolves regardless of the
# process working directory (dev, packaged, or Docker).
_DEFAULT_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "gpw-companies.json"


class GpwCompanyService:
    """Provides the list of GPW-listed companies the scanner tracks."""

    def __init__(self, data_file: Path | None = None) -> None:
        self._data_file = data_file or _DEFAULT_DATA_FILE
        self._lock = threading.Lock()
        self._companies: list[GpwCompany] | None = None

    def get_companies(self) -> list[GpwCompany]:
        """Return every tracked GPW company, loading from disk on first use."""
        if self._companies is not None:
            return self._companies

        with self._lock:
            # Double-check after acquiring the lock in case another caller loaded it first.
            if self._companies is not None:
                return self._companies

            if not self._data_file.exists():
                raise FileNotFoundError(f"GPW company list not found at '{self._data_file}'.")

            raw = json.loads(self._data_file.read_text(encoding="utf-8"))
            self._companies = [GpwCompany.model_validate(item) for item in raw]
            logger.info(
                "Loaded %d GPW companies from %s.", len(self._companies), self._data_file
            )
            return self._companies

    def find(self, ticker: str) -> GpwCompany | None:
        """Find a company by its stooq ticker (case-insensitive), or ``None``."""
        if not ticker or not ticker.strip():
            return None

        needle = ticker.strip().casefold()
        return next(
            (c for c in self.get_companies() if c.ticker.casefold() == needle),
            None,
        )
