"""SQLAlchemy ORM models for persistent storage.

Only two tables are needed:
  * ``companies``     — static company metadata (ticker, name, sector)
  * ``daily_quotes``  — one row per (ticker, date) OHLCV bar

VSA signals and ratings are NOT stored here; they are computed on-the-fly
from the raw OHLCV bars every request (and cached in-process).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Numeric, String, UniqueConstraint
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
