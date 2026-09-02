"""VSA as a first-class trading method.

This wraps the existing Volume Spread Analysis engine (``app/analysis/vsa.py``)
in the generic ``TradingMethod`` interface so it appears in the same selectable
list as every other method (roadmap 23a: "VSA is one method in the same list").

The method's ``score`` is the 0–100 VSA rating; a "fired" event is the most
recent *bullish* structure (Spring, Successful Test, Sign of Strength). The
bearish side still shapes the rating but is not treated as a long entry.

Note: the ranking service builds the VSA method result inline from the rating
and signals it already computes for the row (see ``ranking_service``), so the
VSA column always equals the row's Rating/Signal columns *exactly*. This
``evaluate`` is the standalone path (used by tests and any generic caller); it
reproduces the same numbers, anchoring its analysis window to the last bar.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    register_method,
)
from app.analysis.vsa import (
    SignalType,
    VsaConfig,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.models import StooqDailyQuote

# VSA analysis window (calendar days) — identical to the ranking's slice, so a
# standalone evaluation reproduces the row's rating.
_ANALYSIS_DAYS = 120
_MIN_BARS = 25


def vsa_result_from_signals(
    signals: Sequence,
    rating: int,
    verdict: str,
    as_of,
) -> MethodResult:
    """Build the VSA ``MethodResult`` from values the ranking already computed.

    Reused by ``ranking_service`` so no VSA work is done twice and the VSA
    column can never drift from the Rating column. ``signals`` is the list of
    ``VsaSignal`` for the row; recency is measured from the last *bullish*
    signal (a long entry), while ``rating``/``verdict`` reflect both sides.
    """
    bullish_dates = [s.date for s in signals if s.type == SignalType.BULLISH]
    last_bull = max(bullish_dates, default=None)
    days_since = (as_of - last_bull).days if last_bull is not None else NEVER_FIRED
    return MethodResult(
        score=rating,
        days_since=days_since,
        fired=days_since == 0,
        detail=verdict,
        available=True,
    )


@register_method
class VsaMethod(TradingMethod):
    id = "vsa"
    order = 10
    name = "VSA rating"
    description = (
        "Volume Spread Analysis reads each bar's spread, the close's position "
        "within it and volume to judge whether professional money is "
        "accumulating (strength) or distributing (weakness). The score is the "
        "0–100 VSA rating with time decay; a recent example means a bullish "
        "structure — Spring, Successful Test or Sign of Strength — fired lately."
    )
    source = "Tom Williams — Master the Markets (VSA, after Richard Wyckoff)"
    source_url = None

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")
        last = bars[-1].date
        recent = [q for q in bars if q.date >= last - timedelta(days=_ANALYSIS_DAYS)]
        if len(recent) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")
        signals = detect_signals(recent, config)
        rating = compute_rating(signals, last)
        verdict, _ = verdict_from_signals(signals, last)
        return vsa_result_from_signals(signals, rating, verdict, last)

    def signals(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> list[MethodSignal]:
        """Every detected VSA structure across ``bars`` as chart markers.

        Runs the same detection as the ``/signals`` chart endpoint over the
        whole supplied window (not just the 120-day rating slice), so the
        overlay markers span the full chart. Both sides are returned — bullish
        (Spring / Successful Test / SOS) and bearish (Upthrust / No Demand /
        SOW) — so the chart shows the complete VSA reading.
        """
        if len(bars) < _MIN_BARS:
            return []
        return [
            MethodSignal(date=s.date, label=s.signal_name.value, type=s.type.value)
            for s in detect_signals(bars, config)
        ]
