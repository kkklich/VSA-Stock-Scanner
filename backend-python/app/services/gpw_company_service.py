"""Loads and caches the tracked GPW company list.

The canonical company list lives in ``app/data/gpw-companies.json``.
Enriched metadata (descriptions, industry details, employee counts, websites)
is loaded from ``app/data/company-details.json`` when present and merged in.

Both files are read once on first use and cached for the lifetime of the process.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.models import GpwCompany

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_COMPANIES_FILE = _DATA_DIR / "gpw-companies.json"
_DEFAULT_DETAILS_FILE = _DATA_DIR / "company-details.json"


class GpwCompanyService:
    """Provides the list of GPW-listed companies the scanner tracks."""

    def __init__(
        self,
        companies_file: Path | None = None,
        details_file: Path | None = None,
    ) -> None:
        self._companies_file = companies_file or _DEFAULT_COMPANIES_FILE
        self._details_file = details_file or _DEFAULT_DETAILS_FILE
        self._lock = threading.Lock()
        self._companies: list[GpwCompany] | None = None

    def get_companies(self) -> list[GpwCompany]:
        """Return every tracked GPW company, loading from disk on first use."""
        if self._companies is not None:
            return self._companies

        with self._lock:
            if self._companies is not None:
                return self._companies

            if not self._companies_file.exists():
                raise FileNotFoundError(
                    f"GPW company list not found at '{self._companies_file}'."
                )

            raw = json.loads(self._companies_file.read_text(encoding="utf-8"))

            # Load enriched metadata if available and merge into each company.
            details: dict[str, dict] = {}
            if self._details_file.exists():
                try:
                    details = json.loads(self._details_file.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning(
                        "Could not load company details from '%s'; using base data only.",
                        self._details_file,
                    )

            companies = []
            for item in raw:
                ticker = item.get("ticker", "")
                extra = details.get(ticker, {})
                companies.append(
                    GpwCompany(
                        ticker=ticker,
                        name=item.get("name", ticker),
                        sector=item.get("sector"),
                        description=extra.get("description"),
                        industry=extra.get("industry"),
                        employees=extra.get("employees"),
                        website=extra.get("website"),
                        country=extra.get("country"),
                    )
                )

            self._companies = companies
            logger.info(
                "Loaded %d GPW companies (%d with enriched details) from %s.",
                len(self._companies),
                sum(1 for c in self._companies if c.description),
                self._companies_file,
            )
            return self._companies

    def find(self, ticker: str) -> GpwCompany | None:
        """Find a company by its ticker (case-insensitive), or ``None``."""
        if not ticker or not ticker.strip():
            return None
        needle = ticker.strip().casefold()
        return next(
            (c for c in self.get_companies() if c.ticker.casefold() == needle),
            None,
        )
