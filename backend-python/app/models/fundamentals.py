"""Transparent, versioned fundamental scores; never return probabilities."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.models.stocks import _CamelModel

FUNDAMENTAL_VERSION = "fundamentals-v1"


class FundamentalAssessment(_CamelModel):
    model_version: str = FUNDAMENTAL_VERSION
    profile: Literal["corporate", "bank", "insurance", "financial"] = "corporate"
    score: float | None = Field(default=None, ge=0, le=100)
    pillars: dict[str, float | None] = Field(default_factory=dict)
    inputs: dict[str, float | None] = Field(default_factory=dict)
    metric_scores: dict[str, float] = Field(default_factory=dict)
    coverage: float = Field(default=0, ge=0, le=100)
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_applicable: list[str] = Field(default_factory=list)
    comparison_group: Literal["market", "sector", "mixed"] = "market"
    peer_count: int = 0
    latest_period_end: date | None = None
    annual_period_end: date | None = None
