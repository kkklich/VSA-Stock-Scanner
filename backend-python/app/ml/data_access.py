"""Reading the stored bars the AI bench works on — for the offline scripts only.

The scripts run against the app's own PostgreSQL (on the server since
2026-09-26, decision D6). Reading never writes and never downloads: a company
with no stored bars is simply left out — the back-fill script is the only ML
tool that fetches anything, and only when it is run by hand.

**One stock at a time.** ``stream_stock_inputs`` hands out companies one by
one, so a job holds a single stock's bars in memory rather than a whole
market's: the stored bars of the GPW alone take ~330 MB as Python objects
today, and several times that after a back-fill — next to the live site on a
small server, that difference is the job.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator, Sequence
from datetime import date

from app.config import settings
from app.db.base import DB_SCAN_CONCURRENCY, build_engine, build_session_factory
from app.db.repository import PostgresQuoteRepository
from app.markets import MARKETS, quote_currency
from app.ml.dataset import StockInput
from app.models import GpwCompany
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


def companies_for(markets: Sequence[str], tickers: Sequence[str] | None = None) -> list[GpwCompany]:
    """Every tracked company of ``markets`` (optionally only ``tickers``)."""
    service = GpwCompanyService()
    companies = [c for m in markets for c in service.get_companies(m)]
    if tickers is not None:
        wanted = {t.lower() for t in tickers}
        companies = [c for c in companies if c.ticker in wanted]
    return companies


def _stock_input(company: GpwCompany, bars) -> StockInput:
    return StockInput(
        ticker=company.ticker,
        market=company.market,
        currency=quote_currency(company),
        sector=company.sector,
        bars=bars,
    )


def stream_stock_inputs(
    markets: Sequence[str],
    since: date | None = None,
    tickers: Sequence[str] | None = None,
    *,
    repo=None,
) -> Iterator[StockInput]:
    """Companies with stored bars, **one at a time**, oldest bar first.

    ``since`` limits how far back the bars go (default: everything stored);
    ``tickers`` restricts to a subset. ``repo`` replaces the database (tests
    pass an in-memory one). The generator owns its own event loop, so plain
    synchronous code can consume it.
    """
    companies = companies_for(markets, tickers)
    loop = asyncio.new_event_loop()
    engine = None
    try:
        if repo is None:
            if not settings.database_url:
                raise RuntimeError("No database configured (STOCKPILOT_DATABASE_URL).")
            engine = build_engine(settings.database_url)
            repo = PostgresQuoteRepository(build_session_factory(engine))
        for company in companies:
            bars = loop.run_until_complete(repo.get_quotes(company.ticker, since or EARLIEST, None))
            if bars:
                yield _stock_input(company, bars)
    finally:
        if engine is not None:
            loop.run_until_complete(engine.dispose())
        loop.close()


async def load_stock_inputs(
    markets: Sequence[str],
    since: date | None = None,
    tickers: Sequence[str] | None = None,
) -> list[StockInput]:
    """Every company of ``markets`` with its bars, **all at once**.

    Only for small sets (a handful of tickers, tests). Whole markets go through
    ``stream_stock_inputs``.
    """
    if not settings.database_url:
        raise RuntimeError("No database configured (STOCKPILOT_DATABASE_URL).")
    companies = companies_for(markets, tickers)
    engine = build_engine(settings.database_url)
    try:
        repo = PostgresQuoteRepository(build_session_factory(engine))
        gate = asyncio.Semaphore(DB_SCAN_CONCURRENCY)

        async def one(company: GpwCompany) -> StockInput | None:
            async with gate:
                bars = await repo.get_quotes(company.ticker, since or EARLIEST, None)
            return _stock_input(company, bars) if bars else None

        loaded = await asyncio.gather(*(one(c) for c in companies))
    finally:
        await engine.dispose()
    return [s for s in loaded if s is not None]


def peak_memory_mb() -> float | None:
    """This process's peak memory so far, in MB (``None`` where unknown).

    Printed by the scripts so a run on the server says how close it came to
    the ML container's memory cap.
    """
    try:
        import resource  # Linux / macOS

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / 1024 if sys.platform != "darwin" else peak / 2**20
    except ImportError:
        pass
    try:  # Windows
        import ctypes
        import ctypes.wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(_Counters),
            ctypes.wintypes.DWORD,
        ]
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        me = kernel.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(me, ctypes.byref(counters), counters.cb):
            return counters.PeakWorkingSetSize / 2**20
    except (OSError, AttributeError):
        pass
    return None
