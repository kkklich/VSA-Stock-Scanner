"""SQLAlchemy ORM models for persistent storage.

Tables:
  * ``companies``                  — static company metadata (ticker, name, sector)
  * ``daily_quotes``               — one row per (ticker, date) OHLCV bar
  * ``company_fundamentals``       — financial ratios snapshot (market cap, PE, EPS …)
  * ``company_quarterly_financials`` — quarterly income-statement history

VSA signals and ratings are NOT stored here; they are computed on-the-fly
from the raw OHLCV bars every request (and cached in-process).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Float, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompanyRow(Base):
    """One tracked GPW company."""

    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)


class DailyQuoteRow(Base):
    """One end-of-day OHLCV bar for a (ticker, date) pair.

    The composite UNIQUE constraint on (ticker, date) is the natural key;
    the surrogate ``id`` is kept for ORM convenience (e.g. bulk operations).
    """

    __tablename__ = "daily_quotes"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_daily_quote"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CompanyFundamentalsRow(Base):
    """Latest financial metrics snapshot for a company (one row per ticker).

    Refreshed during the daily ingest; values reflect the most recent
    close and the last published financial statement.
    """

    __tablename__ = "company_fundamentals"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_revenue: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_income: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    shares_outstanding: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class CompanyQuarterlyRow(Base):
    """One quarter of income-statement data (revenue + net income) per ticker.

    Populated during the daily ingest from Yahoo Finance
    ``quarterly_income_stmt``.  At most 8 quarters are kept per ticker.
    """

    __tablename__ = "company_quarterly_financials"
    __table_args__ = (UniqueConstraint("ticker", "period_end", name="uq_quarterly"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_revenue: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_income: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operating_income: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
