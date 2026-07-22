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

from datetime import UTC, date, datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    CompanyCashflowRow,
    CompanyFundamentalsRow,
    CompanyQuarterlyRow,
    CompanyRow,
    DailyQuoteRow,
    RatingSnapshotRow,
)
from app.models import (
    CashflowPeriod,
    CompanyFundamentalsResponse,
    FinancialMetrics,
    GpwCompany,
    QuarterlyReport,
    RatingPoint,
    StooqDailyQuote,
)

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

    async def upsert_cashflow(self, ticker: str, periods: list[CashflowPeriod]) -> None:
        """Insert or update cash-flow rows (capex, operating/free cash flow)."""
        ...

    async def get_cashflow(self, ticker: str) -> list[CashflowPeriod]:
        """Return every stored cash-flow period for one ticker, newest first."""
        ...

    async def get_all_cashflow(self) -> dict[str, list[CashflowPeriod]]:
        """Return the cash-flow periods of every ticker, keyed by ticker.

        One query for the whole universe — the capex screen needs all ~200
        companies at once, so a per-ticker round trip would be ~200 queries.
        """
        ...

    async def has_cashflow(self) -> bool:
        """True when at least one cash-flow row is stored, for any ticker.

        A pure existence probe: the daily ingest asks it to decide whether the
        capex tables still need their first fill. Reading the whole table (~290
        companies × up to 13 periods) just to test it for emptiness would be
        thousands of rows built into models and thrown away every evening.
        """
        ...

    async def get_all_revenue(self) -> dict[str, int]:
        """Return the stored trailing-12-month revenue per ticker.

        Only tickers whose revenue is known appear. Used as the denominator of
        the capex/revenue ratio on the capex screen.
        """
        ...

    async def upsert_rating_snapshots(self, ticker: str, points: list[RatingPoint]) -> None:
        """Insert or update daily VSA rating snapshots for a ticker."""
        ...

    async def get_rating_history(
        self,
        ticker: str,
        from_date: date,
        to_date: date | None = None,
    ) -> list[RatingPoint]:
        """Return stored rating snapshots for ``ticker`` in date order."""
        ...


# ── Shared row → model mapping ────────────────────────────────────────────────

def _cashflow_period(row: CompanyCashflowRow) -> CashflowPeriod:
    """Map one stored cash-flow row to its API model."""
    return CashflowPeriod(
        period_end=row.period_end.isoformat(),
        period_type=row.period_type,  # type: ignore[arg-type]  # constrained on write
        capex=row.capex,
        operating_cash_flow=row.operating_cash_flow,
        free_cash_flow=row.free_cash_flow,
        currency=row.currency,
    )


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

    # asyncpg caps a statement at 32,767 bind parameters; at 7 columns per row
    # that is ~4,600 rows, so multi-year backfills must be written in chunks.
    _QUOTE_CHUNK_ROWS = 2000

    async def upsert_quotes(self, ticker: str, quotes: list[StooqDailyQuote]) -> None:
        if not quotes:
            return
        async with self._sf() as session, session.begin():
            for start in range(0, len(quotes), self._QUOTE_CHUNK_ROWS):
                chunk = quotes[start : start + self._QUOTE_CHUNK_ROWS]
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
                    for q in chunk
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
        now = datetime.now(tz=UTC)
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
            "return_on_equity": metrics.return_on_equity,
            "return_on_assets": metrics.return_on_assets,
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

    async def upsert_cashflow(self, ticker: str, periods: list[CashflowPeriod]) -> None:
        if not periods:
            return
        rows = [
            {
                "ticker": ticker,
                "period_end": date.fromisoformat(p.period_end),
                "period_type": p.period_type,
                "capex": p.capex,
                "operating_cash_flow": p.operating_cash_flow,
                "free_cash_flow": p.free_cash_flow,
                "currency": p.currency,
            }
            for p in periods
        ]
        async with self._sf() as session, session.begin():
            stmt = pg_insert(CompanyCashflowRow).values(rows).on_conflict_do_update(
                constraint="uq_cashflow",
                set_={
                    "capex": pg_insert(CompanyCashflowRow).excluded.capex,
                    "operating_cash_flow": (
                        pg_insert(CompanyCashflowRow).excluded.operating_cash_flow
                    ),
                    "free_cash_flow": (
                        pg_insert(CompanyCashflowRow).excluded.free_cash_flow
                    ),
                    "currency": pg_insert(CompanyCashflowRow).excluded.currency,
                },
            )
            await session.execute(stmt)

    async def get_cashflow(self, ticker: str) -> list[CashflowPeriod]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(CompanyCashflowRow)
                    .where(CompanyCashflowRow.ticker == ticker)
                    .order_by(CompanyCashflowRow.period_end.desc())
                )
            ).scalars().all()
        return [_cashflow_period(row) for row in rows]

    async def get_all_cashflow(self) -> dict[str, list[CashflowPeriod]]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(CompanyCashflowRow).order_by(
                        CompanyCashflowRow.period_end.desc()
                    )
                )
            ).scalars().all()
        by_ticker: dict[str, list[CashflowPeriod]] = {}
        for row in rows:
            by_ticker.setdefault(row.ticker, []).append(_cashflow_period(row))
        return by_ticker

    async def has_cashflow(self) -> bool:
        async with self._sf() as session:
            stmt = select(CompanyCashflowRow.id).limit(1)
            return (await session.execute(stmt)).scalar() is not None

    async def get_all_revenue(self) -> dict[str, int]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(
                        CompanyFundamentalsRow.ticker,
                        CompanyFundamentalsRow.total_revenue,
                    ).where(CompanyFundamentalsRow.total_revenue.is_not(None))
                )
            ).all()
        return {ticker: revenue for ticker, revenue in rows}

    async def upsert_rating_snapshots(self, ticker: str, points: list[RatingPoint]) -> None:
        if not points:
            return
        rows = [
            {
                "ticker": ticker,
                "date": p.date,
                "rating": p.rating,
                "verdict": p.verdict,
                "close": p.close,
            }
            for p in points
        ]
        async with self._sf() as session, session.begin():
            stmt = pg_insert(RatingSnapshotRow).values(rows).on_conflict_do_update(
                constraint="uq_rating_snapshot",
                set_={
                    "rating": pg_insert(RatingSnapshotRow).excluded.rating,
                    "verdict": pg_insert(RatingSnapshotRow).excluded.verdict,
                    "close": pg_insert(RatingSnapshotRow).excluded.close,
                },
            )
            await session.execute(stmt)

    async def get_rating_history(
        self,
        ticker: str,
        from_date: date,
        to_date: date | None = None,
    ) -> list[RatingPoint]:
        async with self._sf() as session:
            stmt = (
                select(RatingSnapshotRow)
                .where(RatingSnapshotRow.ticker == ticker, RatingSnapshotRow.date >= from_date)
                .order_by(RatingSnapshotRow.date)
            )
            if to_date is not None:
                stmt = stmt.where(RatingSnapshotRow.date <= to_date)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                RatingPoint(
                    date=row.date,
                    rating=row.rating,
                    verdict=row.verdict,
                    close=float(row.close) if row.close is not None else None,
                )
                for row in rows
            ]

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
                return_on_equity=fund_row.return_on_equity,
                return_on_assets=fund_row.return_on_assets,
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
        self._cashflow: dict[str, list[CashflowPeriod]] = {}
        self._ratings: dict[str, dict[date, RatingPoint]] = {}

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

    async def upsert_cashflow(self, ticker: str, periods: list[CashflowPeriod]) -> None:
        # Same key as the DB's unique constraint, so a re-ingest replaces a
        # period instead of duplicating it.
        merged = {(p.period_end, p.period_type): p for p in self._cashflow.get(ticker, [])}
        for p in periods:
            merged[(p.period_end, p.period_type)] = p
        self._cashflow[ticker] = sorted(
            merged.values(), key=lambda p: p.period_end, reverse=True
        )

    async def get_cashflow(self, ticker: str) -> list[CashflowPeriod]:
        return list(self._cashflow.get(ticker, []))

    async def get_all_cashflow(self) -> dict[str, list[CashflowPeriod]]:
        return {t: list(rows) for t, rows in self._cashflow.items()}

    async def has_cashflow(self) -> bool:
        return any(self._cashflow.values())

    async def get_all_revenue(self) -> dict[str, int]:
        return {
            t: m.total_revenue
            for t, m in self._fundamentals.items()
            if m.total_revenue is not None
        }

    async def upsert_rating_snapshots(self, ticker: str, points: list[RatingPoint]) -> None:
        bucket = self._ratings.setdefault(ticker, {})
        for p in points:
            bucket[p.date] = p

    async def get_rating_history(
        self,
        ticker: str,
        from_date: date,
        to_date: date | None = None,
    ) -> list[RatingPoint]:
        rows = [
            p for p in self._ratings.get(ticker, {}).values()
            if p.date >= from_date and (to_date is None or p.date <= to_date)
        ]
        return sorted(rows, key=lambda p: p.date)

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
