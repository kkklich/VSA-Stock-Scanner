"""Reading the stored bars the AI bench works on — for the offline scripts only.

The scripts run on the owner's PC against the app's own PostgreSQL. Reading
never writes and never downloads: a company with no stored bars is simply
left out (the back-fill script is the only ML tool that fetches anything, and
only when it is run by hand).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date

from app.config import settings
from app.db.base import DB_SCAN_CONCURRENCY, build_engine, build_session_factory
from app.db.repository import PostgresQuoteRepository
from app.markets import MARKETS, quote_currency
from app.ml.dataset import StockInput
from app.services.gpw_company_service import GpwCompanyService

#: Earlier than any stored bar — "everything we have".
EARLIEST = date(1990, 1, 1)


def parse_markets(raw: str) -> list[str]:
    """``"gpw"``, ``"gpw,us"`` or ``"all"`` → market ids, in registry order."""
    known = [m.id for m in MARKETS]
    if raw.strip().lower() == "all":
        return known
    wanted = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise ValueError(f"Unknown market(s) {unknown}; valid: {known} or 'all'.")
    return [m for m in known if m in wanted]


async def load_stock_inputs(
    markets: Sequence[str],
    since: date | None = None,
    tickers: Sequence[str] | None = None,
) -> list[StockInput]:
    """Every tracked company of ``markets`` that has stored bars, with them.

    ``since`` limits how far back the bars go (default: everything stored);
    ``tickers`` restricts to a subset (lower-case app tickers).
    """
    if not settings.database_url:
        raise RuntimeError("No database configured (STOCKPILOT_DATABASE_URL).")
    service = GpwCompanyService()
    companies = [c for m in markets for c in service.get_companies(m)]
    if tickers is not None:
        wanted = {t.lower() for t in tickers}
        companies = [c for c in companies if c.ticker in wanted]

    engine = build_engine(settings.database_url)
    try:
        repo = PostgresQuoteRepository(build_session_factory(engine))
        gate = asyncio.Semaphore(DB_SCAN_CONCURRENCY)

        async def one(company) -> StockInput | None:
            async with gate:
                bars = await repo.get_quotes(company.ticker, since or EARLIEST, None)
            if not bars:
                return None
            return StockInput(
                ticker=company.ticker,
                market=company.market,
                currency=quote_currency(company),
                sector=company.sector,
                bars=bars,
            )

        loaded = await asyncio.gather(*(one(c) for c in companies))
    finally:
        await engine.dispose()
    return [s for s in loaded if s is not None]
