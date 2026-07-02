"""Pydantic models describing the API contract (see agent/DOCUMENTATION.md §5)."""

from app.models.stocks import (
    CandleBar,
    CompanyFundamentalsResponse,
    FinancialMetrics,
    GpwCompany,
    QuarterlyReport,
    SignalEffectiveness,
    StockHistoryResponse,
    StockRankingItem,
    StockSignalsResponse,
    StooqDailyQuote,
    VsaSignalResponse,
)

__all__ = [
    "CandleBar",
    "CompanyFundamentalsResponse",
    "FinancialMetrics",
    "GpwCompany",
    "QuarterlyReport",
    "SignalEffectiveness",
    "StockHistoryResponse",
    "StockRankingItem",
    "StockSignalsResponse",
    "StooqDailyQuote",
    "VsaSignalResponse",
]
