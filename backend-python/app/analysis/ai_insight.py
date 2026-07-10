"""Built-in AI insight engine — a deterministic VSA expert system.

The rule engine in ``app/analysis/vsa.py`` detects signals bar by bar; it
cannot judge whether a signal made sense in its wider chart context. This
module adds that judgement layer, computed locally from the same OHLCV data —
no external services, no API keys, no per-call cost, and the same input always
produces the same answer.

For every rule-detected signal it checks:

  * follow-through — did price actually move the way the signal implied in
    the sessions that followed;
  * volume behaviour — where volume concentrated after the signal (up-days
    vs down-days), the classic VSA confirmation;
  * trend background — e.g. a Spring fires best after a downtrend
    (accumulation), an Upthrust after an uptrend (distribution);
  * the stock's own track record — how often this signal type was followed
    by the expected move on this ticker historically.

It then folds the per-signal verdicts, the trend and the volume pressure into
an overall verdict + confidence, and writes the whole reasoning out in plain
language. Used by ``GET /api/stocks/{ticker}/ai-analysis``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from app.analysis.vsa import SignalType, VsaSignal
from app.models import AiAnalysisResponse, AiSignalAssessment, StooqDailyQuote

# Bumped when the heuristics change, so the frontend can show what produced
# a stored/cached analysis.
ENGINE_VERSION = "stockpilot-insight-1"

# ── Tunables (trading sessions unless stated otherwise) ──────────────────────

# Sessions the trend/support/resistance context is measured over.
_CONTEXT_SMA = 20
# How far after a signal we look for follow-through.
_FOLLOW_THROUGH_BARS = 5
# Horizon for the per-signal historical success statistic (matches the
# scanner back-test convention).
_HISTORY_FWD_BARS = 10
# Minimum occurrences before the historical statistic is worth mentioning.
_MIN_HISTORY_CASES = 3
# Signals get an individual assessment only this far back; older ones still
# count (decayed) toward the overall verdict.
_MAX_ASSESSED_SIGNALS = 10
# Two same-direction signals within this many sessions form a "cluster".
_CLUSTER_RADIUS = 10

# Follow-through thresholds: percent move in the signal's expected direction.
_CONFIRM_PCT = 1.5
_REJECT_PCT = -1.5

# Volume-pressure ratio (avg volume on up-days ÷ down-days) thresholds.
_ACCUMULATION_RATIO = 1.25
_DISTRIBUTION_RATIO = 0.8

# Evidence decay half-life in calendar days (mirrors compute_rating).
_HALF_LIFE_DAYS = 30

# Net-evidence score → verdict boundaries.
_VERDICT_BOUNDS: list[tuple[float, str]] = [
    (1.2, "Strong Buy"),
    (0.4, "Buy"),
    (-0.4, "Hold"),
    (-1.2, "Sell"),
]

# How much each agreement level lets a signal count toward the verdict.
_AGREEMENT_WEIGHT = {"confirm": 1.0, "uncertain": 0.45, "reject": 0.0}


# ── Small numeric helpers ─────────────────────────────────────────────────────


def _pct_change(a: float, b: float) -> float:
    return (b - a) / a * 100.0 if a else 0.0


def _sma(values: Sequence[float], end_idx: int, n: int) -> float | None:
    """Mean of the n values ending at end_idx (inclusive); None if too few."""
    start = end_idx - n + 1
    if start < 0:
        return None
    window = values[start : end_idx + 1]
    return sum(window) / len(window)


def _volume_pressure(
    closes: Sequence[float], volumes: Sequence[float], start: int, end: int
) -> float | None:
    """Avg volume on up-days ÷ avg volume on down-days over bars (start, end].

    > 1 means volume concentrates when price rises (buying / accumulation),
    < 1 when it falls (selling / distribution). None when one side is empty.
    """
    up: list[float] = []
    down: list[float] = []
    for i in range(max(start, 0) + 1, min(end, len(closes) - 1) + 1):
        if closes[i] > closes[i - 1]:
            up.append(volumes[i])
        elif closes[i] < closes[i - 1]:
            down.append(volumes[i])
    if not up or not down:
        return None
    avg_down = sum(down) / len(down)
    if avg_down == 0:
        return None
    return (sum(up) / len(up)) / avg_down


def _trend(closes: Sequence[float], idx: int) -> tuple[str, float]:
    """Trend label at bar idx: last close vs its 20-session average."""
    sma = _sma(closes, idx, _CONTEXT_SMA)
    if sma is None or sma == 0:
        return "sideways", 0.0
    diff = _pct_change(sma, closes[idx])
    if diff > 2.0:
        return "uptrend", diff
    if diff < -2.0:
        return "downtrend", diff
    return "sideways", diff


# ── Historical signal effectiveness on this stock ────────────────────────────


def _historical_success(
    signals: Sequence[VsaSignal],
    idx_of: dict[date, int],
    closes: Sequence[float],
) -> dict[str, tuple[int, int]]:
    """Per signal name: (evaluable occurrences, successes) on this stock.

    Success = price moved in the signal's direction over the next
    ``_HISTORY_FWD_BARS`` sessions. Only occurrences with enough forward data
    are counted, so fresh signals never distort the statistic.
    """
    stats: dict[str, tuple[int, int]] = {}
    for s in signals:
        idx = idx_of.get(s.date)
        if idx is None or idx + _HISTORY_FWD_BARS >= len(closes):
            continue
        move = _pct_change(closes[idx], closes[idx + _HISTORY_FWD_BARS])
        success = move > 0 if s.type == SignalType.BULLISH else move < 0
        count, wins = stats.get(s.signal_name.value, (0, 0))
        stats[s.signal_name.value] = (count + 1, wins + (1 if success else 0))
    return stats


# ── Per-signal assessment ─────────────────────────────────────────────────────


def _assess_signal(
    s: VsaSignal,
    idx: int,
    closes: Sequence[float],
    volumes: Sequence[float],
    history: dict[str, tuple[int, int]],
) -> AiSignalAssessment:
    """Judge one signal by what the chart actually did around it."""
    bullish = s.type == SignalType.BULLISH
    label = s.signal_name.value
    side = "buying" if bullish else "selling"
    bars_after = len(closes) - 1 - idx

    if bars_after < 3:
        agreement = "uncertain"
        comment = (
            f"Only {bars_after} session(s) since this signal — too fresh to judge. "
            f"Watch whether volume now concentrates on "
            f"{'up-days (confirms it)' if bullish else 'down-days (confirms it)'}."
        )
    else:
        horizon = min(_FOLLOW_THROUGH_BARS, bars_after)
        move = _pct_change(closes[idx], closes[idx + horizon])
        directional = move if bullish else -move

        if directional >= _CONFIRM_PCT:
            agreement = "confirm"
            comment = (
                f"Price moved {abs(move):.1f}% {'up' if bullish else 'down'} within "
                f"{horizon} sessions — the professional {side} this signal implies "
                f"followed through."
            )
        elif directional <= _REJECT_PCT:
            agreement = "reject"
            comment = (
                f"Price moved {abs(move):.1f}% against this signal within {horizon} "
                f"sessions — the expected {side} never materialised."
            )
        else:
            agreement = "uncertain"
            pressure = _volume_pressure(closes, volumes, idx, idx + horizon)
            if pressure is not None and (
                pressure > _ACCUMULATION_RATIO
                if bullish
                else pressure < _DISTRIBUTION_RATIO
            ):
                comment = (
                    f"Price went sideways after the signal, but volume concentrated "
                    f"on {'up' if bullish else 'down'}-days — quiet "
                    f"{'accumulation' if bullish else 'distribution'} is possible."
                )
            else:
                comment = (
                    f"No clear follow-through yet: price is roughly flat since the "
                    f"signal and volume shows no decisive {side} pressure."
                )

    count, wins = history.get(label, (0, 0))
    if count >= _MIN_HISTORY_CASES:
        comment += (
            f" Historically on this stock, {label} was followed by the expected "
            f"move {wins / count * 100:.0f}% of the time ({count} cases)."
        )

    return AiSignalAssessment(
        date=s.date, signal_name=label, agreement=agreement, comment=comment
    )


# ── Overall verdict, confidence and narrative ─────────────────────────────────


def _net_score(
    assessed: Sequence[tuple[VsaSignal, AiSignalAssessment]],
    as_of: date,
    trend_label: str,
    pressure: float | None,
) -> float:
    """Fold all evidence into one signed score (positive = bullish)."""
    lam = math.log(2) / _HALF_LIFE_DAYS
    score = 0.0
    for s, a in assessed:
        days_ago = max((as_of - s.date).days, 0)
        decay = math.exp(-lam * days_ago)
        weight = decay * s.strength * _AGREEMENT_WEIGHT[a.agreement]
        score += weight if s.type == SignalType.BULLISH else -weight

    if trend_label == "uptrend":
        score += 0.4
    elif trend_label == "downtrend":
        score -= 0.4

    if pressure is not None:
        if pressure > _ACCUMULATION_RATIO:
            score += 0.3
        elif pressure < _DISTRIBUTION_RATIO:
            score -= 0.3

    return score


def _verdict_for(score: float) -> str:
    for bound, verdict in _VERDICT_BOUNDS:
        if score >= bound:
            return verdict
    return "Strong Sell"


def _confidence(
    assessments: Sequence[AiSignalAssessment], verdict: str, trend_label: str
) -> int:
    """0–100 conviction: more decisive evidence and less conflict = higher."""
    n_confirm = sum(1 for a in assessments if a.agreement == "confirm")
    n_reject = sum(1 for a in assessments if a.agreement == "reject")

    # Share of decisive assessments that point the same way.
    consistency = (n_confirm + 1) / (n_confirm + n_reject + 2)
    evidence = min(1.0, len(assessments) / 6)

    conf = 35 + 30 * consistency + 15 * evidence
    trend_dir = {"uptrend": 1, "downtrend": -1}.get(trend_label, 0)
    verdict_dir = {"Strong Buy": 1, "Buy": 1, "Sell": -1, "Strong Sell": -1}.get(
        verdict, 0
    )
    if trend_dir and trend_dir == verdict_dir:
        conf += 5
    return max(20, min(95, round(conf)))


def _build_summary(
    *,
    display_name: str,
    trend_label: str,
    trend_diff: float,
    window_change: float,
    window_len: int,
    pressure: float | None,
    assessments: Sequence[AiSignalAssessment],
    n_bullish: int,
    n_bearish: int,
    verdict: str,
    confidence: int,
) -> str:
    sentences: list[str] = []

    trend_phrase = {
        "uptrend": "is in an uptrend",
        "downtrend": "is in a downtrend",
    }.get(trend_label, "is moving sideways")
    sentences.append(
        f"{display_name} {trend_phrase}: the last close sits "
        f"{abs(trend_diff):.1f}% {'above' if trend_diff >= 0 else 'below'} its "
        f"20-session average, and the price is "
        f"{'up' if window_change >= 0 else 'down'} {abs(window_change):.1f}% over "
        f"the analysed {window_len} sessions."
    )

    if pressure is None:
        sentences.append(
            "Recent volume gives no clear reading of buying or selling pressure."
        )
    elif pressure > _ACCUMULATION_RATIO:
        sentences.append(
            f"Volume has been about {pressure:.1f}× heavier on up-days than on "
            f"down-days recently — in VSA terms a sign of professional buying "
            f"(accumulation)."
        )
    elif pressure < _DISTRIBUTION_RATIO:
        sentences.append(
            f"Volume has been noticeably heavier on down-days recently (up/down "
            f"ratio {pressure:.1f}) — in VSA terms a sign of professional selling "
            f"(distribution)."
        )
    else:
        sentences.append(
            "Volume is fairly balanced between up-days and down-days, so neither "
            "side is clearly in control."
        )

    if assessments:
        n_confirm = sum(1 for a in assessments if a.agreement == "confirm")
        n_reject = sum(1 for a in assessments if a.agreement == "reject")
        sentences.append(
            f"The rule engine found {n_bullish} bullish and {n_bearish} bearish "
            f"signal(s) in this window; checking what price and volume did "
            f"afterwards confirms {n_confirm} and rejects {n_reject} of the "
            f"{len(assessments)} most recent."
        )
    else:
        sentences.append(
            "The rule engine found no VSA signals in this window, so the read "
            "rests on trend and volume behaviour alone."
        )

    qualifier = " though the picture is mixed, so conviction is low" if confidence < 45 else ""
    sentences.append(f"Taken together, the evidence points to {verdict}{qualifier}.")

    return " ".join(sentences)


def _build_observations(
    *,
    trend_label: str,
    trend_diff: float,
    pressure: float | None,
    closes: Sequence[float],
    history: dict[str, tuple[int, int]],
    assessed: Sequence[tuple[VsaSignal, AiSignalAssessment]],
    rating: int,
) -> list[str]:
    obs: list[str] = []

    obs.append(
        f"Trend: {trend_label} — price {abs(trend_diff):.1f}% "
        f"{'above' if trend_diff >= 0 else 'below'} the 20-session average."
    )

    if pressure is not None:
        obs.append(
            f"Volume pressure: up-day volume is {pressure:.2f}× down-day volume "
            f"over the last {_CONTEXT_SMA} sessions."
        )

    if len(closes) >= _CONTEXT_SMA:
        recent = closes[-_CONTEXT_SMA:]
        obs.append(
            f"Nearest support ≈ {min(recent):.2f} PLN, resistance ≈ "
            f"{max(recent):.2f} PLN (20-session low/high)."
        )

    # The signal type with the best track record on this stock, if any has
    # enough history to be meaningful.
    reliable = {k: (c, w) for k, (c, w) in history.items() if c >= _MIN_HISTORY_CASES}
    if reliable:
        best, (count, wins) = max(
            reliable.items(), key=lambda kv: kv[1][1] / kv[1][0]
        )
        obs.append(
            f"Best track record on this stock: {best} — the expected move followed "
            f"in {wins / count * 100:.0f}% of {count} historical cases."
        )

    # Clustered same-direction signals reinforce each other in VSA.
    recent_assessed = [s for s, _ in assessed[-4:]]
    for a, b in zip(recent_assessed, recent_assessed[1:], strict=False):
        if a.type == b.type and abs((b.date - a.date).days) <= _CLUSTER_RADIUS * 2:
            direction = "bullish" if a.type == SignalType.BULLISH else "bearish"
            obs.append(
                f"Recent {direction} signals cluster together ({a.date} and "
                f"{b.date}) — clustered signals reinforce each other in VSA."
            )
            break

    obs.append(f"Rule-engine VSA rating for comparison: {rating}/100.")
    return obs


# ── Public entry point ────────────────────────────────────────────────────────


def analyze_stock(
    *,
    ticker: str,
    name: str | None,
    quotes: Sequence[StooqDailyQuote],
    signals: Sequence[VsaSignal],
    rating: int,
) -> AiAnalysisResponse:
    """Produce the full insight analysis for one stock.

    ``quotes`` must be in date order and non-empty; ``signals`` are the
    rule-engine detections for the same window (any VsaConfig). ``rating`` is
    the rule engine's 0–100 rating, included for comparison.
    """
    if not quotes:
        raise ValueError("analyze_stock requires at least one quote.")

    closes = [float(q.close) for q in quotes]
    volumes = [float(q.volume) for q in quotes]
    idx_of = {q.date: i for i, q in enumerate(quotes)}
    last_idx = len(quotes) - 1
    as_of = quotes[last_idx].date

    trend_label, trend_diff = _trend(closes, last_idx)
    pressure = _volume_pressure(
        closes, volumes, last_idx - _CONTEXT_SMA, last_idx
    )
    history = _historical_success(signals, idx_of, closes)

    # Individually assess the most recent signals (oldest → newest).
    recent = [s for s in signals if s.date in idx_of][-_MAX_ASSESSED_SIGNALS:]
    assessed: list[tuple[VsaSignal, AiSignalAssessment]] = [
        (s, _assess_signal(s, idx_of[s.date], closes, volumes, history))
        for s in recent
    ]
    assessments = [a for _, a in assessed]

    score = _net_score(assessed, as_of, trend_label, pressure)
    verdict = _verdict_for(score)
    confidence = _confidence(assessments, verdict, trend_label)

    summary = _build_summary(
        display_name=name or ticker.upper(),
        trend_label=trend_label,
        trend_diff=trend_diff,
        window_change=_pct_change(closes[0], closes[-1]),
        window_len=len(quotes),
        pressure=pressure,
        assessments=assessments,
        n_bullish=sum(1 for s in recent if s.type == SignalType.BULLISH),
        n_bearish=sum(1 for s in recent if s.type == SignalType.BEARISH),
        verdict=verdict,
        confidence=confidence,
    )

    observations = _build_observations(
        trend_label=trend_label,
        trend_diff=trend_diff,
        pressure=pressure,
        closes=closes,
        history=history,
        assessed=assessed,
        rating=rating,
    )

    return AiAnalysisResponse(
        ticker=ticker.upper(),
        as_of=as_of,
        verdict=verdict,  # type: ignore[arg-type]
        confidence=confidence,
        summary=summary,
        signal_assessments=list(reversed(assessments)),  # newest first for the UI
        key_observations=observations,
        engine=ENGINE_VERSION,
    )
