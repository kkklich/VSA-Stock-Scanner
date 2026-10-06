"""Tests for the Pocket Pivot method (app/analysis/methods/pocket_pivot.py).

Covers the complete setup, one fixture per rule it can fail on, the fail-closed
volume test, recency and the posture score, the ``signals`` overlay (including
that it never looks ahead and agrees with ``evaluate`` bar for bar), the exact
close-against-average test (a frozen price is level with its averages, not
above them), the guards, and a real GPW pocket pivot — XTB on 2026-07-01, a
pivot again the next day — with two real days nearby that it must refuse.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.analysis.methods import get_method, method_ids
from app.analysis.methods import pocket_pivot as P
from app.analysis.methods.base import NEVER_FIRED, TradingMethod
from app.models import StooqDailyQuote
from tests.data_xtb_2026 import EXTENDED_DAY, PIVOT_DAY, WEDGE_DAY, xtb_daily_bars

# ── Fixtures ──────────────────────────────────────────────────────────────────

_FIRST_DAY = date(2025, 1, 6)  # a Monday


def _weekdays(n: int) -> list[date]:
    """``n`` consecutive Monday-to-Friday sessions from ``_FIRST_DAY``."""
    out: list[date] = []
    d = _FIRST_DAY
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bars(rows: list[tuple[float, float, float, float, int]]) -> list[StooqDailyQuote]:
    return [
        StooqDailyQuote(
            date=d,
            open=Decimal(str(round(o, 4))),
            high=Decimal(str(round(h, 4))),
            low=Decimal(str(round(low, 4))),
            close=Decimal(str(round(c, 4))),
            volume=v,
        )
        for d, (o, h, low, c, v) in zip(_weekdays(len(rows)), rows, strict=True)
    ]


def _pp_rows(
    *,
    downtrend: bool = False,
    run_len: int = 230,
    base_volume: int = 100_000,
    wedge: bool = False,
    pullback_days: int = 5,
    pullback_volume: int = 50_000,
    pivot_volume: int = 150_000,
    pivot_up: bool = True,
    extended: bool = False,
    trailing: int = 0,
) -> list[tuple[float, float, float, float, int]]:
    """A steady trend, a quiet pull-back onto the 10-day line, then the pivot day.

    Every keyword breaks exactly one of the six firing rules, so a test can
    show which gate did the rejecting:

    * ``pivot_up``        — rule 1 (an up day)
    * ``pivot_volume``    — rule 2 (at least the largest down-day volume)
    * ``downtrend``       — rule 3 (above the 50- and 200-day averages)
    * ``extended``        — rule 4 (up off / through the 10- or 50-day line)
    * ``pullback_volume`` — rule 5 (quiet volume going in)
    * ``wedge``           — rule 6 (no upward wedge into the pivot)
    * ``pullback_days``   — how long the drift into the pivot lasts; ten days
                            on ``pullback_volume=0`` leave rule 2's whole window
                            without a traded down day (its fail-closed case)
    * ``trailing``        — quiet sessions after the pivot, for recency
    """
    rows: list[tuple[float, float, float, float, int]] = []
    start, end = (140.0, 100.0) if downtrend else (60.0, 100.0)
    prev = start
    # The trend: a steady slope with an alternating wiggle, so every other
    # session is a down day carrying ``base_volume``.
    for i in range(run_len):
        c = start + (end - start) * i / (run_len - 1) + (0.4 if i % 2 == 0 else -0.4)
        rows.append((prev, c + 0.5, c - 0.5, c, base_volume))
        prev = c
    top = prev

    # Five sessions (``pullback_days``) into the pivot: a quiet drift down (the
    # book's picture), or, with ``wedge``, a quiet drift UP on rising lows.
    for _ in range(pullback_days):
        c = prev + (0.3 if wedge else -0.4)
        rows.append((prev, max(prev, c) + 0.2, c - 0.5, c, pullback_volume))
        prev = c

    # The pivot day: up from its low under the 10-day line to above the top
    # of the pull-back — or, with ``extended``, a gap far above both lines.
    if extended:
        pivot = (top + 4.0, top + 6.5, top + 4.0, top + 6.0, pivot_volume)
    else:
        close = max(top, prev) + 0.5 if pivot_up else prev - 0.1
        pivot = (prev, max(close, prev) + 0.3, min(prev, top) - 3.0, close, pivot_volume)
    rows.append(pivot)
    prev = pivot[3]

    # Quiet sessions after it: light up days, slightly heavier down days, so
    # none of them is a pocket pivot of its own.
    for i in range(trailing):
        c = prev + (0.2 if i % 2 == 0 else -0.2)
        rows.append((prev, max(prev, c) + 0.3, min(prev, c) - 0.3, c,
                     40_000 if c > prev else 60_000))
        prev = c
    return rows


def _pp_bars(**kwargs: Any) -> list[StooqDailyQuote]:
    return _bars(_pp_rows(**kwargs))


def _flat_bars(prices: list[Decimal], volumes: list[int]) -> list[StooqDailyQuote]:
    """One bar per exact price, open = high = low = close."""
    return [
        StooqDailyQuote(date=d, open=p, high=p, low=p, close=p, volume=v)
        for d, p, v in zip(_weekdays(len(prices)), prices, volumes, strict=True)
    ]


def _frozen_bars(price: str, n: int, *, volume: int, lead: int = 0) -> list[StooqDailyQuote]:
    """``n`` sessions frozen at ``price`` — a suspended stock, say.

    With ``lead``, the frozen stretch comes after that many varied sessions: a
    slide from 5,000 to 20 with every session 1% off the line, so the sums the
    averages are taken from run to hundreds of thousands.
    """
    slide = [
        Decimal(str(round((5000.0 - 4980.0 * k / max(lead - 1, 1))
                          * (1.01 if k % 2 == 0 else 0.99), 4)))
        for k in range(lead)
    ]
    varied = [100_000 + 7_919 * (k % 13) for k in range(lead)]
    return _flat_bars(slide + [Decimal(price)] * n, varied + [volume] * n)


def _method() -> TradingMethod:
    m = get_method("pocket_pivot")
    assert m is not None
    return m


def _fires_last(bars: list[StooqDailyQuote]) -> bool:
    return P._pivot_line(P._Series(bars), len(bars) - 1) is not None


# ── Registration ──────────────────────────────────────────────────────────────


class TestPocketPivotRegistration:
    def test_registered_after_weinstein_and_long_only(self) -> None:
        m = _method()
        assert m is not None
        ids = method_ids()
        # order: ... weinstein (70) < pocket_pivot (80)
        assert ids.index("pocket_pivot") > ids.index("weinstein")
        assert m.direction == "Bullish"
        assert m.name == "Pocket Pivot"

    def test_source_names_the_authors(self) -> None:
        m = _method()
        assert "Morales" in m.source and "Kacher" in m.source
        assert m.source_url


# ── Firing: the complete setup, then each rule on its own ─────────────────────


class TestPocketPivotFiring:
    def test_complete_setup_fires(self) -> None:
        bars = _pp_bars()
        r = _method().evaluate(bars)
        assert r.available
        assert r.fired and r.days_since == 0
        assert r.score == 100  # every posture rule in place on the pivot day
        assert r.detail == "Pocket pivot x1.5 down-vol"  # 150k vs a 100k down day

    def test_comes_off_the_ten_day_line(self) -> None:
        bars = _pp_bars()
        assert P._pivot_line(P._Series(bars), len(bars) - 1) == 10

    def test_down_day_does_not_fire(self) -> None:
        assert not _fires_last(_pp_bars(pivot_up=False))

    def test_volume_under_the_largest_down_day_does_not_fire(self) -> None:
        # 90k against a 100k down day inside the ten-session window.
        assert not _fires_last(_pp_bars(pivot_volume=90_000))

    def test_equal_to_the_largest_down_day_fires(self) -> None:
        # The book: "equal to or greater than the largest down-volume day".
        assert _fires_last(_pp_bars(pivot_volume=100_000))

    def test_below_the_moving_averages_does_not_fire(self) -> None:
        assert not _fires_last(_pp_bars(downtrend=True))

    def test_extended_from_the_lines_does_not_fire(self) -> None:
        # A gap far above both averages: "otherwise it is extended".
        assert not _fires_last(_pp_bars(extended=True))

    def test_heavy_volume_going_in_does_not_fire(self) -> None:
        # A 120k-a-day pull-back is not the quiet one the book asks for — and
        # the pivot's 200k still clears the (now 120k) largest down day, so
        # only the quiet-volume rule rejects it.
        assert not _fires_last(_pp_bars(pullback_volume=120_000, pivot_volume=200_000))

    def test_after_a_wedge_does_not_fire(self) -> None:
        assert not _fires_last(_pp_bars(wedge=True))


class TestLargestDownVolume:
    def test_no_down_day_in_the_window_fails_closed(self) -> None:
        # Ten straight up days: nothing to beat, so the test must not pass
        # vacuously.
        rows = [(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 100_000) for i in range(12)]
        s = P._Series(_bars(rows))
        assert P._largest_down_volume(s, 11) == 0.0

    def test_zero_volume_down_days_fail_closed(self) -> None:
        # A ten-session pull-back on no trades, then a day of real demand: the
        # ten sessions before it hold down days, but none that traded, so rule
        # 2 has no supply to compare with. Every other rule holds — the fifty
        # sessions before the quiet window traded normally — so only the
        # fail-closed guard can refuse it, and a vacuous test must not pass.
        bars = _pp_bars(pullback_days=10, pullback_volume=0)
        s = P._Series(bars)
        i = len(bars) - 1
        assert P._largest_down_volume(s, i) == 0.0
        assert s.close[i] > s.close[i - 1] and s.volume[i] > 0  # 1: an up day, traded
        assert P._above_trend(s, i) == (True, True)  # 3
        assert P._line_touched(s, i) == P._SMA_FAST  # 4
        assert P._quiet_into(s, i)  # 5
        assert not P._wedging_into(s, i)  # 6
        assert not _fires_last(bars)
        assert _method().signals(bars) == []
        # The same pull-back with some selling to beat is a pocket pivot.
        assert _fires_last(_pp_bars(pullback_days=10, pullback_volume=50_000))

    def test_picks_the_heaviest_down_day(self) -> None:
        closes = [10, 9, 10, 8, 9, 7, 8, 9, 10, 11, 12]
        vols = [0, 500, 100, 900, 100, 300, 100, 100, 100, 100, 100]
        rows = [(c, c + 0.5, c - 0.5, c, v) for c, v in zip(closes, vols, strict=True)]
        s = P._Series(_bars(rows))
        assert P._largest_down_volume(s, 10) == 900


# ── Recency and the posture score ─────────────────────────────────────────────


class TestPocketPivotRecency:
    def test_recent_pivot_reports_its_age(self) -> None:
        bars = _pp_bars(trailing=3)
        r = _method().evaluate(bars)
        pivot_day = bars[-4].date
        assert not r.fired
        assert r.days_since == (bars[-1].date - pivot_day).days
        assert r.detail is not None and r.detail.startswith(f"Pocket pivot {r.days_since}d ago")

    def test_old_pivot_is_no_longer_fresh(self) -> None:
        fresh = _method().evaluate(_pp_bars(trailing=3))
        old = _method().evaluate(_pp_bars(trailing=20))
        assert old.days_since > P._RECENT_FIRED
        assert old.days_since != NEVER_FIRED
        assert old.score < fresh.score

    def test_no_pivot_reports_never(self) -> None:
        r = _method().evaluate(_pp_bars(pivot_volume=90_000))
        assert r.days_since == NEVER_FIRED
        assert not r.fired

    def test_downtrend_never_leans_bullish(self) -> None:
        # The analytics summary reads a score above 50 as a bullish lean.
        r = _method().evaluate(_pp_bars(downtrend=True))
        assert r.available
        assert r.score <= 50
        assert r.detail is not None and "below 200d MA" in r.detail

    def test_under_the_200_day_line_the_score_is_capped_at_neutral(self) -> None:
        # A recovery: a long fall, a climb back above the 50-day line that is
        # still under the 200-day one, then a quiet pull-back onto the 50-day
        # line. Most of the posture is in place, but the authors buy no pocket
        # pivot under the 200-day line, so the method must not lean bullish.
        rows: list[tuple[float, float, float, float, int]] = []
        prev = 140.0
        for i in range(180):
            c = 140.0 - 50.0 * i / 179 + (0.4 if i % 2 == 0 else -0.4)
            rows.append((prev, c + 0.5, c - 0.5, c, 100_000))
            prev = c
        for i in range(45):
            c = 90.0 + 10.0 * (i + 1) / 45 + (0.4 if i % 2 == 0 else -0.4)
            rows.append((prev, c + 0.5, c - 0.5, c, 100_000))
            prev = c
        for _ in range(5):
            c = prev - 0.4
            rows.append((prev, prev + 0.2, c - 0.5, c, 50_000))
            prev = c
        rows.append((prev, prev + 0.5, prev - 1.5, prev + 0.3, 40_000))
        bars = _bars(rows)

        s = P._Series(bars)
        i = len(bars) - 1
        assert P._above_trend(s, i) == (True, False)  # above the 50-day, under the 200-day
        uncapped = round(P._posture_rules(s, i, False) / P._TOTAL_RULES * 100)
        assert uncapped > 50
        r = _method().evaluate(bars)
        assert r.score == 50
        assert r.detail is not None and "below 200d MA" in r.detail

    def test_a_recent_pivot_under_the_200_day_line_says_why_it_is_capped(self) -> None:
        # A pivot, then a three-session slide of ~25% through both lines: the
        # pivot is still fresh, but under the 200-day line the method stays
        # neutral, and the note says why.
        rows = _pp_rows()
        prev = rows[-1][3]
        for _ in range(3):
            c = prev - 8.5
            rows.append((prev, prev + 0.2, c - 0.3, c, 120_000))
            prev = c
        bars = _bars(rows)
        assert P._above_trend(P._Series(bars), len(bars) - 1) == (False, False)
        r = _method().evaluate(bars)
        assert r.days_since == (bars[-1].date - bars[-4].date).days  # the pivot day
        assert 0 < r.days_since <= P._RECENT_FIRED
        assert r.score <= 50
        assert r.detail is not None
        assert r.detail.startswith("Pocket pivot ") and "below 200d MA" in r.detail


# ── The chart overlay ─────────────────────────────────────────────────────────


class TestPocketPivotSignals:
    def test_marks_the_pivot_day(self) -> None:
        bars = _pp_bars(trailing=5)
        sigs = _method().signals(bars)
        assert [s.date for s in sigs] == [bars[-6].date]
        assert sigs[0].type == "Bullish"
        assert sigs[0].label == "Pocket Pivot 10d"

    def test_no_markers_without_the_setup(self) -> None:
        assert _method().signals(_pp_bars(wedge=True, trailing=5)) == []

    def test_never_looks_ahead(self) -> None:
        # The markers up to any day are the same whether or not later bars
        # exist — a chart marker can never depend on the future.
        bars = _pp_bars(trailing=8)
        full = _method().signals(bars)
        for k in range(P._MIN_BARS, len(bars) + 1):
            cut = bars[k - 1].date
            part = _method().signals(bars[:k])
            assert part == [s for s in full if s.date <= cut]

    def test_evaluate_and_signals_agree(self) -> None:
        # "fired" means a chart marker on the latest bar, in both directions,
        # for every prefix. The real XTB bars hold a run of two pivot days
        # (2026-07-01 and 07-02) that carries one marker, so the second day
        # must not read as fired.
        for bars in (_pp_bars(trailing=8), xtb_daily_bars()):
            fired_on: list[date] = []
            for k in range(P._MIN_BARS, len(bars) + 1):
                prefix = bars[:k]
                last = prefix[-1].date
                marked = any(s.date == last for s in _method().signals(prefix))
                fired = _method().evaluate(prefix).fired
                assert fired == marked, last
                if fired:
                    fired_on.append(last)
            assert fired_on  # the loop really met a firing


# ── Guards ────────────────────────────────────────────────────────────────────


class TestPocketPivotGuards:
    def test_too_little_history_is_unavailable(self) -> None:
        bars = _pp_bars()[-(P._MIN_BARS - 1):]
        r = _method().evaluate(bars)
        assert not r.available
        assert _method().signals(bars) == []

    def test_empty_series_is_unavailable(self) -> None:
        assert not _method().evaluate([]).available
        assert _method().signals([]) == []

    def test_frozen_and_degenerate_series_do_not_raise(self) -> None:
        flat = _bars([(50.0, 50.0, 50.0, 50.0, 1_000)] * 260)
        zero = _bars([(50.0, 50.0, 50.0, 50.0, 0)] * 260)
        for bars in (flat, zero):
            r = _method().evaluate(bars)
            assert r.available and not r.fired
            assert _method().signals(bars) == []

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
    def test_a_non_finite_close_is_unavailable_not_an_error(self, bad: str) -> None:
        # Validation refuses such a price, but a bar built without it (as
        # model_copy does here) can still carry one, and the exact averages
        # have no integer ratio for it. The contract: never raise.
        for pos in (100, -1):
            bars = _pp_bars()
            bars[pos] = bars[pos].model_copy(update={"close": Decimal(bad)})
            r = _method().evaluate(bars)
            assert not r.available
            assert r.detail == "Invalid price data"
            assert _method().signals(bars) == []


# ── Exact averages: a frozen price is not above its averages ──────────────────


class TestPocketPivotExactAverages:
    """Whether a close is above its average is decided exactly (see ``_Series``).

    A float running sum drifts: 260 closes of 12.35 give a float 50-day average
    of 12.349999999999909, a hair under the price, so a float ``close > sma``
    read a suspended stock as trading above both of its averages.
    """

    def test_closes_above_is_false_when_the_close_equals_its_average(self) -> None:
        def last_above(*closes: str) -> bool:
            s = P._Series(_flat_bars([Decimal(c) for c in closes], [1] * len(closes)))
            return s.closes_above(len(closes), len(closes) - 1)

        # (12.3 + 12.40 + 12.35) / 3 is exactly 12.35 — mixed decimal places.
        assert not last_above("12.3", "12.40", "12.35")  # level with its average
        assert last_above("12.3", "12.40", "12.3501")  # one tick above it
        assert not last_above("12.3", "12.40", "12.3499")  # one tick below it
        s = P._Series(_frozen_bars("12.35", 260, volume=1_000))
        for length in (P._SMA_FAST, P._SMA_MID, P._SMA_SLOW):
            assert not any(s.closes_above(length, i) for i in range(length - 1, 260))
        assert not s.closes_above(P._SMA_SLOW, P._SMA_SLOW - 2)  # too few bars

    @pytest.mark.parametrize("price", ["12.35", "57.91"])
    @pytest.mark.parametrize("lead", [0, 200])
    def test_a_frozen_price_is_not_above_its_averages(self, price: str, lead: int) -> None:
        # ``lead`` > 0: a couple of hundred varied sessions first, so the sums
        # under the averages are large.
        bars = _frozen_bars(price, 260, volume=1_000, lead=lead)
        self._assert_level(bars)

    @pytest.mark.parametrize("price", ["12.35", "57.91"])
    def test_a_frozen_price_on_no_volume_is_not_above_its_averages(self, price: str) -> None:
        self._assert_level(_frozen_bars(price, 260, volume=0))

    @staticmethod
    def _assert_level(bars: list[StooqDailyQuote]) -> None:
        s = P._Series(bars)
        i = len(bars) - 1
        assert P._above_trend(s, i) == (False, False)
        assert P._line_touched(s, i) is None  # not "up off" a line it sits on
        r = _method().evaluate(bars)
        assert r.available and not r.fired
        assert r.score <= 50
        assert _method().signals(bars) == []


# ── A real pocket pivot: XTB, 2026-07-01 ──────────────────────────────────────


class TestPocketPivotXtb:
    """The real GPW example pinned in ``tests/data_xtb_2026.py``."""

    def _upto(self, day: date) -> list[StooqDailyQuote]:
        return [b for b in xtb_daily_bars() if b.date <= day]

    def test_fires_on_the_real_pivot_day(self) -> None:
        r = _method().evaluate(self._upto(PIVOT_DAY))
        assert r.fired and r.days_since == 0
        assert r.detail == "Pocket pivot x1.4 down-vol"

    def test_the_second_pivot_day_in_a_row_is_not_a_new_firing(self) -> None:
        # 2026-07-02 is a pivot too (3.1x the heaviest down day), but it is the
        # second day of the move that 07-01 started, which carries the marker:
        # not fired, one day old.
        bars = self._upto(date(2026, 7, 2))
        assert _fires_last(bars)  # the six rules hold on 07-02 as well
        r = _method().evaluate(bars)
        assert r.fired is False
        assert r.days_since == 1
        assert r.detail is not None and r.detail.startswith("Pocket pivot 1d ago")

    def test_marks_it_off_the_ten_day_line_once(self) -> None:
        # The next day is a pivot too (3.1x); one move gets one marker.
        sigs = _method().signals(xtb_daily_bars())
        assert [(s.date, s.label) for s in sigs] == [
            (date(2026, 2, 27), "Pocket Pivot 10d"),
            (date(2026, 3, 17), "Pocket Pivot 10d"),
            (date(2026, 6, 5), "Pocket Pivot 10d"),
            (PIVOT_DAY, "Pocket Pivot 10d"),
        ]

    def test_refuses_the_heavy_volume_day_after_a_wedge(self) -> None:
        bars = self._upto(WEDGE_DAY)
        s = P._Series(bars)
        i = len(bars) - 1
        assert s.volume[i] >= 2 * P._largest_down_volume(s, i)  # the volume is there
        assert P._wedging_into(s, i)
        assert not _method().evaluate(bars).fired

    def test_refuses_the_extended_day(self) -> None:
        bars = self._upto(EXTENDED_DAY)
        s = P._Series(bars)
        i = len(bars) - 1
        assert s.volume[i] >= 2 * P._largest_down_volume(s, i)
        assert P._line_touched(s, i) is None  # far above both lines
        assert not _method().evaluate(bars).fired
