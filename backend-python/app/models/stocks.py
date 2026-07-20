"""API models for the market-data endpoints.

These mirror the documented API contract (agent/DOCUMENTATION.md §5). Field names
follow Python conventions (snake_case); camelCase aliases are generated automatically
so JSON responses match the TypeScript frontend's expectations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
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
    # Market capitalisation in PLN — feeds the ranking pre-filter (> 100M PLN).
    market_cap: int | None = None


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
    # Confidence (0–100) of the built-in AI-insight engine's verdict.
    ai_confidence: int = 0


# ── New models: sector heatmap endpoint ───────────────────────────────────────

class HeatmapItem(_CamelModel):
    """One tile in the sector heatmap (``GET /api/stocks/heatmap``).

    Percentage changes are ``None`` when the stored history is too short to
    compute them (e.g. a recently listed company has no bar from a year ago).
    """

    ticker: str
    name: str
    sector: str | None = None
    # Market capitalisation in PLN (tile size); None when not known.
    market_cap: int | None = None
    # Last EOD closing price in PLN.
    last_price: float
    # Computed VSA rating 0–100 (tile colour in the default view).
    current_rating: int
    # Verdict derived from the most recent VSA signal (tooltip).
    last_signal: str
    # Close-to-close change over the last session, percent.
    change_1d: float | None = None
    # Change vs the close ~1 calendar month ago, percent.
    change_1m: float | None = None
    # Change vs the close ~1 year ago, percent.
    change_1y: float | None = None
    # Change vs the oldest stored bar (full stored history), percent.
    change_max: float | None = None


class HeatmapResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/heatmap``."""

    # Trading day of the newest bar across all tiles.
    as_of: date | None = None
    # Tiles sorted by market cap (largest first, unknown caps last).
    items: list[HeatmapItem] = []


# ── New models: volume-surge endpoint ─────────────────────────────────────────

class VolumeSurgeItem(_CamelModel):
    """One surging stock in ``GET /api/stocks/volume-surge``.

    "Surging" means the average volume of the last few sessions is well above
    the stock's own baseline average (multi-day relative volume, RVOL).
    """

    ticker: str
    name: str
    sector: str | None = None
    # Last EOD closing price in PLN.
    last_price: float
    # Average daily volume over the recent window (shares).
    recent_avg_volume: int
    # Average daily volume over the baseline window before it (shares).
    baseline_avg_volume: int
    # recent avg ÷ baseline avg — the multi-day relative volume. >= minRatio.
    volume_ratio: float
    # Latest single session's volume ÷ baseline avg (classic RVOL).
    last_day_ratio: float
    # Recent sessions whose volume individually beat the baseline average.
    days_above_baseline: int
    # Close-to-close price change across the recent window, percent — a rough
    # proxy for the price "result" of the volume "effort" (the full VSA
    # reading also weighs each bar's spread and close position).
    price_change_pct: float
    # Computed VSA rating 0–100 (same window/settings as the ranking).
    current_rating: int
    # Verdict derived from the most recent VSA signal.
    last_signal: str


class VolumeSurgeResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/volume-surge``."""

    # Trading day of the newest bar across the surging stocks.
    as_of: date | None = None
    # Echo of the screen parameters the results were computed with.
    recent_days: int
    baseline_days: int
    min_ratio: float
    # Stocks that passed the pre-filters and had enough history to score.
    scanned_count: int = 0
    # Surging stocks matching the screen, before pagination (the pager total).
    total_count: int = 0
    # One page of surging stocks (server-side sorted; default: ratio desc).
    items: list[VolumeSurgeItem] = []


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


# ── New models: VSA detection settings (Scanner page → engine) ───────────────


class VsaSignalSettings(_CamelModel):
    """Detection thresholds for one VSA signal, as sent by the Scanner page.

    All fields are optional — omitted values fall back to the signal's
    documented defaults. ``close_pos`` is a percentage (0–100) in the API for
    slider-friendliness; the engine converts it to a 0.0–1.0 fraction.
    """

    enabled: bool = True
    spread_mult: float | None = Field(default=None, ge=0.0, le=10.0)
    vol_mult: float | None = Field(default=None, ge=0.0, le=10.0)
    close_pos: float | None = Field(default=None, ge=0.0, le=100.0)
    lookback: int | None = Field(default=None, ge=5, le=60)


class VsaSettings(_CamelModel):
    """Full VSA engine configuration (``settings`` query parameter, JSON).

    Keys match the Scanner page rule ids. Missing signals keep their defaults.
    """

    spring: VsaSignalSettings | None = None
    sos: VsaSignalSettings | None = None
    test: VsaSignalSettings | None = None
    upthrust: VsaSignalSettings | None = None
    nodemand: VsaSignalSettings | None = None
    sow: VsaSignalSettings | None = None


# ── New models: AI analysis endpoint ─────────────────────────────────────────


class AiSignalAssessment(_CamelModel):
    """The insight engine's second opinion on one rule-detected VSA signal."""

    date: date
    # Signal display name, e.g. "Spring", "SOS".
    signal_name: str
    # Whether the chart context supports the signal.
    agreement: Literal["confirm", "reject", "uncertain"]
    # One-sentence justification in plain language.
    comment: str


class AiAnalysisResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/ai-analysis``.

    Produced locally by ``app/analysis/ai_insight.py`` from the same OHLCV
    history and rule-detected signals the charts use — an interpretive layer
    on top of the rule engine, never a replacement for it. No external
    services involved.
    """

    ticker: str
    # Trading day of the last bar the analysis is based on.
    as_of: date
    # The engine's overall read of the chart.
    verdict: Literal["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
    # How confident the engine is in its verdict, 0–100.
    confidence: int = Field(ge=0, le=100)
    # Plain-language narrative of what the price/volume action shows.
    summary: str
    # Per-signal agreement with the rule engine (recent signals only).
    signal_assessments: list[AiSignalAssessment] = []
    # Short bullet observations (trend, volume behaviour, support/resistance).
    key_observations: list[str] = []
    # Identifier of the built-in engine that produced the analysis.
    engine: str


# ── New models: trust-score endpoint ─────────────────────────────────────────


class TrustScoreEvent(_CamelModel):
    """One back-tested historical strong signal (a "paper trade")."""

    date: date
    # Signal display name, e.g. "Spring", "SOS".
    signal_name: str
    # The verdict the signal mapped to when it fired.
    verdict: Literal["Strong Buy", "Strong Sell"]
    # Actual close-to-close move over the sessions after the signal, percent.
    forward_return_pct: float
    # The stock's typical (median) move over the same horizon, percent.
    baseline_return_pct: float
    # Edge vs. the baseline in the signal's direction, percentage points
    # (positive = the signal was a better entry than a random day).
    excess_return_pct: float
    # True when the signal beat the baseline in its direction.
    good_entry: bool


class TrustScoreResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/trust-score``.

    A prediction-accuracy score for the VSA engine on this particular stock:
    every historical Strong Buy / Strong Sell signal old enough to judge is
    back-tested (forward return vs. the stock's own baseline) and the results
    are folded into a single 0–100 trust score. Computed locally by
    ``app/analysis/trust_score.py``; deterministic, no external services.
    """

    ticker: str
    # Trading day of the last bar the back-test is based on.
    as_of: date
    # 0–100 trust score; None when no strong signal is old enough to judge.
    score: int | None = Field(default=None, ge=0, le=100)
    # Qualitative bucket for the score (drives the badge label/colour).
    grade: Literal["high", "medium", "low", "insufficient"]
    # Sessions a paper entry is held before it is judged.
    horizon_sessions: int
    # Strong signals with enough forward data to judge / of those, good entries.
    evaluated_count: int
    good_count: int
    # Strong signals too recent to judge yet (fewer forward sessions than the horizon).
    fresh_count: int
    # Per-direction breakdown of the evaluated signals.
    buy_evaluated: int
    buy_good: int
    sell_evaluated: int
    sell_good: int
    # The stock's median forward return over the horizon, percent.
    baseline_return_pct: float | None = None
    # Mean edge vs. baseline across the evaluated signals, percentage points.
    avg_excess_return_pct: float | None = None
    # Plain-language explanation of the track record.
    summary: str
    # Back-tested strong signals, newest first (capped; counts cover all).
    events: list[TrustScoreEvent] = []
    # Identifier of the built-in engine that produced the score.
    engine: str


# ── New models: rating history + refresh endpoints ───────────────────────────


class RatingPoint(_CamelModel):
    """One stored VSA rating snapshot (one per ticker per trading day)."""

    date: date
    # VSA rating 0–100, computed with the DEFAULT engine settings so points
    # from different days are comparable.
    rating: int = Field(ge=0, le=100)
    # Verdict badge on that day, e.g. "Strong Buy" / "Hold".
    verdict: str
    # Closing price that day (PLN); lets the UI plot rating vs price.
    close: float | None = None


class RatingHistoryResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/rating-history``."""

    ticker: str
    name: str | None = None
    # Chronological (oldest → newest) rating snapshots.
    points: list[RatingPoint] = []
    # "db" when served from stored snapshots, "computed" when derived
    # on-the-fly (no database configured / no snapshots yet).
    source: Literal["db", "computed"] = "db"


class RefreshStatusResponse(_CamelModel):
    """Status of the data-refresh pipeline (``/api/stocks/refresh``)."""

    # "running" while a refresh (ingest + ranking + snapshots) is in flight.
    state: Literal["idle", "running"]
    # When the last refresh started / successfully finished (ISO datetimes).
    last_started_at: str | None = None
    last_refresh_at: str | None = None
    # Error message of the last failed run, if any.
    last_error: str | None = None
    # How many stocks passed the pre-filters in the last completed run.
    stocks_ranked: int | None = None
    # False when the app runs without PostgreSQL — ratings are then
    # recalculated but not stored, so no history accumulates.
    db_enabled: bool = False


# ── New models: scanner stats endpoint ───────────────────────────────────────


class SignalEffectiveness(_CamelModel):
    """Back-test result for one VSA signal type (``GET /api/stocks/scanner/stats``)."""

    # Display name, e.g. "Spring", "Sign of Strength".
    signal: str
    # Total evaluable occurrences across all tracked stocks in the last 120 sessions.
    count: int
    # Percentage where the forward return beat the stock's own baseline in the
    # signal's direction over the next 10 sessions.
    success_pct: float
    # Average winner magnitude ÷ average loser magnitude, both measured as
    # excess over the baseline. Null when the ratio is undefined: no judged
    # occurrences, or wins but no losses.
    reward_risk: float | None
    # Number of stocks whose last detected signal is this type right now.
    active_count: int
