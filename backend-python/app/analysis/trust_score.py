"""VSA prediction-accuracy ("trust") score per stock.

The rule engine (``app/analysis/vsa.py``) detects signals; the insight engine
(``app/analysis/ai_insight.py``) judges their chart context. This module
answers a third question: *when this stock's chart said Strong Buy or Strong
Sell in the past, was it actually right?*

Every historical Strong Buy / Strong Sell signal old enough to judge is
replayed as a paper trade:

  * the signal bar's close is the entry;
  * its forward return over the next ``HORIZON_SESSIONS`` sessions is compared
    with the stock's *baseline* — the median forward return over the same
    horizon across the whole analysed window, i.e. what entering on a random
    day would typically have done;
  * the entry is "good" when it beat that baseline in the signal's direction
    (price outperformed after a Strong Buy, underperformed after a Strong
    Sell).

The hit-rate and the median edge over baseline are then folded into a single
0–100 trust score, shrunk toward the neutral 50 on small samples; below
``_MIN_EVALUATED`` judged signals no numeric score is reported at all
(``grade: "insufficient"``), so a couple of lucky signals can never produce
a high grade. Deterministic, computed locally from the same OHLCV data the
charts use. Used by ``GET /api/stocks/{ticker}/trust-score``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median

from app.analysis.vsa import VsaSignal, verdict_for_signal
from app.models import StooqDailyQuote, TrustScoreEvent, TrustScoreResponse

# Bumped when the scoring heuristics change, so the frontend can show what
# produced a stored/cached score.
ENGINE_VERSION = "stockpilot-trust-1"

# Sessions a paper entry is held before it is judged (matches the scanner
# back-test and the insight engine's historical statistic).
HORIZON_SESSIONS = 10

# Only these verdicts are back-tested — the feature scores the engine's
# *strong* calls, not every Buy/Sell lean.
_STRONG_VERDICTS = ("Strong Buy", "Strong Sell")

# Excess return (percentage points over baseline) at which the magnitude
# component saturates; ~4 pp over 10 sessions is already a large edge.
_EXCESS_SCALE_PP = 4.0

# Blend of the two evidence components in the raw score.
_HIT_RATE_WEIGHT = 0.65
_MAGNITUDE_WEIGHT = 0.35

# Sample-size shrinkage: with n evaluated signals the raw score keeps
# n / (n + _SHRINK_N) of its distance from the neutral 50, so a handful of
# lucky signals can never produce an extreme score (with n = 8 the score
# keeps 40% of its distance from neutral).
_SHRINK_N = 12

# Minimum evaluated signals before a numeric score is reported at all —
# below this the sample is too small to grade and the response uses the
# "insufficient" path (score: null).
_MIN_EVALUATED = 8

# Score boundaries for the qualitative grade.
_GRADE_HIGH = 65
_GRADE_LOW = 45

# Newest events included in the response (the counts always cover all).
_MAX_EVENTS = 20


def _pct_change(a: float, b: float) -> float:
    return (b - a) / a * 100.0 if a else 0.0


def _grade_for(score: int) -> str:
    if score >= _GRADE_HIGH:
        return "high"
    if score < _GRADE_LOW:
        return "low"
    return "medium"


def _score_from(hit_rate: float, median_excess_pp: float, n: int) -> int:
    """Fold hit-rate and median edge into the shrunk 0–100 trust score.

    The magnitude term uses the MEDIAN excess return, matching the median
    baseline — a mean here would let one outlier rally (right-skewed returns)
    systematically favour buy signals.
    """
    magnitude = 0.5 + 0.5 * math.tanh(median_excess_pp / _EXCESS_SCALE_PP)
    raw = 100.0 * (_HIT_RATE_WEIGHT * hit_rate + _MAGNITUDE_WEIGHT * magnitude)
    shrunk = 50.0 + (raw - 50.0) * n / (n + _SHRINK_N)
    return max(0, min(100, round(shrunk)))


def _build_summary(
    *,
    display_name: str,
    n: int,
    good: int,
    fresh: int,
    baseline: float | None,
    avg_excess: float | None,
    score: int | None,
    grade: str,
) -> str:
    if n == 0:
        base = (
            f"The VSA engine fired no Strong Buy or Strong Sell signal on "
            f"{display_name} in the analysed window that is old enough to judge, "
            f"so there is no track record to score yet."
        )
        if fresh:
            base += (
                f" {fresh} recent strong signal(s) will become scorable once "
                f"{HORIZON_SESSIONS} sessions have passed."
            )
        return base

    assert baseline is not None and avg_excess is not None
    sentences = [
        f"Of the {n} strong signal(s) the VSA engine fired on {display_name} in "
        f"the analysed window, {good} ({good / n * 100:.0f}%) proved to be good "
        f"entries: price did better over the following {HORIZON_SESSIONS} "
        f"sessions than the stock's typical {HORIZON_SESSIONS}-session move "
        f"({baseline:+.1f}%).",
        f"In the typical (median) case, acting on these signals "
        f"{'beat' if avg_excess >= 0 else 'lagged'} that baseline by "
        f"{abs(avg_excess):.1f} percentage points.",
    ]
    if fresh:
        sentences.append(
            f"{fresh} more recent strong signal(s) are still too fresh to judge."
        )
    if score is None:
        sentences.append(
            f"Only {n} strong signal(s) are old enough to judge — fewer than "
            f"the {_MIN_EVALUATED} needed for a reliable trust score, so no "
            f"score is given yet."
        )
    else:
        quality = {
            "high": "have been reliable",
            "medium": "have a mixed record",
            "low": "have been unreliable",
        }[grade]
        sentences.append(
            f"Overall, strong VSA signals {quality} on this stock: "
            f"trust score {score}/100."
        )
    return " ".join(sentences)


def compute_trust_score(
    *,
    ticker: str,
    name: str | None,
    quotes: Sequence[StooqDailyQuote],
    signals: Sequence[VsaSignal],
) -> TrustScoreResponse:
    """Back-test the stock's historical strong verdicts into one trust score.

    ``quotes`` must be in date order and non-empty; ``signals`` are the
    rule-engine detections for the same window (any VsaConfig).
    """
    if not quotes:
        raise ValueError("compute_trust_score requires at least one quote.")

    closes = [float(q.close) for q in quotes]
    idx_of = {q.date: i for i, q in enumerate(quotes)}
    as_of = quotes[-1].date
    # Last bar index that still has a full forward horizon behind it.
    last_entry_idx = len(closes) - 1 - HORIZON_SESSIONS

    # Baseline: the stock's typical (median) forward return over the horizon,
    # measured from every bar in the window — the "random-day entry".
    forward_returns = [
        _pct_change(closes[i], closes[i + HORIZON_SESSIONS])
        for i in range(last_entry_idx + 1)
    ]
    baseline = median(forward_returns) if forward_returns else None

    events: list[TrustScoreEvent] = []
    raw_excess: list[float] = []
    fresh = 0
    for s in signals:
        verdict = verdict_for_signal(s.signal_name)
        if verdict not in _STRONG_VERDICTS:
            continue
        idx = idx_of.get(s.date)
        if idx is None:
            continue
        if idx > last_entry_idx or baseline is None:
            fresh += 1
            continue
        fwd = _pct_change(closes[idx], closes[idx + HORIZON_SESSIONS])
        excess = (fwd - baseline) if verdict == "Strong Buy" else (baseline - fwd)
        raw_excess.append(excess)
        events.append(
            TrustScoreEvent(
                date=s.date,
                signal_name=s.signal_name.value,
                verdict=verdict,  # type: ignore[arg-type]
                forward_return_pct=round(fwd, 2),
                baseline_return_pct=round(baseline, 2),
                excess_return_pct=round(excess, 2),
                good_entry=excess > 0,
            )
        )

    n = len(events)
    good = sum(1 for e in events if e.good_entry)
    buy = [e for e in events if e.verdict == "Strong Buy"]
    sell = [e for e in events if e.verdict == "Strong Sell"]

    if n == 0:
        score: int | None = None
        grade = "insufficient"
        avg_excess: float | None = None
    else:
        # Median (not mean) excess, consistent with the median baseline:
        # right-skewed returns would let one outlier rally drag a mean up
        # and systematically favour buy signals.
        avg_excess = median(raw_excess)
        if n < _MIN_EVALUATED:
            # Too few judged signals for a meaningful grade — report the
            # counts and the (median) edge, but no numeric score.
            score = None
            grade = "insufficient"
        else:
            score = _score_from(good / n, avg_excess, n)
            grade = _grade_for(score)

    summary = _build_summary(
        display_name=name or ticker.upper(),
        n=n,
        good=good,
        fresh=fresh,
        baseline=baseline,
        avg_excess=avg_excess,
        score=score,
        grade=grade,
    )

    return TrustScoreResponse(
        ticker=ticker.upper(),
        as_of=as_of,
        score=score,
        grade=grade,  # type: ignore[arg-type]
        horizon_sessions=HORIZON_SESSIONS,
        evaluated_count=n,
        good_count=good,
        fresh_count=fresh,
        buy_evaluated=len(buy),
        buy_good=sum(1 for e in buy if e.good_entry),
        sell_evaluated=len(sell),
        sell_good=sum(1 for e in sell if e.good_entry),
        baseline_return_pct=round(baseline, 2) if baseline is not None else None,
        avg_excess_return_pct=round(avg_excess, 2) if avg_excess is not None else None,
        summary=summary,
        events=list(reversed(events))[:_MAX_EVENTS],  # newest first for the UI
        engine=ENGINE_VERSION,
    )
