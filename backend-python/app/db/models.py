"""SQLAlchemy ORM models for persistent storage.

Tables:
  * ``companies``                  — static company metadata (ticker, name, sector)
  * ``daily_quotes``               — one row per (ticker, date) OHLCV bar
  * ``company_fundamentals``       — financial ratios snapshot (market cap, PE, EPS …)
  * ``company_quarterly_financials`` — quarterly income-statement history
  * ``company_cashflow``            — capex / operating cash flow per reported
                                     period (feeds the capex screen)
  * ``rating_snapshots``           — one VSA rating per (ticker, date), written by
                                     the refresh pipeline so the rating's evolution
                                     over time can be charted
  * ``action_logs``                — audit trail: one row per API call and per
                                     background job (what was done, when, how it
                                     ended)

Per-request VSA signals are still computed on-the-fly from the raw OHLCV bars
(and cached in-process); only the daily rating snapshot is persisted.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
    # Profitability ratios stored as fractions (0.184 = 18.4%), added
    # 2026-07-21. These are COLUMNS on an existing table, so unlike a new
    # table they do not appear via create_all — run `alembic upgrade head`.
    return_on_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_on_assets: Mapped[float | None] = mapped_column(Float, nullable=True)


class RatingSnapshotRow(Base):
    """One VSA rating snapshot for a (ticker, date) pair.

    Written by the refresh pipeline (nightly job or the manual Refresh button)
    using the DEFAULT engine settings, so the stored history is comparable
    across days regardless of the user's current Scanner configuration.
    """

    __tablename__ = "rating_snapshots"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_rating_snapshot"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # VSA rating 0–100 (default engine settings).
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    # Verdict badge derived from the most recent signal, e.g. "Strong Buy".
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    # Closing price on that day, for plotting rating vs price together.
    close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)


class CompanyCashflowRow(Base):
    """One reported period of cash-flow data per ticker (capex + cash flow).

    Populated during the daily ingest's fundamentals pass from Yahoo Finance
    (``cashflow`` = annual, ``quarterly_cashflow`` = quarterly). Both period
    types live in one table, distinguished by ``period_type``, because a
    company reports the same calendar date in both frames (Q4 end == year end).

    ``capex`` is stored as a POSITIVE "money spent" figure; Yahoo reports it as
    a negative cash outflow. ``currency`` is the statement's reporting currency
    — not always PLN, so it must never be assumed.
    """

    __tablename__ = "company_cashflow"
    __table_args__ = (
        UniqueConstraint("ticker", "period_end", "period_type", name="uq_cashflow"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    capex: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operating_cash_flow: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    free_cash_flow: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)


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


class ActionLogRow(Base):
    """One recorded action — an API call or a background job.

    Written by ``app/services/action_log.py`` (batched, off the request path).
    Rows older than ``STOCKPILOT_ACTION_LOG_RETENTION_DAYS`` are deleted by the
    log's own periodic prune, so the table cannot grow without bound.

    Deliberately denormalised and index-light: this table is written on every
    single request, so each extra index is a cost paid ~thousands of times a
    day to speed up an admin screen opened occasionally. ``started_at`` (the
    default ordering and the retention prune's predicate) and ``action`` (the
    natural grouping) are the two that earn their place.
    """

    __tablename__ = "action_logs"
    __table_args__ = (
        Index("ix_action_logs_started_at", "started_at"),
        Index("ix_action_logs_action", "action"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # When the action STARTED, in UTC. Stored timezone-aware so the Warsaw
    # local time in the JSON-lines file and this column can never drift apart.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Correlates a row with the X-Request-Id header the caller received, and a
    # job with the request that started it.
    request_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # "request" (an HTTP call) or "job" (refresh, ingest, scheduler).
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # The route template ("/api/stocks/{ticker}/signals") or the job name.
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    # ok | client_error | server_error | started | finished | failed | skipped.
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Sanitised: the `settings` blob is hashed and credential-like names masked.
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Job counters and error text. JSON so a new job can add its own numbers
    # without a migration.
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
