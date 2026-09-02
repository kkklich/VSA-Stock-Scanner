"""Tests for the pluggable trading-method framework (app/analysis/methods).

Covers the registry, the two shipped methods (VSA + Minervini Trend Template),
the combined cross-method score, and that the ranking attaches per-method
results to every row.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.analysis.methods import get_method, method_ids
from app.analysis.methods.base import MethodResult
from app.models import GpwCompany, StooqDailyQuote
from app.routers.stocks import _with_combined_score
from app.services.cache import TTLCache
from app.services.ranking_service import compute_ranking

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


# ── Registry ──────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_vsa_and_minervini_are_registered_in_order(self) -> None:
        ids = method_ids()
        assert ids[0] == "vsa"  # VSA is a first-class member, listed first
        assert "minervini" in ids

    def test_get_method_and_metadata(self) -> None:
        m = get_method("minervini")
        assert m is not None
        assert m.name and m.description and m.source  # self-describing
        assert m.direction == "Bullish"  # long-only
        assert get_method("does-not-exist") is None

    def test_ids_are_unique(self) -> None:
        ids = method_ids()
        assert len(ids) == len(set(ids))


# ── Minervini Trend Template ──────────────────────────────────────────────────


class TestMinervini:
    def test_strong_uptrend_fires_full_template(self) -> None:
        # A long, steady rise puts price above rising 50/150/200 MAs and near
        # the high → all seven structural rules pass.
        result = get_method("minervini").evaluate(
            _series([100.0 + i * 0.5 for i in range(300)])
        )
        assert result.available is True
        assert result.fired is True
        assert result.score == 100
        assert result.days_since == 0

    def test_downtrend_does_not_fire(self) -> None:
        # A steady decline: price below its MAs, at/near the low → the template
        # cannot fire, and the score is well short of 100.
        result = get_method("minervini").evaluate(
            _series([250.0 - i * 0.5 for i in range(300)])
        )
        assert result.available is True
        assert result.fired is False
        assert result.score < 100

    def test_short_history_is_unavailable(self) -> None:
        # Fewer than a 200-day MA plus its trend lookback → cannot be judged.
        result = get_method("minervini").evaluate(_series([100.0] * 50))
        assert result.available is False
        assert result.fired is False

    def test_signals_mark_template_turning_on(self) -> None:
        # A steady rise turns the full template on and keeps it on → exactly one
        # "turns on" marker, tagged as a bullish Trend Template.
        signals = get_method("minervini").signals(
            _series([100.0 + i * 0.5 for i in range(300)])
        )
        assert len(signals) >= 1
        assert all(s.label == "Trend Template" and s.type == "Bullish" for s in signals)
        # Oldest-first, matching the chart's expectation.
        assert signals == sorted(signals, key=lambda s: s.date)

    def test_signals_empty_in_a_downtrend(self) -> None:
        signals = get_method("minervini").signals(
            _series([250.0 - i * 0.5 for i in range(300)])
        )
        assert signals == []

    def test_signals_empty_on_short_history(self) -> None:
        assert get_method("minervini").signals(_series([100.0] * 50)) == []


# ── VSA method wrapper ────────────────────────────────────────────────────────


class TestVsaMethod:
    def test_available_on_enough_history(self) -> None:
        result = get_method("vsa").evaluate(_series([100.0 + (i % 5) for i in range(80)]))
        assert result.available is True
        assert 0 <= result.score <= 100

    def test_unavailable_on_tiny_history(self) -> None:
        result = get_method("vsa").evaluate(_series([100.0, 101.0, 102.0]))
        assert result.available is False

    def test_signals_wrap_detection_over_the_full_window(self) -> None:
        # The VSA overlay is exactly the engine's detected signals across the
        # whole window (what the /signals chart endpoint draws), each carrying a
        # bullish/bearish type the chart can colour.
        from app.analysis.vsa import detect_signals

        bars = _series([100.0 + (i % 7) * 2 for i in range(120)])
        overlay = get_method("vsa").signals(bars)
        assert len(overlay) == len(detect_signals(bars))
        assert all(s.type in ("Bullish", "Bearish") and s.label for s in overlay)

    def test_signals_empty_on_tiny_history(self) -> None:
        assert get_method("vsa").signals(_series([100.0, 101.0, 102.0])) == []


# ── Combined cross-method score ───────────────────────────────────────────────


def _row_with(results: dict[str, MethodResult]):
    """Build a minimal ranking row carrying the given method results."""
    from app.models import MethodResultModel, StockRankingItem

    return StockRankingItem(
        ticker="X",
        name="X",
        last_price=1.0,
        price_change_pct=0.0,
        current_rating=50,
        rating_change=0,
        last_signal="Hold",
        days_since_signal=999,
        sparkline=[1.0],
        volume=1,
        method_results={
            k: MethodResultModel(
                method_id=k,
                score=v.score,
                days_since=v.days_since,
                fired=v.fired,
                available=v.available,
            )
            for k, v in results.items()
        },
    )


class TestCombinedScore:
    def test_mean_of_all_methods(self) -> None:
        row = _row_with(
            {"vsa": MethodResult(score=40), "minervini": MethodResult(score=100)}
        )
        assert _with_combined_score(row, None).combined_score == 70

    def test_selected_subset_only(self) -> None:
        row = _row_with(
            {"vsa": MethodResult(score=40), "minervini": MethodResult(score=100)}
        )
        assert _with_combined_score(row, ["vsa"]).combined_score == 40
        assert _with_combined_score(row, ["minervini"]).combined_score == 100

    def test_unavailable_methods_are_skipped(self) -> None:
        row = _row_with(
            {
                "vsa": MethodResult(score=60),
                "minervini": MethodResult.unavailable(),
            }
        )
        # Minervini unavailable → combined is just VSA's score.
        assert _with_combined_score(row, None).combined_score == 60

    def test_none_when_no_selected_method_available(self) -> None:
        row = _row_with({"vsa": MethodResult.unavailable()})
        assert _with_combined_score(row, ["vsa"]).combined_score is None


# ── Ranking integration ───────────────────────────────────────────────────────


class _Client:
    def __init__(self, by: dict[str, list[StooqDailyQuote]]) -> None:
        self._by = by

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        rows = self._by.get(ticker, [])
        if from_date is not None:
            rows = [q for q in rows if q.date >= from_date]
        return rows


class TestRankingAttachesMethods:
    def test_every_row_carries_all_method_results(self) -> None:
        company = GpwCompany(ticker="up", name="Uptrend", sector="Tech", market_cap=None)
        client = _Client({"up": _series([100.0 + i * 0.5 for i in range(300)])})
        rows = asyncio.run(
            compute_ranking(
                companies=[company],
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )
        assert len(rows) == 1
        results = rows[0].method_results
        assert set(results) == set(method_ids())
        # VSA's method score equals the row's headline VSA rating exactly.
        assert results["vsa"].score == rows[0].current_rating
        # The strong uptrend fires the full Minervini template.
        assert results["minervini"].fired is True
