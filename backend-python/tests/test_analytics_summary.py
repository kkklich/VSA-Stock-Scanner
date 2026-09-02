"""Tests for the consolidated analytics-opinion summary.

Covers the pure consensus maths (``_consensus`` + the lean/stance helpers),
the human list-join, and an integration pass over ``build_analytics_summary``
that checks it fuses the real engines into a valid, self-consistent payload.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analysis.analytics_summary import (
    ENGINE_VERSION,
    _consensus,
    _Directional,
    _join,
    _method_lean,
    _stance_from_lean,
    build_analytics_summary,
)
from app.analysis.methods import method_ids
from app.analysis.vsa import compute_rating, detect_signals
from app.models import AnalyticsOpinionSource, StooqDailyQuote

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(closes: list[float], end: date | None = None) -> list[StooqDailyQuote]:
    if end is None:
        end = date.today()
    n = len(closes)
    return [_quote(end - timedelta(days=n - 1 - i), closes[i]) for i in range(n)]


def _d(lean: float, weight: float = 1.0) -> _Directional:
    """A directional source carrying just the lean/weight the consensus uses."""
    src = AnalyticsOpinionSource(
        key="x",
        label="X",
        kind="direction",
        stance=_stance_from_lean(lean),
        headline="",
        detail="",
    )
    return _Directional(source=src, lean=lean, weight=weight)


# ── Lean / stance helpers ──────────────────────────────────────────────────────


class TestLeanHelpers:
    def test_method_lean_is_bullish_or_neutral_only(self) -> None:
        assert _method_lean(50) == 0.0  # neutral middle
        assert _method_lean(100) == 1.0  # fully bullish
        assert _method_lean(75) == 0.5
        assert _method_lean(30) == 0.0  # below 50 is "absent", never bearish

    def test_stance_from_lean(self) -> None:
        assert _stance_from_lean(0.5) == "bullish"
        assert _stance_from_lean(-0.5) == "bearish"
        assert _stance_from_lean(0.0) == "neutral"
        assert _stance_from_lean(0.1) == "neutral"  # inside the epsilon band


# ── Consensus ───────────────────────────────────────────────────────────────


class TestConsensus:
    def test_unanimous_bullish(self) -> None:
        stance, agreement, mean = _consensus([_d(1.0), _d(0.5), _d(0.8)])
        assert stance == "bullish"
        assert agreement == 100
        assert mean > 0

    def test_unanimous_bearish(self) -> None:
        stance, agreement, _ = _consensus([_d(-1.0), _d(-0.5)])
        assert stance == "bearish"
        assert agreement == 100

    def test_even_split_is_mixed(self) -> None:
        stance, agreement, _ = _consensus([_d(1.0), _d(-1.0)])
        assert stance == "mixed"
        assert agreement == 50

    def test_majority_bullish_with_one_dissenter(self) -> None:
        # 2 bullish, 1 bearish, equal weight → mean positive, agreement 67 (not
        # below the mixed threshold) → a bullish read, not "mixed".
        stance, agreement, _ = _consensus([_d(1.0), _d(1.0), _d(-1.0)])
        assert stance == "bullish"
        assert agreement == 67

    def test_all_neutral_is_neutral(self) -> None:
        stance, agreement, mean = _consensus([_d(0.0), _d(0.1)])
        assert stance == "neutral"
        assert agreement == 100  # nothing to disagree about
        assert mean == pytest.approx(0.05)

    def test_no_voting_sources(self) -> None:
        # Every source unavailable (weight 0) → neutral, full agreement.
        stance, agreement, mean = _consensus([_d(1.0, weight=0.0)])
        assert stance == "neutral"
        assert agreement == 100
        assert mean == 0.0

    def test_unavailable_sources_do_not_vote(self) -> None:
        # A weight-0 bearish source must not turn a bullish consensus mixed.
        stance, _, _ = _consensus([_d(1.0), _d(0.6), _d(-1.0, weight=0.0)])
        assert stance == "bullish"


# ── Human list join ─────────────────────────────────────────────────────────


class TestJoin:
    def test_join_variants(self) -> None:
        assert _join([]) == ""
        assert _join(["A"]) == "A"
        assert _join(["A", "B"]) == "A and B"
        assert _join(["A", "B", "C"]) == "A, B and C"


# ── Integration over the real engines ──────────────────────────────────────


class TestBuildSummary:
    def test_uptrend_payload_is_valid_and_consistent(self) -> None:
        bars = _series([100.0 + i * 0.5 for i in range(300)])
        signals = detect_signals(bars)
        res = build_analytics_summary(
            ticker="up", name="Uptrend Co", quotes=bars, signals=signals
        )

        assert res.ticker == "UP"
        assert res.name == "Uptrend Co"
        assert res.as_of == bars[-1].date
        assert res.engine == ENGINE_VERSION
        assert res.stance in ("bullish", "bearish", "neutral", "mixed")
        assert 0 <= res.agreement <= 100
        assert res.headline and res.summary  # non-empty narrative

        by_key = {s.key: s for s in res.sources}
        # Every registered method is represented, plus AI Insight + Trust Score.
        for mid in method_ids():
            assert mid in by_key
        assert "aiInsight" in by_key
        assert by_key["trustScore"].kind == "reliability"

        # The VSA source's score is exactly the rule engine's rating.
        rating = compute_rating(signals, bars[-1].date)
        assert by_key["vsa"].headline.endswith(f"{rating}/100")

        # A steady uptrend fires Minervini's full template and is not bearish.
        assert by_key["minervini"].stance == "bullish"
        assert by_key["minervini"].fired_recently is True
        assert res.stance != "bearish"

    def test_short_history_marks_minervini_unavailable(self) -> None:
        # ~80 bars: enough for VSA, too few for Minervini's 200-day MA.
        bars = _series([100.0 + (i % 5) for i in range(80)])
        signals = detect_signals(bars)
        res = build_analytics_summary(
            ticker="sh", name=None, quotes=bars, signals=signals
        )
        by_key = {s.key: s for s in res.sources}
        assert by_key["minervini"].stance == "unavailable"
        # Name falls back to the upper-cased ticker in the narrative.
        assert "SH" in res.headline
        # An unavailable method must not break the payload.
        assert res.stance in ("bullish", "bearish", "neutral", "mixed")

    def test_empty_quotes_raises(self) -> None:
        with pytest.raises(ValueError):
            build_analytics_summary(ticker="x", name=None, quotes=[], signals=[])
