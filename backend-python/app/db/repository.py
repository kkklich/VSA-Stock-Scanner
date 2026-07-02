"""Quote repository: abstract interface + PostgreSQL implementation.

The ``QuoteRepository`` Protocol defines the interface. Any class that
implements all four methods is a valid repository, regardless of inheritance.
This makes it trivial to:

  * swap the storage backend (e.g. SQLite for dev, TimescaleDB for prod)
  * inject an in-memory fake in unit tests without touching the app code

``PostgresQuoteRepository`` is the production implementation backed by
SQLAlchemy async + asyncpg.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import CompanyFundamentalsRow, CompanyQuarterlyRow, CompanyRow, DailyQuoteRow
from app.models import CompanyFundamentalsResponse, FinancialMetrics, GpwCompany, QuarterlyReport, StooqDailyQuote


# ── Abstract interface ────────────────────────────────────────────────────────

@runtime_checkable
class QuoteRepository(Protocol):
    """Protocol (structural interface) for the quote persistence layer."""

    async def upsert_companies(self, companies: list[GpwCompany]) -> None:
        """Insert or update company metadata rows."""
        ...

    async def upsert_quotes(self, ticker: str, quotes: list[StooqDailyQuote]) -> None:
        """Insert OHLCV bars; ignore rows that already exist (same date)."""
        ...

    async def get_quotes(
        self,
        ticker: str,
        from_date: date,
        to_date: date | None = None,
    ) -> list[StooqDailyQuote]:
        """Return OHLCV bars for ``ticker`` in [from_date, to_date], sorted by date."""
        ...

    async def has_today_data(self, ticker: str, as_of: date | None = None) -> bool:
        """Return True if there is at least one bar for ``ticker`` on ``as_of`` (default today)."""
        ...

    async def upsert_fundamentals(self, ticker: str, metrics: FinancialMetrics) -> None:
        """Insert or replace the financial metrics snapshot for a ticker."""
        ...

    async def upsert_quarterly(self, ticker: str, reports: list[QuarterlyReport]) -> None:
        """Insert or update quarterly income-statement rows for a ticker."""
        ...

    async def get_fundamentals(self, ticker: str) -> CompanyFundamentalsResponse | None:
        """Return the stored fundamentals for a ticker, or None if not yet ingested."""
        ...


# ── PostgreSQL implementation ─────────────────────────────────────────────────

class PostgresQuoteRepository:
    """Production repository backed by PostgreSQL (via SQLAlchemy async + asyncpg)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def upsert_companies(self, companies: list[GpwCompany]) -> None:
        if not companies:
            return
        async with self._sf() as session, session.begin():
            stmt = pg_insert(CompanyRow).values(
                [{"ticker": c.ticker, "name": c.name, "sector": c.sector} for c in companies]
            ).on_conflict_do_update(
                index_elements=["ticker"],
                set_={"name": pg_insert(CompanyRow).excluded.name,
                      "sector": pg_insert(CompanyRow).excluded.sector},
            )
            await session.execute(stmt)

    async def upsert_quotes(self, ticker: str, quotes: list[StooqDailyQuote]) -> None:
        if not quotes:
            return
        async with self._sf() as session, session.begin():
            stmt = pg_insert(DailyQuoteRow).values([
                {
                    "ticker": ticker,
                    "date": q.date,
                    "open": q.open,
                    "high": q.high,
                    "low": q.low,
                    "close": q.close,
                    "volume": q.volume,
                }
                for q in quotes
            ]).on_conflict_do_update(
                constraint="uq_daily_quote",
                set_={
                    "open": pg_insert(DailyQuoteRow).excluded.open,
                    "high": pg_insert(DailyQuoteRow).excluded.high,
                    "low": pg_insert(DailyQuoteRow).excluded.low,
                    "close": pg_insert(DailyQuoteRow).excluded.close,
                    "volume": pg_insert(DailyQuoteRow).excluded.volume,
                },
            )
            await session.execute(stmt)

    async def get_quotes(
        self,
        ticker: str,
        from_date: date,
        to_date: date | None = None,
    ) -> list[StooqDailyQuote]:
        async with self._sf() as session:
            stmt = (
                select(DailyQuoteRow)
                .where(DailyQuoteRow.ticker == ticker, DailyQuoteRow.date >= from_date)
                .order_by(DailyQuoteRow.date)
            )
            if to_date is not None:
                stmt = stmt.where(DailyQuoteRow.date <= to_date)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                StooqDailyQuote(
                    date=row.date,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                )
                for row in rows
            ]

    async def has_today_data(self, ticker: str, as_of: date | None = None) -> bool:
        effective = as_of or date.today()
        async with self._sf() as session:
            stmt = (
                select(DailyQuoteRow.id)
                .where(DailyQuoteRow.ticker == ticker, DailyQuoteRow.date == effective)
                .limit(1)
            )
            return (await session.execute(stmt)).scalar() is not None

    async def upsert_fundamentals(self, ticker: str, metrics: FinancialMetrics) -> None:
        now = datetime.now(tz=timezone.utc)
        values = {
            "ticker": ticker,
            "updated_at": now,
            "market_cap": metrics.market_cap,
            "pe_ratio": metrics.pe_ratio,
            "forward_pe": metrics.forward_pe,
            "eps": metrics.eps,
            "dividend_yield": metrics.dividend_yield,
            "total_revenue": metrics.total_revenue,
            "net_income": metrics.net_income,
            "shares_outstanding": metrics.shares_outstanding,
        }
        async with self._sf() as session, session.begin():
            stmt = pg_insert(CompanyFundamentalsRow).values([values]).on_conflict_do_update(
                index_elements=["ticker"],
                set_={k: v for k, v in values.items() if k != "ticker"},
            )
            await session.execute(stmt)

    async def upsert_quarterly(self, ticker: str, reports: list[QuarterlyReport]) -> None:
        if not reports:
            return
        rows = [
            {
                "ticker": ticker,
                "period_end": date.fromisoformat(r.period_end),
                "total_revenue": r.total_revenue,
                "net_income": r.net_income,
                "operating_income": r.operating_income,
                "eps": r.eps,
            }
            for r in reports
        ]
        async with self._sf() as session, session.begin():
            stmt = pg_insert(CompanyQuarterlyRow).values(rows).on_conflict_do_update(
                constraint="uq_quarterly",
                set_={
                    "total_revenue": pg_insert(CompanyQuarterlyRow).excluded.total_revenue,
                    "net_income": pg_insert(CompanyQuarterlyRow).excluded.net_income,
                    "operating_income": pg_insert(CompanyQuarterlyRow).excluded.operating_income,
                    "eps": pg_insert(CompanyQuarterlyRow).excluded.eps,
                },
            )
            await session.execute(stmt)

    async def get_fundamentals(self, ticker: str) -> CompanyFundamentalsResponse | None:
        async with self._sf() as session:
            fund_row = (
                await session.execute(
                    select(CompanyFundamentalsRow).where(CompanyFundamentalsRow.ticker == ticker)
                )
            ).scalar_one_or_none()

            q_rows = (
                await session.execute(
                    select(CompanyQuarterlyRow)
                    .where(CompanyQuarterlyRow.ticker == ticker)
                    .order_by(CompanyQuarterlyRow.period_end.desc())
                    .limit(8)
                )
            ).scalars().all()

        metrics = None
        if fund_row is not None:
            metrics = FinancialMetrics(
                updated_at=fund_row.updated_at.isoformat(),
                market_cap=fund_row.market_cap,
                pe_ratio=fund_row.pe_ratio,
                forward_pe=fund_row.forward_pe,
                eps=fund_row.eps,
                dividend_yield=fund_row.dividend_yield,
                total_revenue=fund_row.total_revenue,
                net_income=fund_row.net_income,
                shares_outstanding=fund_row.shares_outstanding,
            )

        quarterly = [
            QuarterlyReport(
                period_end=r.period_end.isoformat(),
                total_revenue=r.total_revenue,
                net_income=r.net_income,
                operating_income=r.operating_income,
                eps=r.eps,
            )
            for r in q_rows
        ]

        if metrics is None and not quarterly:
            return None

        return CompanyFundamentalsResponse(
            ticker=ticker.upper(),
            metrics=metrics,
            quarterly_reports=quarterly,
        )


# ── In-memory implementation (used in tests) ─────────────────────────────────

class InMemoryQuoteRepository:
    """Simple in-memory repository for unit tests. Not thread-safe."""

    def __init__(self) -> None:
        self._quotes: dict[str, dict[date, StooqDailyQuote]] = {}
        self._companies: list[GpwCompany] = []
        self._fundamentals: dict[str, FinancialMetrics] = {}
        self._quarterly: dict[str, list[QuarterlyReport]] = {}

    async def upsert_companies(self, companies: list[GpwCompany]) -> None:
        by_ticker = {c.ticker: c for c in self._companies}
        for c in companies:
            by_ticker[c.ticker] = c
        self._companies = list(by_ticker.values())

    async def upsert_quotes(self, ticker: str, quotes: list[StooqDailyQuote]) -> None:
        bucket = self._quotes.setdefault(ticker, {})
        for q in quotes:
            bucket[q.date] = q

    async def get_quotes(
        self,
        ticker: str,
        from_date: date,
        to_date: date | None = None,
    ) -> list[StooqDailyQuote]:
        rows = [
            q for q in self._quotes.get(ticker, {}).values()
            if q.date >= from_date and (to_date is None or q.date <= to_date)
        ]
        return sorted(rows, key=lambda q: q.date)

    async def has_today_data(self, ticker: str, as_of: date | None = None) -> bool:
        effective = as_of or date.today()
        return effective in self._quotes.get(ticker, {})

    async def upsert_fundamentals(self, ticker: str, metrics: FinancialMetrics) -> None:
        self._fundamentals[ticker] = metrics

    async def upsert_quarterly(self, ticker: str, reports: list[QuarterlyReport]) -> None:
        self._quarterly[ticker] = reports

    async def get_fundamentals(self, ticker: str) -> CompanyFundamentalsResponse | None:
        metrics = self._fundamentals.get(ticker)
        quarterly = self._quarterly.get(ticker, [])
        if metrics is None and not quarterly:
            return None
        return CompanyFundamentalsResponse(
            ticker=ticker.upper(),
            metrics=metrics,
            quarterly_reports=quarterly,
        )
