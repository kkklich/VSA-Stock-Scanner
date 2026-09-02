"""Consolidated per-stock analytics opinion — the "bottom line" summary.

The app judges a stock through several independent lenses, each on its own
card: the VSA rating/verdict (``vsa.py``), the AI Insight second opinion
(``ai_insight.py``), the Signal Trust Score (``trust_score.py``) and every
pluggable trading method (``methods/``). A reader has to assemble the takeaway
themselves from four cards that don't always agree.

This module does that assembly. It fuses those opinions into ONE plain-language
read: an overall stance (bullish / bearish / neutral / mixed), a 0–100 measure
of how much the sources agree, a one-line takeaway and a short paragraph that
reconciles them — where they line up, where they conflict, and how much to
trust the VSA calls on this particular stock.

Two kinds of source feed it:

  * *directional* sources vote on the stance — the VSA verdict, the AI Insight
    verdict, and each trading method (long-only, so a method votes bullish or
    stays neutral, never bearish);
  * one *reliability* source — the Signal Trust Score — does not vote on
    direction; it only modulates how confidently the takeaway is phrased.

Deterministic and local: it calls the same built-in engines the individual
cards use (no external AI services, no API keys), so the summary can never
disagree with the cards it summarises. Used by
``GET /api/stocks/{ticker}/opinion-summary``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.ai_insight import analyze_stock
from app.analysis.methods import all_methods
from app.analysis.methods.base import MethodResult, TradingMethod
from app.analysis.methods.vsa_method import vsa_result_from_signals
from app.analysis.trust_score import compute_trust_score
from app.analysis.vsa import (
    VsaConfig,
    VsaSignal,
    compute_rating,
    verdict_from_signals,
)
from app.models import (
    AnalyticsOpinionSource,
    AnalyticsSummaryResponse,
    StooqDailyQuote,
)

# Bumped when the consolidation heuristics change, so a stored/cached summary
# can show which engine produced it (mirrors the other analysis engines).
ENGINE_VERSION = "stockpilot-summary-1"

# The five-level verdict → signed lean in [-1, +1] (bullish positive). Shared by
# the VSA verdict and the AI Insight verdict, so both map onto one scale.
_VERDICT_LEAN: dict[str, float] = {
    "Strong Buy": 1.0,
    "Buy": 0.5,
    "Hold": 0.0,
    "Sell": -0.5,
    "Strong Sell": -1.0,
}

# A source counts as leaning (rather than neutral) once its lean clears this.
_LEAN_EPS = 0.15

# Relative weight of each directional source in the consensus mean. The two
# full verdict engines lead; a single trading method is supporting evidence.
_WEIGHT_VSA = 1.0
_WEIGHT_AI = 1.0
_WEIGHT_METHOD = 0.6

# Agreement (0–100) at/above which a one-sided read is called "broadly agree"
# rather than merely "leans"; and below which a two-sided read is "mixed".
_AGREE_STRONG = 80
_AGREE_MIXED = 67

# A trading method's 0–100 score maps to a bullish lean above the neutral 50;
# below 50 the setup is simply absent (not bearish — every method is
# long-only), so it contributes no bearish vote.
def _method_lean(score: int) -> float:
    return max(0.0, (score - 50) / 50.0)


def _stance_from_lean(lean: float) -> str:
    if lean > _LEAN_EPS:
        return "bullish"
    if lean < -_LEAN_EPS:
        return "bearish"
    return "neutral"


@dataclass(frozen=True)
class _Directional:
    """A directional source plus the signed lean it contributes."""

    source: AnalyticsOpinionSource
    lean: float
    weight: float


def _vsa_source(result: MethodResult, verdict: str) -> _Directional:
    # ``result`` comes from the shared ``vsa_result_from_signals`` helper the
    # ranking uses, so the score (== rating) and the "fired recently" flag match
    # the dashboard's VSA column exactly. Direction comes from the verdict,
    # which — unlike a method's score — can be bearish.
    lean = _VERDICT_LEAN.get(verdict, 0.0)
    rating = result.score
    src = AnalyticsOpinionSource(
        key="vsa",
        label="VSA rating",
        kind="direction",
        stance=_stance_from_lean(lean),
        headline=f"{verdict} · {rating}/100",
        detail=(
            f"Volume Spread Analysis rates this stock {rating}/100 and reads the "
            f"balance of professional buying vs. selling as {verdict}."
        ),
        fired_recently=result.fired,
    )
    return _Directional(src, lean, _WEIGHT_VSA)


def _ai_source(verdict: str, confidence: int) -> _Directional:
    raw_lean = _VERDICT_LEAN.get(verdict, 0.0)
    # An unsure AI leans less: scale its contribution by confidence so a
    # low-confidence Strong Buy counts like a mild Buy, not a full one.
    lean = raw_lean * (0.4 + 0.6 * confidence / 100.0)
    src = AnalyticsOpinionSource(
        key="aiInsight",
        label="AI Insight",
        kind="direction",
        stance=_stance_from_lean(raw_lean),
        headline=f"{verdict} · {confidence}% conf.",
        detail=(
            f"The AI Insight second opinion — which judges each VSA signal by its "
            f"follow-through, trend and track record — concludes {verdict} with "
            f"{confidence}% confidence."
        ),
        fired_recently=False,
    )
    return _Directional(src, lean, _WEIGHT_AI)


def _method_source(method: TradingMethod, result: MethodResult) -> _Directional | None:
    """A directional source for one non-VSA trading method, or None if it
    could not be evaluated on this stock (too little history)."""
    if not result.available:
        # Still surfaced to the reader as an unavailable row, but with no vote.
        return _Directional(
            AnalyticsOpinionSource(
                key=method.id,
                label=method.name,
                kind="direction",
                stance="unavailable",
                headline="—",
                detail=(
                    f"{method.name} could not be evaluated — not enough price "
                    f"history for this stock yet."
                ),
                fired_recently=False,
            ),
            lean=0.0,
            weight=0.0,  # unavailable → no weight in the consensus
        )
    lean = _method_lean(result.score)
    recent = result.days_since == 0
    if recent:
        recency = "and its setup fired on the latest session"
    elif result.days_since < 999:
        recency = f"and its setup last fired {result.days_since} day(s) ago"
    else:
        recency = "and its setup is not currently triggering"
    src = AnalyticsOpinionSource(
        key=method.id,
        label=method.name,
        kind="direction",
        stance=_stance_from_lean(lean),
        headline=(f"{result.detail} · {result.score}/100" if result.detail
                  else f"{result.score}/100"),
        detail=f"{method.name} scores {result.score}/100 {recency}.",
        fired_recently=recent,
    )
    return _Directional(src, lean, _WEIGHT_METHOD)


def _trust_source(grade: str, score: int | None, evaluated: int) -> AnalyticsOpinionSource:
    """The reliability row: how trustworthy VSA's strong calls have been here.

    Not a directional vote — coloured by reliability (green = reliable, red =
    unreliable) so it reuses the app's palette without pretending to be a
    market direction.
    """
    if grade == "high":
        stance, label = "bullish", "Reliable"
    elif grade == "low":
        stance, label = "bearish", "Unreliable"
    elif grade == "medium":
        stance, label = "neutral", "Mixed record"
    else:  # insufficient
        stance, label = "unavailable", "No track record"
    if score is not None:
        headline = f"{label} · {score}/100"
        detail = (
            f"On this stock the VSA engine's past strong calls have been "
            f"{label.lower()} (trust score {score}/100, {evaluated} judged)."
        )
    else:
        headline = label
        detail = (
            "There aren't enough past strong VSA signals on this stock yet to "
            "judge how reliable the engine has been here."
        )
    return AnalyticsOpinionSource(
        key="trustScore",
        label="Signal Trust Score",
        kind="reliability",
        stance=stance,  # type: ignore[arg-type]
        headline=headline,
        detail=detail,
        fired_recently=False,
    )


def _consensus(directional: Sequence[_Directional]) -> tuple[str, int, float]:
    """Fold the directional sources into (stance, agreement 0–100, mean lean).

    Only sources with weight (available ones) count. ``agreement`` is the share
    of sources in the largest agreeing camp — bullish, bearish, or neutral —
    so unanimity of any kind (including "all flat") reads as 100, while an even
    bull/bear split reads as 50.
    """
    voting = [d for d in directional if d.weight > 0]
    if not voting:
        return "neutral", 100, 0.0

    total_w = sum(d.weight for d in voting)
    mean_lean = sum(d.weight * d.lean for d in voting) / total_w

    bull = sum(1 for d in voting if d.lean > _LEAN_EPS)
    bear = sum(1 for d in voting if d.lean < -_LEAN_EPS)
    neutral = len(voting) - bull - bear
    agreement = round(100 * max(bull, bear, neutral) / len(voting))

    conflict = bull > 0 and bear > 0
    if conflict and agreement < _AGREE_MIXED:
        stance = "mixed"
    elif mean_lean > _LEAN_EPS:
        stance = "bullish"
    elif mean_lean < -_LEAN_EPS:
        stance = "bearish"
    else:
        stance = "neutral"
    return stance, agreement, mean_lean


def _headline(name: str, stance: str, agreement: int) -> str:
    if stance == "bullish":
        if agreement >= _AGREE_STRONG:
            return f"The signals broadly agree — {name} looks bullish."
        return f"The signals lean bullish on {name}, but not unanimously."
    if stance == "bearish":
        if agreement >= _AGREE_STRONG:
            return f"The signals broadly agree — {name} looks bearish."
        return f"The signals lean bearish on {name}, but not unanimously."
    if stance == "mixed":
        return f"The signals disagree on {name} — bullish and bearish reads are both present."
    return f"The signals are neutral on {name} right now."


def _reconcile(
    *,
    name: str,
    stance: str,
    vsa_verdict: str,
    vsa_rating: int,
    ai_verdict: str,
    ai_confidence: int,
    method_sources: Sequence[_Directional],
    trust_grade: str,
    trust_score: int | None,
) -> str:
    """The plain-language paragraph tying the sources together."""
    sentences: list[str] = []

    # 1. VSA vs. AI Insight — the two full verdict engines.
    vsa_lean = _VERDICT_LEAN.get(vsa_verdict, 0.0)
    ai_lean = _VERDICT_LEAN.get(ai_verdict, 0.0)
    if vsa_lean and ai_lean and (vsa_lean > 0) == (ai_lean > 0):
        relation = "the two agree"
    elif vsa_lean and ai_lean and (vsa_lean > 0) != (ai_lean > 0):
        relation = "the two point opposite ways"
    else:
        relation = "the two are only mildly apart"
    sentences.append(
        f"The VSA engine reads {name} as {vsa_verdict} (rating {vsa_rating}/100) "
        f"while the AI Insight second opinion says {ai_verdict} at "
        f"{ai_confidence}% confidence — {relation}."
    )

    # 2. What the other trading methods add.
    avail = [m for m in method_sources if m.weight > 0]
    if avail:
        bullish = [m.source.label for m in avail if m.lean > _LEAN_EPS]
        quiet = [m.source.label for m in avail if m.lean <= _LEAN_EPS]
        parts: list[str] = []
        if bullish:
            verb = "signals" if len(bullish) == 1 else "signal"
            parts.append(f"{_join(bullish)} {verb} a bullish setup")
        if quiet:
            verb = "is" if len(quiet) == 1 else "are"
            parts.append(f"{_join(quiet)} {verb} not triggering")
        if parts:
            sentences.append("Among the other methods, " + " while ".join(parts) + ".")

    # 3. Reliability of VSA's calls on this stock.
    if trust_score is not None:
        rel = {
            "high": "have been reliable",
            "medium": "have a mixed record",
            "low": "have been unreliable",
        }.get(trust_grade, "have a mixed record")
        sentences.append(
            f"On this stock, the engine's past strong calls {rel} "
            f"(trust score {trust_score}/100)."
        )
    else:
        sentences.append(
            "There isn't enough signal history on this stock yet to say how "
            "reliable the engine has been here."
        )

    # 4. The bottom line.
    if stance == "mixed":
        sentences.append(
            "Bottom line: the picture is genuinely mixed — one to watch, not a clear call."
        )
    elif stance == "neutral":
        sentences.append("Bottom line: no strong edge either way right now.")
    else:
        direction = "bullish" if stance == "bullish" else "bearish"
        caveat = (
            " — but treat it lightly given the unreliable track record here"
            if trust_grade == "low"
            else ""
        )
        sentences.append(f"Bottom line: a {direction} tilt{caveat}.")

    return " ".join(sentences)


def _join(items: Sequence[str]) -> str:
    """Human list join: 'A', 'A and B', 'A, B and C'."""
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])} and {items[-1]}"


def build_analytics_summary(
    *,
    ticker: str,
    name: str | None,
    quotes: Sequence[StooqDailyQuote],
    signals: Sequence[VsaSignal],
    config: VsaConfig | None = None,
) -> AnalyticsSummaryResponse:
    """Fuse every per-stock opinion into one consolidated summary.

    ``quotes`` must be in date order and non-empty; ``signals`` are the
    rule-engine detections for the same window (any ``VsaConfig``). Reuses the
    same built-in engines the individual cards use, so the summary can never
    contradict them.
    """
    if not quotes:
        raise ValueError("build_analytics_summary requires at least one quote.")

    display_name = name or ticker.upper()
    as_of = quotes[-1].date
    rating = compute_rating(signals, as_of)
    verdict, _vsa_days_since = verdict_from_signals(signals, as_of)
    vsa_result = vsa_result_from_signals(signals, rating, verdict, as_of)

    ai = analyze_stock(
        ticker=ticker, name=name, quotes=quotes, signals=signals, rating=rating
    )
    trust = compute_trust_score(
        ticker=ticker, name=name, quotes=quotes, signals=signals
    )

    # Directional sources, in display order: VSA, AI Insight, then each other
    # registered trading method (VSA is already represented above, so it is not
    # repeated as a method).
    directional: list[_Directional] = [
        _vsa_source(vsa_result, verdict),
        _ai_source(ai.verdict, ai.confidence),
    ]
    method_sources: list[_Directional] = []
    for method in all_methods():
        if method.id == "vsa":
            continue
        try:
            result = method.evaluate(quotes, config)
        except Exception:  # noqa: BLE001 — one bad method must not sink the summary
            result = MethodResult.unavailable("evaluation failed")
        entry = _method_source(method, result)
        if entry is not None:
            method_sources.append(entry)
    directional.extend(method_sources)

    stance, agreement, _mean = _consensus(directional)

    trust_row = _trust_source(trust.grade, trust.score, trust.evaluated_count)
    sources = [d.source for d in directional] + [trust_row]

    headline = _headline(display_name, stance, agreement)
    summary = _reconcile(
        name=display_name,
        stance=stance,
        vsa_verdict=verdict,
        vsa_rating=rating,
        ai_verdict=ai.verdict,
        ai_confidence=ai.confidence,
        method_sources=method_sources,
        trust_grade=trust.grade,
        trust_score=trust.score,
    )

    return AnalyticsSummaryResponse(
        ticker=ticker.upper(),
        name=name,
        as_of=as_of,
        stance=stance,  # type: ignore[arg-type]
        agreement=agreement,
        headline=headline,
        summary=summary,
        sources=sources,
        engine=ENGINE_VERSION,
    )
