"""Phase 0's measurements — plan §6.5 / §6.6, used by ``scripts/ml_report.py``.

Before any model is trained, the bench has to show three things:

1. it **reproduces the app's own back-test gate** (``reproduce_gate``) — a
   bench that cannot re-measure what the app already measures is not ready to
   measure anything new (plan §6.6);
2. its features **never look ahead** (``leak_check``);
3. what the unfiltered methods score, and how high **a random filter** already
   scores by chance (``summarise_method``, ``random_filter_bar``) — the bar
   every AI filter has to clear.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.dataset import MIN_STOCKS_PER_DAY, StockInput
from app.ml.features import METHOD_FEATURE_IDS, STOCK_FEATURE_COLUMNS, stock_features
from app.ml.labels import gate_baseline_pct, gate_forward_pct
from app.ml.validation import random_filter_precisions, truncation_check, wilson_interval

# The gate's history window (method_backtest_service._BACKTEST_HISTORY_DAYS).
GATE_WINDOW_DAYS = 1460


@dataclass(frozen=True)
class GateNumbers:
    """The gate's headline figures, from either the app or the bench."""

    evaluated: int
    wins: int
    win_rate_pct: float | None
    avg_excess_pp: float | None


def reproduce_gate(
    stocks: Sequence[StockInput],
    method_id: str,
    horizons: Sequence[int],
    today: date,
    *,
    vsa4_tick: str = "last_close",
) -> dict[int, GateNumbers]:
    """The gate's numbers recomputed through the bench's own code path.

    Same window as the gate (the last 1,460 days), but the firings come from
    ``features.stock_features`` and the outcome from ``labels`` — so a match
    with ``method_backtest_service`` proves the bench's wiring, not just a
    shared function. One feature pass per stock serves every horizon.

    ``vsa4_tick="last_close"`` (the default) reads VSA V4 exactly as the gate
    does; ``"point_in_time"`` reads it as the program would have on each day,
    which is what shows how much the gate's reading leans on today's price.
    """
    since = today - timedelta(days=GATE_WINDOW_DAYS)
    tally = {n: [0, 0, 0.0] for n in horizons}  # evaluated, wins, excess sum
    for stock in stocks:
        bars = sorted((b for b in stock.bars if b.date >= since), key=lambda b: b.date)
        if len(bars) <= min(horizons):
            continue
        frame = stock_features(bars, method_ids=(method_id,), vsa4_tick=vsa4_tick)
        fired = np.flatnonzero(frame[f"fire_{method_id}"].to_numpy() > 0)
        closes = np.array([float(b.close) for b in bars])
        for n in horizons:
            if len(bars) <= n:
                continue
            pct = gate_forward_pct(closes, n)
            base = gate_baseline_pct(closes, n)
            if base is None:
                continue
            for t in fired:
                if np.isfinite(pct[t]):
                    tally[n][0] += 1
                    tally[n][1] += int(pct[t] > base)
                    tally[n][2] += pct[t] - base
    out: dict[int, GateNumbers] = {}
    for n, (evaluated, wins, excess_sum) in tally.items():
        if evaluated == 0:
            out[n] = GateNumbers(0, 0, None, None)
        else:
            out[n] = GateNumbers(
                evaluated,
                wins,
                round(wins / evaluated * 100, 1),
                round(float(excess_sum) / evaluated, 2),
            )
    return out


@dataclass
class MethodSummary:
    """One method at one horizon, unfiltered, on every label the bench has."""

    method: str
    horizon: int
    firings: int
    l1_n: int
    l1_precision: float | None
    l1_ci: tuple[float, float]
    l1_avg_excess_pct: float | None
    l2_n: int
    l2_precision: float | None
    l2_avg_excess_pp: float | None
    l3_n: int
    l3_win_rate: float | None
    l3_expectancy_r: float | None
    by_year: list[tuple[int, int, float | None]] = field(default_factory=list)


def _mean(values: pd.Series) -> float | None:
    values = values.dropna()
    return float(values.mean()) if len(values) else None


def summarise_method(job1: pd.DataFrame, method: str, horizon: int) -> MethodSummary:
    """Precision, edge and expectancy of one method's firings, unfiltered."""
    rows = job1.loc[job1["method"] == method] if not job1.empty else job1
    y1 = rows[f"l1_y_{horizon}"].dropna() if len(rows) else pd.Series(dtype=float)
    l1_wins = int(y1.sum())
    y2 = rows[f"l2_y_{horizon}"].dropna() if len(rows) else pd.Series(dtype=float)
    r3 = rows[f"l3_r_{horizon}"].dropna() if len(rows) else pd.Series(dtype=float)

    by_year: list[tuple[int, int, float | None]] = []
    if len(rows):
        years = pd.to_datetime(rows["date"]).dt.year
        for year in sorted(years.unique()):
            ys = rows.loc[years == year, f"l1_y_{horizon}"].dropna()
            by_year.append((int(year), int(len(ys)), float(ys.mean()) if len(ys) else None))

    return MethodSummary(
        method=method,
        horizon=horizon,
        firings=int(len(rows)),
        l1_n=int(len(y1)),
        l1_precision=float(y1.mean()) if len(y1) else None,
        l1_ci=wilson_interval(l1_wins, len(y1)),
        l1_avg_excess_pct=(
            _mean(rows[f"l1_excess_{horizon}"]) * 100
            if len(rows) and _mean(rows[f"l1_excess_{horizon}"]) is not None
            else None
        ),
        l2_n=int(len(y2)),
        l2_precision=float(y2.mean()) if len(y2) else None,
        l2_avg_excess_pp=_mean(rows[f"l2_excess_{horizon}"]) if len(rows) else None,
        l3_n=int(len(r3)),
        l3_win_rate=float((r3 > 0).mean()) if len(r3) else None,
        l3_expectancy_r=float(r3.mean()) if len(r3) else None,
        by_year=by_year,
    )


def random_filter_bar(
    labels: pd.Series, keep_rates: Sequence[float] = (0.3, 0.4, 0.5)
) -> dict[float, tuple[float, float]]:
    """For each keep-rate: (mean, 95th percentile) precision of a random filter."""
    y = labels.dropna().to_numpy(dtype=float)
    out: dict[float, tuple[float, float]] = {}
    for rate in keep_rates:
        draws = random_filter_precisions(y, rate)
        if len(draws):
            out[rate] = (float(draws.mean()), float(np.quantile(draws, 0.95)))
    return out


@dataclass(frozen=True)
class MarketCoverage:
    market: str
    companies: int
    bars: int
    first_date: date | None
    median_first_date: date | None
    days_with_market: int  # days on which ≥ MIN_STOCKS_PER_DAY stocks traded
    first_full_day: date | None  # first such day


def coverage(stocks: Sequence[StockInput]) -> list[MarketCoverage]:
    """How much history each market really has — the plan's §3.3 question."""
    out = []
    by_market: dict[str, list[StockInput]] = {}
    for s in stocks:
        by_market.setdefault(s.market, []).append(s)
    for market, items in by_market.items():
        firsts = sorted(min(b.date for b in s.bars) for s in items if s.bars)
        per_day: Counter[date] = Counter(b.date for s in items for b in s.bars)
        full = sorted(d for d, k in per_day.items() if k >= MIN_STOCKS_PER_DAY)
        out.append(
            MarketCoverage(
                market=market,
                companies=len(items),
                bars=sum(len(s.bars) for s in items),
                first_date=firsts[0] if firsts else None,
                median_first_date=firsts[len(firsts) // 2] if firsts else None,
                days_with_market=len(full),
                first_full_day=full[0] if full else None,
            )
        )
    return out


#: Columns whose non-zero rows are "events" — signals, firings, markers.
_EVENT_COLUMNS = (
    "vsa_bull_today",
    "vsa_bear_today",
    *(f"fire_{mid}" for mid in METHOD_FEATURE_IDS),
    "m_vsa4_bear5",
    "m_vsa3_watch5",
    "m_vsa4_watch5",
)


def leak_check(
    stocks: Sequence[StockInput],
    samples: int,
    seed: int = 20260925,
    min_bars: int = 300,
    event_samples: int = 0,
    event_stocks: int = 40,
) -> tuple[int, Counter[str], list[str]]:
    """Truncation check on random (stock, day) pairs, plus targeted event days.

    ``samples`` random rows, and ``event_samples`` rows chosen among the days
    on which a signal, firing or marker happens (drawn from ``event_stocks``
    random stocks) — random days almost never land on a rare marker, and a
    marker is exactly where look-ahead hides. Returns (rows checked,
    mismatches per feature, a few example lines). An empty counter is the pass.
    """
    rng = random.Random(seed)
    eligible = [s for s in stocks if len(s.bars) >= min_bars]
    if not eligible:
        return 0, Counter(), []
    picks: dict[str, list[int]] = {}
    for _ in range(samples):
        stock = rng.choice(eligible)
        picks.setdefault(stock.ticker, []).append(rng.randrange(60, len(stock.bars)))
    if event_samples:
        events: list[tuple[str, int]] = []
        for stock in rng.sample(eligible, min(event_stocks, len(eligible))):
            frame = stock_features(stock.bars)
            hit = np.zeros(len(frame), dtype=bool)
            for col in _EVENT_COLUMNS:
                values = frame[col].fillna(0.0).to_numpy()
                hit |= np.concatenate(([False], np.diff(values) != 0)) | (values > 0)
            events += [(stock.ticker, int(i)) for i in np.flatnonzero(hit) if i >= 60]
        for ticker, pos in rng.sample(events, min(event_samples, len(events))):
            picks.setdefault(ticker, []).append(pos)
    by_ticker = {s.ticker: s for s in eligible}
    counts: Counter[str] = Counter()
    examples: list[str] = []
    checked = 0
    for ticker, positions in picks.items():
        problems = truncation_check(
            by_ticker[ticker].bars, sorted(set(positions)), stock_features, STOCK_FEATURE_COLUMNS
        )
        checked += len(set(positions))
        for p in problems:
            counts[p.column] += 1
            if len(examples) < 10:
                examples.append(f"{ticker} {p.date} {p.column}: {p.full} vs {p.truncated}")
    return checked, counts, examples
