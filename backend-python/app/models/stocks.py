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


# ── New models: pluggable trading methods ────────────────────────────────────


class MethodResultModel(_CamelModel):
    """One trading method's read of one stock — a cell in the multi-method list.

    Produced by the framework in ``app/analysis/methods`` (VSA plus any
    registered method). ``score`` is a 0–100 attractiveness used by the
    combined cross-method ranking; ``days_since`` is how recently the method's
    entry setup last fired (999 = not in the evaluated window, the same
    sentinel the ranking uses elsewhere).
    """

    # Method id this result belongs to (e.g. "vsa", "minervini").
    method_id: str
    # 0–100 attractiveness for this method (feeds the combined score).
    score: int
    # Age in days of the most recent bar the setup fired on; 999 = not recently.
    days_since: int = 999
    # The setup fired on the most recent bar (== days_since 0).
    fired: bool = False
    # Short human note, e.g. the VSA verdict or "6/7 rules". Optional.
    detail: str | None = None
    # False when the stock has too little history to evaluate this method.
    available: bool = True


class TradingMethodInfo(_CamelModel):
    """Catalogue entry for one selectable trading method (``GET .../methods``)."""

    id: str
    name: str
    # Plain-language explainer shown in the UI.
    description: str
    # Evidence source (book / paper / verified track record).
    source: str
    source_url: str | None = None
    # "Bullish" — long-only setups for now.
    direction: str = "Bullish"


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
    # 52-week context. Explicit aliases because the automatic camelCase
    # generator renders "52w" as "52W" ("distFrom52WHighPct"), which reads
    # wrong and would not match the endpoint's query-parameter names.
    #
    # Distance of the last close from the 52-week high, percent (≤ 0;
    # 0 = closed exactly at the high). The extremes cover up to 52 weeks of
    # stored history before the last session — for a recently listed company
    # that is its whole trading history. None only when not computable.
    dist_from_52w_high_pct: float | None = Field(
        default=None, alias="distFrom52wHighPct"
    )
    # Distance of the last close above the 52-week low, percent (≥ 0).
    dist_from_52w_low_pct: float | None = Field(
        default=None, alias="distFrom52wLowPct"
    )
    # True when the newest session set a new 52-week extreme: its intraday
    # high (low) beat every bar of the preceding 52 weeks.
    is_new_52w_high: bool = Field(default=False, alias="isNew52wHigh")
    is_new_52w_low: bool = Field(default=False, alias="isNew52wLow")
    # Per-method results, keyed by method id (VSA plus every registered
    # trading method). Baked into the cached ranking, so selecting methods in
    # the UI is a cheap per-request pass — no recomputation.
    method_results: dict[str, MethodResultModel] = Field(default_factory=dict)
    # Mean of the SELECTED methods' scores, 0–100 — the combined cross-method
    # ranking. Set per request from the ``methods`` query parameter (None until
    # computed, and when the row can evaluate none of the selected methods).
    combined_score: int | None = None


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


class TickerVolumeResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/volume``.

    The single-stock version of the volume-surge screen: the same multi-day
    relative-volume (RVOL) reading, computed with the same defaults and the
    same ``compute_surge_metrics`` helper, so a stock's page and the
    ``/volume-surge`` scanner never disagree. All figures are ``None`` (and
    ``available`` is ``False``) when the stored history is shorter than the two
    windows combined.
    """

    ticker: str
    # Trading day of the last bar the reading is based on.
    as_of: date | None = None
    # Windows used: last ``recent_days`` sessions vs. the ``baseline_days``
    # sessions before them.
    recent_days: int
    baseline_days: int
    # False when there is too little history to compute the ratio.
    available: bool = True
    # Average daily volume over the recent / baseline windows (shares).
    recent_avg_volume: int | None = None
    baseline_avg_volume: int | None = None
    # recent avg ÷ baseline avg — the multi-day relative volume. 1.0 = normal.
    volume_ratio: float | None = None
    # Latest single session's volume ÷ baseline avg (classic single-day RVOL).
    last_day_ratio: float | None = None
    # How many of the recent sessions individually beat the baseline average.
    days_above_baseline: int | None = None
    # Close-to-close price change across the recent window, percent.
    price_change_pct: float | None = None
    # Latest session's raw volume (shares).
    last_volume: int | None = None


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


class MethodSignalItem(_CamelModel):
    """One bar where a trading method's setup fired — a chart overlay marker."""

    date: date
    # Short on-chart tag, e.g. "Spring", "Trend Template".
    label: str
    type: Literal["Bullish", "Bearish"]


class MethodSignalGroup(_CamelModel):
    """All chart-overlay markers for one trading method.

    Lets the stock chart draw a per-method layer (and the user toggle each
    method on/off). VSA's markers are NOT repeated here — they already ship in
    ``StockSignalsResponse.vsa_signals`` — so this carries the other registered
    methods (Minervini, …). A method with no firings in the window is still
    listed with an empty ``signals`` list, so the UI knows it exists.
    """

    method_id: str
    # Display name (column/legend label), e.g. "Minervini Trend Template".
    name: str
    # "Bullish" — long-only setups for now.
    direction: str = "Bullish"
    signals: list[MethodSignalItem] = []


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
    # Detected VSA patterns within the same window (the VSA method's overlay).
    vsa_signals: list[VsaSignalResponse]
    # Per-method chart overlays for every OTHER registered trading method
    # (Minervini, …); VSA stays in ``vsa_signals`` above. Additive — an older
    # client that ignores this field still gets the unchanged VSA chart.
    method_signals: list[MethodSignalGroup] = []


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
    # Profitability ratios as fractions from Yahoo (0.184 = 18.4%); the UI
    # renders them as percentages. Return on equity / on assets — how much
    # profit the company earns per zloty of shareholder capital / of assets.
    return_on_equity: float | None = None
    return_on_assets: float | None = None


class PriceReturns(_CamelModel):
    """Trailing price returns for a stock, percent.

    Computed from the stored EOD bars (``app/analysis/returns.py``), not from
    an external field, so the numbers always agree with the charts. A horizon
    is ``None`` when the stored history does not reach back that far. These
    ignore dividends — they are price returns, not total returns.
    """

    ytd_pct: float | None = None
    # Field names carry the "1y"/"3y"/"5y" horizon; explicit aliases because
    # the camelCase generator would render "y1_pct" as "y1Pct" but "1y" style
    # names cannot start an identifier.
    y1_pct: float | None = Field(default=None, alias="y1Pct")
    y3_pct: float | None = Field(default=None, alias="y3Pct")
    y5_pct: float | None = Field(default=None, alias="y5Pct")
    # Change over the full stored history, and the date it starts from — so
    # the UI can label it "since 2025-06-16" rather than claiming a horizon.
    max_pct: float | None = None
    max_from_date: date | None = None


class QuarterlyReport(_CamelModel):
    """One quarter of income-statement data."""

    period_end: str
    total_revenue: int | None = None
    net_income: int | None = None
    operating_income: int | None = None
    eps: float | None = None


class CashflowPeriod(_CamelModel):
    """One reported period of investment-related cash-flow figures.

    Sourced from Yahoo's cash-flow statement (annual and quarterly frames).
    ``capex`` is normalised to a POSITIVE "money spent" number — Yahoo reports
    capital expenditure as a negative cash outflow, which reads as "-1.4bn
    invested" in a table and sorts backwards.
    """

    period_end: str
    # "annual" = a full reporting year, "quarterly" = one quarter.
    period_type: Literal["annual", "quarterly"]
    capex: int | None = None
    operating_cash_flow: int | None = None
    free_cash_flow: int | None = None
    # Reporting currency of these figures (Yahoo ``financialCurrency``). NOT
    # always PLN: foreign dual-listings report in EUR/USD/CZK/HUF/UAH, so the
    # value is meaningless without it.
    currency: str | None = None


class CapexSummary(_CamelModel):
    """How much a company invests in itself, condensed to one row.

    All money figures are in ``currency`` (positive = spent). ``basis`` says
    which reporting period the headline ``capex`` and the two ratios describe:
    ``"ttm"`` (last four quarters — preferred) or ``"annual"`` (the latest full
    year, used when quarterly cash-flow data is missing). Every field is
    optional: for roughly one company in five Yahoo has no usable capex, and a
    blank cell is the honest answer.
    """

    currency: str | None = None
    # Which period the headline capex/ratios refer to; None when no data.
    basis: Literal["ttm", "annual"] | None = None
    # Headline figure — capex_ttm when available, else capex_annual.
    capex: int | None = None
    # Last four reported quarters summed (None unless all four carry a figure).
    capex_ttm: int | None = None
    # Latest full reporting year, and the year before it (for the YoY change).
    capex_annual: int | None = None
    annual_period_end: str | None = None
    capex_prev_annual: int | None = None
    # Change in yearly capex, percent — the "is it investing more?" number.
    capex_growth_yoy_pct: float | None = None
    # Capex as a share of revenue: capital intensity, comparable across sizes.
    capex_to_revenue_pct: float | None = None
    # Capex as a share of operating cash flow: above 100% means the investment
    # is not covered by what the business itself generates.
    capex_to_ocf_pct: float | None = None
    operating_cash_flow: int | None = None


class CapexItem(CapexSummary):
    """One row of the capex screen: a company plus its investment figures."""

    ticker: str
    name: str
    sector: str | None = None


class CapexResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/capex``."""

    # Newest reporting period end across all companies with data.
    as_of: str | None = None
    # Companies matching the filters before pagination (the pager total).
    total_count: int = 0
    # Of those, how many actually carry a capex figure.
    with_data_count: int = 0
    # Companies considered before filtering — context for "why so few rows".
    scanned_count: int = 0
    items: list[CapexItem] = []


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
    # Trailing price returns computed from the stored EOD bars.
    price_returns: PriceReturns | None = None
    # Trailing-twelve-month revenue / net income — the last four reported
    # quarters summed. None when fewer than four quarters are stored, or when
    # any of them is missing the figure (a partial sum would understate it).
    ttm_revenue: int | None = None
    ttm_net_income: int | None = None
    # How much the company invests in itself (capital expenditure). None when
    # Yahoo has no cash-flow statement for this ticker.
    capex: CapexSummary | None = None


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


# ── New models: analytics opinion summary endpoint ───────────────────────────


class AnalyticsOpinionSource(_CamelModel):
    """One analytical engine's contribution to the consolidated opinion.

    A row in the "Analytics summary" card. Most sources are *directional* —
    they lean bullish / bearish / neutral (VSA, the AI Insight second opinion,
    each trading method). One is a *reliability* gauge (the Signal Trust
    Score): it does not vote on direction, it says how much the VSA calls on
    this stock can be trusted, so it is coloured green (reliable) → red
    (unreliable) rather than by market direction.
    """

    # Stable key, e.g. "vsa", "aiInsight", "trustScore", "minervini".
    key: str
    # Display name shown in the card, e.g. "VSA rating", "AI Insight".
    label: str
    # "direction" sources vote on the consensus; "reliability" ones don't.
    kind: Literal["direction", "reliability"]
    # For a direction source: its bullish/bearish/neutral lean. For a
    # reliability source: green ("bullish") = reliable, red ("bearish") =
    # unreliable, "neutral" = mixed/unknown. "unavailable" = could not evaluate.
    stance: Literal["bullish", "bearish", "neutral", "unavailable"]
    # Compact value, e.g. "Buy · 72/100", "Strong Buy · 68% conf.", "6/7 rules".
    headline: str
    # One plain-language sentence explaining this source's read.
    detail: str
    # The source's entry setup fired in the last few sessions (methods only).
    fired_recently: bool = False


class AnalyticsSummaryResponse(_CamelModel):
    """Response payload for ``GET /api/stocks/{ticker}/opinion-summary``.

    A single consolidated read that fuses the app's separate per-stock
    opinions — the VSA rating/verdict, the AI Insight second opinion, the
    Signal Trust Score and every trading method — into one plain-language
    takeaway: where they agree, where they disagree, and the bottom line.
    Computed locally by ``app/analysis/analytics_summary.py``; deterministic,
    no external AI services.
    """

    ticker: str
    name: str | None = None
    # Trading day of the last bar the summary is based on.
    as_of: date
    # The consolidated direction across the directional sources. "mixed" when
    # bullish and bearish sources genuinely conflict.
    stance: Literal["bullish", "bearish", "neutral", "mixed"]
    # 0–100 — how strongly the directional sources agree with each other
    # (100 = unanimous, 50 = evenly split).
    agreement: int = Field(ge=0, le=100)
    # One-line takeaway.
    headline: str
    # Plain-language paragraph reconciling the sources.
    summary: str
    # Per-source breakdown (direction sources first, reliability last).
    sources: list[AnalyticsOpinionSource] = []
    # Identifier of the built-in engine that produced the summary.
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
