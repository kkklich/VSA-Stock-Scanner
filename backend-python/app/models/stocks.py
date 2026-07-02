"""API models for the market-data endpoints.

These mirror the documented API contract (agent/DOCUMENTATION.md §5). Field names
follow Python conventions (snake_case); camelCase aliases are generated automatically
so JSON responses match the TypeScript frontend's expectations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


# ── Shared helpers ────────────────────────────────────────────────────────────

class _CamelModel(BaseModel):
    """Base that serialises field names to camelCase for the frontend."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


# ── Existing models (unchanged contract) ─────────────────────────────────────

class GpwCompany(BaseModel):
    """A company listed on the Warsaw Stock Exchange (GPW)."""

    model_config = ConfigDict(frozen=True)

    # Stooq ticker symbol (always lower-case), e.g. "kgh".
    ticker: str
    name: str
    sector: str | None = None
    # Enriched metadata — populated from company-details.json when available.
    description: str | None = None
    industry: str | None = None
    employees: int | None = None
    website: str | None = None
    country: str | None = None


class StooqDailyQuote(BaseModel):
    """One end-of-day (EOD) OHLCV bar for a ticker, as returned by stooq.pl."""

    model_config = ConfigDict(frozen=True)

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class StockHistoryResponse(BaseModel):
    """Response payload for ``GET /api/stocks/{ticker}/history``."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str | None = None
    quotes: list[StooqDailyQuote]


# ── New models: ranking endpoint ──────────────────────────────────────────────

class StockRankingItem(_CamelModel):
    """One row in the ranking / watchlist feed (``GET /api/stocks/ranking``)."""

    ticker: str
    name: str
    # Last EOD closing price in PLN.
    last_price: float
    # Day-over-day price change, percent.
    price_change_pct: float
    # Computed VSA rating 0–100.
    current_rating: int
    # Day-over-day rating change.
    rating_change: int
    # Verdict derived from the most recent VSA signal.
    last_signal: str
    # Sessions since the most recent signal fired.
    days_since_signal: int
    # Last 10 closing prices (used by the sparkline component).
    sparkline: list[float]
    # 20-session median volume (shares).
    volume: int
    # Sector from the GPW company list.
    sector: str | None = None


# ── New models: signals endpoint ──────────────────────────────────────────────

class CandleBar(_CamelModel):
    """One OHLCV bar in the chart history (``GET /api/stocks/{ticker}/signals``)."""

    # The frontend expects the key "time", not "date", for TradingView compatibility.
    time: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class VsaSignalResponse(_CamelModel):
    """A detected VSA pattern marker for the chart overlay."""

    date: date
    # e.g. "Spring", "SOS", "Upthrust" — the display label on the chart.
    signal_name: str
    type: Literal["Bullish", "Bearish"]


class StockSignalsResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/signals``."""

    ticker: str
    name: str | None = None
    sector: str | None = None
    last_price: float
    price_change_pct: float
    current_rating: int
    rating_change: int
    # Full OHLCV history for the requested window.
    history: list[CandleBar]
    # Detected VSA patterns within the same window.
    vsa_signals: list[VsaSignalResponse]


# ── New models: fundamentals endpoint ─────────────────────────────────────────


class FinancialMetrics(_CamelModel):
    """Current financial ratios for a stock (refreshed daily)."""

    updated_at: str | None = None
    market_cap: int | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    total_revenue: int | None = None
    net_income: int | None = None
    shares_outstanding: int | None = None


class QuarterlyReport(_CamelModel):
    """One quarter of income-statement data."""

    period_end: str
    total_revenue: int | None = None
    net_income: int | None = None
    operating_income: int | None = None
    eps: float | None = None


class CompanyFundamentalsResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/fundamentals``."""

    ticker: str
    name: str | None = None
    sector: str | None = None
    description: str | None = None
    industry: str | None = None
    employees: int | None = None
    website: str | None = None
    country: str | None = None
    metrics: FinancialMetrics | None = None
    quarterly_reports: list[QuarterlyReport] = []


# ── New models: scanner stats endpoint ───────────────────────────────────────


class SignalEffectiveness(_CamelModel):
    """Back-test result for one VSA signal type (``GET /api/stocks/scanner/stats``)."""

    # Display name, e.g. "Spring", "Sign of Strength".
    signal: str
    # Total evaluable occurrences across all tracked stocks in the last 120 sessions.
    count: int
    # Percentage where price moved in the expected direction over the next 10 sessions.
    success_pct: float
    # Average winner magnitude ÷ average loser magnitude (0 if insufficient data).
    reward_risk: float
    # Number of stocks whose last detected signal is this type right now.
    active_count: int
