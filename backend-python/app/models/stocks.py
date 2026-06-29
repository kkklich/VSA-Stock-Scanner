"""API models for the market-data endpoints.

These mirror the .NET records (``GpwCompany``, ``StooqDailyQuote``,
``StockHistoryResponse``) so the JSON contract — and therefore the frontend —
stays identical across both backends.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class GpwCompany(BaseModel):
    """A company listed on the Warsaw Stock Exchange (GPW), as identified on stooq.pl."""

    model_config = ConfigDict(frozen=True)

    # Stooq ticker symbol (always lower-case, the form used in stooq.pl URLs), e.g. "kgh".
    ticker: str
    # Full company name, e.g. "KGHM Polska Miedź".
    name: str
    # Optional GPW sector / industry classification.
    sector: str | None = None


class StooqDailyQuote(BaseModel):
    """One end-of-day (EOD) OHLCV bar for a ticker, as returned by stooq.pl."""

    model_config = ConfigDict(frozen=True)

    # Session date (the trading day this bar belongs to). Serialized as YYYY-MM-DD.
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    # Number of shares traded during the session (0 when stooq leaves it blank).
    volume: int


class StockHistoryResponse(BaseModel):
    """Response payload for ``GET /api/stocks/{ticker}/history``."""

    model_config = ConfigDict(frozen=True)

    # Ticker the history belongs to (upper-case for display).
    ticker: str
    # Company name when the ticker is known in the GPW list; otherwise None.
    name: str | None = None
    # Chronological list of EOD OHLCV bars (oldest first).
    quotes: list[StooqDailyQuote]
