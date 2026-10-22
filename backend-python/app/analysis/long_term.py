"""Versioned, deterministic Quality / Value / Momentum screen (qvm-v1).

This ranks today's observable inputs; it does not estimate returns or their
probability. Total = equal-weight mean of three available component scores.
Missing components never acquire a neutral or bullish substitute.

Quality averages at least two of ROE, ROA and net-margin percentiles. Value
ranks trailing earnings yield (1 / positive P/E); known nonpositive net income
or EPS gets value zero if there are enough peers. Without that evidence, a
missing, zero, negative or nonfinite P/E is unavailable. Forward P/E is unused.
Momentum averages the percentiles of close[t-21]/close[t-252]-1 and
close[t-21]/close[t-126]-1. Both need 253 unique daily bars and reasonable
calendar coverage. Ratios and returns in ``inputs`` are fractions, not %.

All percentiles use average ranks for ties on a 0–100 scale; five observations
are required, and all-tied cohorts score 50. Each financial input compares to
the same sector within the same market if five usable observations exist,
otherwise to the whole market. Momentum always uses same-market peers.
Ineligible (stale, illiquid or small) companies never enter reference cohorts.

Callers supply only finished, corporate-action-adjusted daily bars. This pure
engine additionally rejects bars and financial observations after ``as_of``;
that date is an observation date, not a reconstructed earnings publication date.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean

from app.analysis.statistics import median_turnover
from app.markets import below_liquidity_floor, below_market_cap_floor, market_of, quote_currency
from app.models.long_term import MODEL_VERSION, LongTermItem
from app.models.stocks import FinancialMetrics, GpwCompany, StooqDailyQuote

__all__ = ["MODEL_VERSION", "compute_long_term"]

MIN_PEERS = 5
MAX_FUNDAMENTALS_AGE_DAYS = 45
MAX_PRICE_AGE_DAYS = 10
_QUALITY_KEYS = ("roe", "roa", "netMargin")
_MOMENTUM_KEYS = ("momentum12_1", "momentum6_1")
_INPUT_KEYS = (*_QUALITY_KEYS, "earningsYield", *_MOMENTUM_KEYS)


@dataclass
class _Candidate:
    company: GpwCompany
    currency: str
    last_session: date | None
    inputs: dict[str, float | None]
    observed_at: datetime | None
    missing: list[str]
    loss_making: bool


def _finite(value: float | int | None) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def _momentum(bars: list[StooqDailyQuote]) -> tuple[float | None, float | None]:
    if len(bars) < 253:
        return None, None
    recent = bars[-253:]
    # Reject compressed, duplicated, or very gappy histories. A year of 253
    # business days normally spans about 352–370 calendar days.
    end = recent[-1].date
    for offset, minimum, maximum in ((252, 330, 420), (126, 150, 220), (21, 21, 45)):
        if not minimum <= (end - recent[-offset - 1].date).days <= maximum:
            return None, None
    closes = [_finite(float(bar.close)) for bar in recent]
    if any(value is None or value <= 0 for value in closes):
        return None, None
    numerator = float(recent[-22].close)
    return (
        _finite(numerator / float(recent[0].close) - 1),
        _finite(numerator / float(recent[-127].close) - 1),
    )


def _candidate(
    company: GpwCompany,
    quotes: list[StooqDailyQuote],
    fundamentals: dict | None,
    as_of: date,
) -> _Candidate:
    inputs: dict[str, float | None] = dict.fromkeys(_INPUT_KEYS)
    missing: list[str] = []
    currency = quote_currency(company)
    bars = sorted(
        {bar.date: bar for bar in quotes if bar.date <= as_of}.values(), key=lambda bar: bar.date
    )
    if not bars or (as_of - bars[-1].date).days > MAX_PRICE_AGE_DAYS:
        missing.append("price_stale")
    if len(bars) < 20 or any(
        not bar.close.is_finite() or bar.close <= 0 or bar.volume < 0 for bar in bars[-20:]
    ):
        missing.append("liquidity")
    else:
        try:
            if below_liquidity_floor(median_turnover(bars), currency):
                missing.append("liquidity")
        except ValueError:
            # Unknown quote currencies must not silently clear the floor.
            missing.append("liquidity")

    metrics = (fundamentals or {}).get("metrics")
    observed_at = (fundamentals or {}).get("observed_at")
    admissible = (
        isinstance(metrics, FinancialMetrics)
        and isinstance(observed_at, datetime)
        and observed_at.tzinfo is not None
        and observed_at.utcoffset() is not None
    )
    if admissible:
        observed_day = observed_at.astimezone(market_of(company.ticker).tz).date()
        if observed_day > as_of:
            admissible = False
            observed_at = None
            missing.append("fundamentals_missing")
        elif (as_of - observed_day).days > MAX_FUNDAMENTALS_AGE_DAYS:
            admissible = False
            missing.append("fundamentals_stale")
    else:
        missing.append("fundamentals_missing")
        observed_at = None

    loss_making = False
    if admissible:
        income, revenue, eps = map(
            _finite, (metrics.net_income, metrics.total_revenue, metrics.eps)
        )
        loss_making = (income is not None and income <= 0) or (eps is not None and eps <= 0)
        roe = _finite(metrics.return_on_equity)
        # Loss divided by negative equity creates a misleading positive ROE.
        # EPS can establish that loss even when the total net-income field is
        # absent; use the same known-earnings evidence as the valuation gate.
        inputs["roe"] = None if loss_making and roe is not None and roe > 0 else roe
        inputs["roa"] = _finite(metrics.return_on_assets)
        inputs["netMargin"] = (
            _finite(income / revenue) if income is not None and revenue and revenue > 0 else None
        )
        pe = _finite(metrics.pe_ratio)
        inputs["earningsYield"] = 0.0 if loss_making else _finite(1 / pe) if pe and pe > 0 else None

    # Market cap is denominated in the major quote currency (GBP, not GBp),
    # even when accounting figures use another reporting currency altogether.
    cap = (
        metrics.market_cap if admissible and metrics.market_cap is not None else company.market_cap
    )
    try:
        if below_market_cap_floor(cap, currency):
            missing.append("market_cap")
    except ValueError:
        missing.append("market_cap")
    inputs["momentum12_1"], inputs["momentum6_1"] = _momentum(bars)
    return _Candidate(
        company,
        currency,
        bars[-1].date if bars else None,
        inputs,
        observed_at,
        missing,
        loss_making,
    )


def _percentile(value: float, peers: list[float]) -> float:
    below = sum(peer < value for peer in peers)
    tied = sum(peer == value for peer in peers)
    return 100 * (below + (tied - 1) / 2) / (len(peers) - 1)


def compute_long_term(
    companies: list[GpwCompany],
    quotes: dict[str, list[StooqDailyQuote]],
    fundamentals: dict[str, dict],
    *,
    as_of: date,
) -> list[LongTermItem]:
    """Return every company, ordered by score descending, unavailable rows last.

    ``coverage`` is the percentage of six raw inputs available. ``peer_count``
    is the smallest cohort used for a reported metric. Financial comparison
    groups may be mixed when one metric has sparser sector data than another.
    """
    candidates = [
        _candidate(c, quotes.get(c.ticker, []), fundamentals.get(c.ticker), as_of)
        for c in companies
    ]
    output: list[LongTermItem] = []
    for row in candidates:
        missing = list(row.missing)
        ranked: dict[str, float] = {}
        peer_counts: list[int] = []
        financial_groups: set[str] = set()
        insufficient_peers = False
        if not missing:
            for key, value in row.inputs.items():
                if value is None:
                    continue
                peers = [
                    peer
                    for peer in candidates
                    if not peer.missing
                    and peer.company.market == row.company.market
                    and peer.inputs[key] is not None
                ]
                group = "market"
                if key not in _MOMENTUM_KEYS and row.company.sector:
                    sector = [peer for peer in peers if peer.company.sector == row.company.sector]
                    if len(sector) >= MIN_PEERS:
                        peers, group = sector, "sector"
                if len(peers) < MIN_PEERS:
                    insufficient_peers = True
                    continue
                ranked[key] = _percentile(value, [peer.inputs[key] for peer in peers])
                peer_counts.append(len(peers))
                if key not in _MOMENTUM_KEYS:
                    financial_groups.add(group)
            if row.loss_making and "earningsYield" in ranked:
                ranked["earningsYield"] = 0.0

        quality_parts = [ranked[key] for key in _QUALITY_KEYS if key in ranked]
        quality = mean(quality_parts) if len(quality_parts) >= 2 else None
        value_score = ranked.get("earningsYield")
        momentum = (
            mean(ranked[key] for key in _MOMENTUM_KEYS)
            if all(key in ranked for key in _MOMENTUM_KEYS)
            else None
        )
        # Explain missing inputs separately from a score withheld by freshness,
        # eligibility or peer-count gates. Complete history does not become
        # incomplete merely because a stock is illiquid or its prices are old.
        if not {"fundamentals_missing", "fundamentals_stale"}.intersection(row.missing):
            if sum(row.inputs[key] is not None for key in _QUALITY_KEYS) < 2:
                missing.append("quality_missing")
            if row.inputs["earningsYield"] is None:
                missing.append("value_missing")
        if any(row.inputs[key] is None for key in _MOMENTUM_KEYS):
            missing.append("momentum_missing")
        complete = all(value is not None for value in (quality, value_score, momentum))
        if insufficient_peers and not complete:
            missing.append("peers_missing")
        score = mean((quality, value_score, momentum)) if complete else None
        output.append(
            LongTermItem(
                ticker=row.company.ticker,
                name=row.company.name,
                sector=row.company.sector,
                market=row.company.market,
                currency=row.currency,
                as_of=row.last_session,
                score=round(score, 2) if score is not None else None,
                quality_score=round(quality, 2) if quality is not None else None,
                value_score=round(value_score, 2) if value_score is not None else None,
                momentum_score=round(momentum, 2) if momentum is not None else None,
                coverage=round(100 * sum(v is not None for v in row.inputs.values()) / 6, 2),
                eligible=complete,
                missing=missing,
                inputs=row.inputs,
                fundamentals_observed_at=row.observed_at,
                comparison_group=(
                    next(iter(financial_groups))
                    if len(financial_groups) == 1
                    else "mixed"
                    if financial_groups
                    else "market"
                ),
                peer_count=min(peer_counts, default=0),
            )
        )
    return sorted(output, key=lambda row: (row.score is None, -(row.score or 0), row.ticker))
