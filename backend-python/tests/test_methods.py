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


def _flat_then_rise(
    flat_n: int = 260, rise_n: int = 120, slope: float = 0.8
) -> list[StooqDailyQuote]:
    """A long flat base then a clean sustained rise.

    The trend template is OFF through the base (the 200-day MA is flat, price is
    not yet 30% above its low) and turns ON partway up the rise — a genuine
    off->on transition that sits INSIDE the evaluated window, unlike a series
    that is already rising at the left edge (whose true entry predates the data).
    """
    closes = [100.0] * flat_n + [100.0 + (i + 1) * slope for i in range(rise_n)]
    return _series(closes)


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

    def test_breakout_is_registered_after_minervini(self) -> None:
        ids = method_ids()
        assert "breakout" in ids
        # order: vsa (10) < minervini (20) < breakout (30)
        assert ids.index("breakout") > ids.index("minervini")


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
        # Fewer than a full 52-week window → cannot be judged.
        result = get_method("minervini").evaluate(_series([100.0] * 50))
        assert result.available is False
        assert result.fired is False

    def test_rule8_folds_rs_rank_into_score_when_provided(self) -> None:
        # A full 7/7 structural template. With a high RS rank (rule 8 passes)
        # the score is 8/8; with a low RS rank it is 7/8 — but ``fired`` still
        # tracks the structural template (RS rank is only known cross-sectionally
        # for the latest session, so it modulates the score, not the marker).
        rise = _series([100.0 + i * 0.5 for i in range(300)])
        strong = get_method("minervini").evaluate(rise, rs_rank=90.0)
        assert strong.score == 100
        assert strong.detail == "8/8 rules"
        assert strong.fired is True

        weak = get_method("minervini").evaluate(rise, rs_rank=20.0)
        assert weak.score == 88  # 7 of 8
        assert weak.detail == "7/8 rules"
        assert weak.fired is True  # structural template still on

    def test_no_rs_rank_falls_back_to_structural(self) -> None:
        # Standalone (no universe) → 7 structural rules, and the label says so.
        result = get_method("minervini").evaluate(
            _series([100.0 + i * 0.5 for i in range(300)])
        )
        assert result.score == 100
        assert result.detail == "7/7 structural"

    def test_full_52w_window_required(self) -> None:
        # Rules 6-7 need a genuine 52-week window (~252 sessions). A stock with
        # only ~240 bars — enough for the moving averages but not a real year —
        # must be unavailable, not judged on a truncated window (its 3-month
        # high must never be read as a fresh 52-week high). Just over the
        # threshold (~260 bars, the standard production fetch) it evaluates the
        # last bar normally.
        assert get_method("minervini").evaluate(
            _series([100.0 + i * 0.5 for i in range(240)])
        ).available is False
        just_enough = get_method("minervini").evaluate(
            _series([100.0 + i * 0.5 for i in range(260)])
        )
        assert just_enough.available is True
        assert just_enough.fired is True

    def test_signals_mark_template_turning_on(self) -> None:
        # A base then a rise turns the full template on partway up → exactly one
        # "turns on" marker (a genuine off->on transition), tagged bullish.
        signals = get_method("minervini").signals(_flat_then_rise())
        assert len(signals) == 1
        assert all(s.label == "Trend Template" and s.type == "Bullish" for s in signals)
        # Oldest-first, matching the chart's expectation.
        assert signals == sorted(signals, key=lambda s: s.date)

    def test_signals_no_marker_when_already_on_at_left_edge(self) -> None:
        # A steady rise that is already a full template at the first evaluable
        # bar has its true entry BEFORE the window — so no fresh marker is
        # emitted (the left-edge state is seeded, not reported as an entry).
        signals = get_method("minervini").signals(
            _series([100.0 + i * 0.5 for i in range(300)])
        )
        assert signals == []

    def test_signals_empty_in_a_downtrend(self) -> None:
        signals = get_method("minervini").signals(
            _series([250.0 - i * 0.5 for i in range(300)])
        )
        assert signals == []

    def test_signals_empty_on_short_history(self) -> None:
        assert get_method("minervini").signals(_series([100.0] * 50)) == []


# ── Volume Breakout ───────────────────────────────────────────────────────────


def _breakout_series(
    n_base: int = 200,
    breakout_close: float = 106.0,
    breakout_volume: int = 600_000,
    end: date | None = None,
) -> list[StooqDailyQuote]:
    """A long, flat base at 100 on 200k volume, then one final breakout bar.

    The last bar closes at a new high (default 106 vs the base's ~101 highs) on
    expanded volume — a volume-confirmed breakout on the most recent session.
    """
    if end is None:
        end = date.today()
    rows = [(100.0, 200_000)] * n_base + [(breakout_close, breakout_volume)]
    n = len(rows)
    return [
        _quote(end - timedelta(days=n - 1 - i), c, v) for i, (c, v) in enumerate(rows)
    ]


class TestVolumeBreakout:
    def test_breakout_fires_on_volume_expansion_to_new_high(self) -> None:
        result = get_method("breakout").evaluate(_breakout_series())
        assert result.available is True
        assert result.fired is True
        assert result.days_since == 0
        assert result.score >= 60  # good posture on the breakout bar
        assert result.detail and result.detail.startswith("Breakout")

    def test_new_high_without_volume_does_not_fire(self) -> None:
        # Same new-high close, but volume stays at the base level → no breakout,
        # even though the price posture still scores well.
        result = get_method("breakout").evaluate(
            _breakout_series(breakout_volume=200_000)
        )
        assert result.available is True
        assert result.fired is False
        assert result.days_since == 999  # NEVER_FIRED

    def test_downtrend_does_not_fire_and_scores_low(self) -> None:
        result = get_method("breakout").evaluate(
            _series([250.0 - i * 0.5 for i in range(300)])
        )
        assert result.available is True
        assert result.fired is False
        # A downtrend must not lean bullish in the analytics summary (score <= 50).
        assert result.score < 50

    def test_no_base_running_move_does_not_fire(self) -> None:
        # A stock already running vertically (a wide, steep advance — no tight
        # base) that pokes a new high on volume must NOT count as a base
        # breakout: the prior 50 sessions span far more than a proper base.
        end = date.today()
        closes = (
            [100.0] * 150
            + [100.0 + (i + 1) * 1.5 for i in range(49)]  # steep run 101.5..173.5
        )
        closes.append(closes[-1] + 4.0)  # a new-high "breakout" on top of the run
        n = len(closes)
        rows = [
            _quote(end - timedelta(days=n - 1 - i), c, 600_000 if i == n - 1 else 200_000)
            for i, c in enumerate(closes)
        ]
        result = get_method("breakout").evaluate(rows)
        assert result.available is True
        assert result.fired is False  # base too deep (a vertical run, no base)

    def test_volume_rising_into_pivot_does_not_fire(self) -> None:
        # A tight flat base, but volume was RISING into the pivot rather than
        # drying up — the volume-dry-up precondition (measured on the bar before
        # the breakout) fails, so it is not a genuine coiled base breakout.
        end = date.today()
        rows_spec = (
            [(100.0, 200_000)] * 190
            + [(100.0, 400_000)] * 10  # volume expands through the last 10 base bars
            + [(106.0, 900_000)]       # new-high, high-volume, strong-close bar
        )
        n = len(rows_spec)
        rows = [
            _quote(end - timedelta(days=n - 1 - i), c, v)
            for i, (c, v) in enumerate(rows_spec)
        ]
        result = get_method("breakout").evaluate(rows)
        assert result.available is True
        assert result.fired is False  # no volume dry-up into the pivot

    def test_short_history_is_unavailable(self) -> None:
        result = get_method("breakout").evaluate(_series([100.0] * 50))
        assert result.available is False
        assert result.fired is False

    def test_signals_mark_the_breakout(self) -> None:
        signals = get_method("breakout").signals(_breakout_series())
        assert len(signals) >= 1
        assert all(
            s.label == "Volume Breakout" and s.type == "Bullish" for s in signals
        )
        assert signals == sorted(signals, key=lambda s: s.date)  # oldest first

    def test_signals_empty_in_a_downtrend(self) -> None:
        assert (
            get_method("breakout").signals(
                _series([250.0 - i * 0.5 for i in range(300)])
            )
            == []
        )

    def test_signals_empty_on_short_history(self) -> None:
        assert get_method("breakout").signals(_series([100.0] * 50)) == []


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

    def test_relative_strength_rank_flows_into_minervini(self) -> None:
        # Two full-template uptrends of different steepness. The steeper one has
        # the higher relative strength, so it ranks in the top percentile and
        # Minervini's rule 8 lifts it to a full 8/8; the weaker one ranks bottom
        # and scores 7/8. This proves the cross-sectional RS pre-pass threads a
        # per-stock rs_rank into each method's evaluate.
        companies = [
            GpwCompany(ticker="aaa", name="Strong", sector="Tech", market_cap=None),
            GpwCompany(ticker="bbb", name="Weak", sector="Tech", market_cap=None),
        ]
        client = _Client({
            "aaa": _series([100.0 + i * 0.8 for i in range(300)]),
            "bbb": _series([100.0 + i * 0.3 for i in range(300)]),
        })
        rows = asyncio.run(
            compute_ranking(
                companies=companies,
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )
        by_ticker = {r.ticker: r for r in rows}
        strong = by_ticker["AAA"].method_results["minervini"]
        weak = by_ticker["BBB"].method_results["minervini"]
        assert strong.detail == "8/8 rules" and strong.score == 100
        assert weak.detail == "7/8 rules" and weak.score == 88


class TestRelativeStrength:
    def test_raw_none_on_short_history(self) -> None:
        from app.services.ranking_service import _relative_strength_raw

        assert _relative_strength_raw(_series([100.0] * 50)) is None

    def test_raw_higher_for_stronger_performer(self) -> None:
        from app.services.ranking_service import _relative_strength_raw

        strong = _relative_strength_raw(_series([100.0 + i * 0.8 for i in range(300)]))
        weak = _relative_strength_raw(_series([100.0 + i * 0.3 for i in range(300)]))
        assert strong is not None and weak is not None
        assert strong > weak

    def test_percentile_ranks_span_0_to_100(self) -> None:
        from app.services.ranking_service import _percentile_ranks

        ranks = _percentile_ranks({"low": 1.0, "mid": 5.0, "high": 9.0})
        assert ranks["low"] == 0.0
        assert ranks["high"] == 100.0
        assert 0.0 < ranks["mid"] < 100.0

    def test_percentile_ranks_need_at_least_two(self) -> None:
        from app.services.ranking_service import _percentile_ranks

        # A single stock cannot be ranked cross-sectionally → no rank.
        assert _percentile_ranks({"solo": 3.0}) == {}
