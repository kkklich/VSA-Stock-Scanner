"""Loads and caches the tracked company lists — the GPW and every other market.

The GPW list lives in ``app/data/gpw-companies.json``, with enriched metadata
(descriptions, industry details, employee counts, websites) merged in from
``app/data/company-details.json`` when present.

Every other market has one self-contained file, ``app/data/markets/<id>.json``
(``us.json``, ``de.json`` …), written by ``scripts/build_market_universe.py``::

    {"market": "us", "generatedAt": "…", "companies": [{"ticker": "aapl.us", …}]}

A market without a file simply has no companies, so the app runs unchanged
before those lists exist. All files are read once on first use and cached for
the lifetime of the process.

**What callers see.** ``get_companies()`` answers for one market at a time and
defaults to the GPW, which is what every screen asked for before other markets
existed. ``find()`` looks a ticker up across the markets this deployment has
switched on (``STOCKPILOT_MARKETS``) and nowhere else, so a stock from a
market that is still off stays invisible to visitors.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.markets import GPW, GPW_ID, MARKETS, enabled_markets, market_of, normalize_ticker
from app.models import GpwCompany

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_COMPANIES_FILE = _DATA_DIR / "gpw-companies.json"
_DEFAULT_DETAILS_FILE = _DATA_DIR / "company-details.json"
_DEFAULT_MARKETS_DIR = _DATA_DIR / "markets"


class GpwCompanyService:
    """Provides the companies the scanner tracks, market by market."""

    def __init__(
        self,
        companies_file: Path | None = None,
        details_file: Path | None = None,
        markets_dir: Path | None = None,
    ) -> None:
        self._companies_file = companies_file or _DEFAULT_COMPANIES_FILE
        self._details_file = details_file or _DEFAULT_DETAILS_FILE
        self._markets_dir = markets_dir or _DEFAULT_MARKETS_DIR
        self._lock = threading.Lock()
        self._by_market: dict[str, list[GpwCompany]] | None = None
        self._by_ticker: dict[str, GpwCompany] = {}

    def get_companies(self, market: str = GPW_ID) -> list[GpwCompany]:
        """Every tracked company on one market (the GPW unless another is named).

        Answers whether or not that market is switched on — callers that serve
        visitors check ``app.markets.is_enabled`` first. An unknown market id
        has no companies.
        """
        return self._load().get(market, [])

    def enabled_companies(self) -> list[GpwCompany]:
        """Every tracked company on the markets this deployment serves."""
        by_market = self._load()
        return [c for m in enabled_markets() for c in by_market.get(m.id, [])]

    def find(self, ticker: str) -> GpwCompany | None:
        """Find a company by its ticker (case-insensitive), or ``None``.

        Only markets that are switched on are searched.
        """
        normalized = normalize_ticker(ticker)
        if normalized is None:
            return None
        self._load()
        company = self._by_ticker.get(normalized)
        if company is None or all(m.id != company.market for m in enabled_markets()):
            return None
        return company

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, list[GpwCompany]]:
        if self._by_market is not None:
            return self._by_market

        with self._lock:
            if self._by_market is not None:
                return self._by_market

            by_market: dict[str, list[GpwCompany]] = {GPW_ID: self._load_gpw()}
            for market in MARKETS:
                if market.id != GPW_ID:
                    by_market[market.id] = self._load_market_file(market.id)

            self._by_ticker = {
                c.ticker.casefold(): c
                for companies in by_market.values()
                for c in companies
            }
            self._by_market = by_market
            return by_market

    def _load_gpw(self) -> list[GpwCompany]:
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
                    market_cap=extra.get("marketCap"),
                    market=GPW_ID,
                    exchange=GPW.exchange,
                    currency=GPW.currency,
                )
            )

        logger.info(
            "Loaded %d GPW companies (%d with enriched details) from %s.",
            len(companies),
            sum(1 for c in companies if c.description),
            self._companies_file,
        )
        return companies

    def _load_market_file(self, market_id: str) -> list[GpwCompany]:
        """One market's companies from ``markets/<id>.json`` (none if absent).

        A malformed file costs that market, never the app: the error is logged
        and the market comes back empty. A single bad entry — a ticker that is
        not valid, or belongs to a different market — is skipped on its own.
        """
        path = self._markets_dir / f"{market_id}.json"
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw["companies"] if isinstance(raw, dict) else raw
        except Exception:
            logger.exception("Could not read the %s company list at '%s'.", market_id, path)
            return []

        companies: list[GpwCompany] = []
        seen: set[str] = set()
        for item in items:
            ticker = normalize_ticker(item.get("ticker"))
            if ticker is None or market_of(ticker).id != market_id:
                logger.warning(
                    "Skipping %r in %s: not a %s ticker.", item.get("ticker"), path.name, market_id
                )
                continue
            if ticker in seen:
                logger.warning("Skipping duplicate %s in %s.", ticker, path.name)
                continue
            seen.add(ticker)
            try:
                companies.append(
                    GpwCompany(
                        ticker=ticker,
                        name=item.get("name") or ticker.upper(),
                        sector=item.get("sector"),
                        description=item.get("description"),
                        industry=item.get("industry"),
                        employees=item.get("employees"),
                        website=item.get("website"),
                        country=item.get("country"),
                        market_cap=item.get("marketCap"),
                        market=market_id,
                        exchange=item.get("exchange"),
                        currency=item.get("currency"),
                        indices=tuple(item.get("indices") or ()),
                    )
                )
            except Exception:
                logger.warning("Skipping malformed entry %s in %s.", ticker, path.name)

        logger.info("Loaded %d %s companies from %s.", len(companies), market_id, path)
        return companies
