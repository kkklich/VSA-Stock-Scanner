"""Contracts for the long-term Quality / Value / Momentum ranking."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.models.fundamentals import FundamentalAssessment
from app.models.stocks import _CamelModel

MODEL_VERSION = "qvm-v1"


class LongTermItem(_CamelModel):
    ticker: str
    name: str
    sector: str | None = None
    market: str
    currency: str
    as_of: date | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    value_score: float | None = Field(default=None, ge=0, le=100)
    momentum_score: float | None = Field(default=None, ge=0, le=100)
    # Share of the six raw inputs available, not a probability or confidence.
    coverage: float = Field(default=0, ge=0, le=100)
    eligible: bool = False
    missing: list[str] = Field(default_factory=list)
    inputs: dict[str, float | None] = Field(default_factory=dict)
    fundamentals_observed_at: datetime | None = None
    # Financial comparisons can fall back separately for each input. Momentum
    # always compares within a market and does not affect this label.
    comparison_group: Literal["market", "sector", "mixed"] = "market"
    # Smallest reference cohort used; includes the company itself.
    peer_count: int = 0
    fundamental_analysis: FundamentalAssessment | None = None


class LongTermRankingResponse(_CamelModel):
    market: str
    as_of: date | None = None
    model_version: str = MODEL_VERSION
    db_enabled: bool
    items: list[LongTermItem] = Field(default_factory=list)
    total_count: int = 0
    scored_count: int = 0


class LongTermHistoryResponse(_CamelModel):
    ticker: str
    db_enabled: bool
    items: list[dict[str, Any]]


class FinancialHistoryResponse(_CamelModel):
    ticker: str
    db_enabled: bool
    items: list[dict[str, Any]]
