"""Tests for the Weinstein Stage 1->2 breakout method (app/analysis/methods/weinstein.py).

Covers the complete setup, one fixture per rule it can fail on (including the
rise cap that separates it from a late-Stage-2 continuation buy), the weekly
mechanics (a forming week is never read as a breakout), the ``signals``
overlay, the guards, and the real Dom Development breakout of 2022-12-19 that
``agent/ROADMAP.md`` #28 records as verified.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.analysis.methods import get_method, method_ids
from app.analysis.methods import weinstein as W
from app.analysis.methods.base import NEVER_FIRED
from app.models import StooqDailyQuote
from tests.data_dom_2022 import BREAKOUT_WEEK, CONTINUATION_WEEK, dom_weekly_bars

# ── Fixtures ──────────────────────────────────────────────────────────────────

# A Friday, so every generated bar ends its own ISO week and one daily bar
# becomes exactly one weekly candle — the method then reads precisely the
# series a test writes, with no aggregation in between.
_LAST_FRIDAY = date(2026, 1, 2)


def _bar(d: date, o: float, h: float, low: float, c: float, v: int) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(round(o, 4))),
        high=Decimal(str(round(h, 4))),
        low=Decimal(str(round(low, 4))),
        close=Decimal(str(round(c, 4))),
        volume=v,
    )


def _weekly(rows: list[tuple[float, float, float, float, int]]) -> list[StooqDailyQuote]:
    """One Friday bar per week from (open, high, low, close, volume) rows."""
    n = len(rows)
    out = []
    for i, (o, h, low, c, v) in enumerate(rows):
        out.append(_bar(_LAST_FRIDAY - timedelta(weeks=n - 1 - i), o, h, low, c, v))
    return out


def _daily(rows: list[tuple[float, float, float, float, int]]) -> list[StooqDailyQuote]:
    """The same weeks as five Monday-to-Friday sessions each.

    An ordinary daily series, which ``_weekly`` deliberately is not: with one
    bar per week a stock's "typical week" is a single session, so a one-day
    stub of the next week looks like a complete week to
    ``trailing_week_is_complete``. Anything that tests the forming-week
    behaviour has to be built from this.
    """
    out: list[StooqDailyQuote] = []
    for wk in _weekly(rows):
        monday = wk.date - timedelta(days=4)
        o, h, low, c = (float(wk.open), float(wk.high), float(wk.low), float(wk.close))
        v = wk.volume
        fifth, rest = v // 5, v - 4 * (v // 5)
        # Mon..Fri: the week's open on Monday, its high and low mid-week, its
        # close on Friday — so re-aggregating gives back exactly ``wk``.
        out.append(_bar(monday, o, o, o, o, fifth))
        out.append(_bar(monday + timedelta(days=1), o, h, o, h, fifth))
        out.append(_bar(monday + timedelta(days=2), h, h, low, low, fifth))
        out.append(_bar(monday + timedelta(days=3), low, c, low, c, fifth))
        out.append(_bar(monday + timedelta(days=4), c, c, c, c, rest))
    return out


def _weinstein_rows(
    *,
    decline_weeks: int = 15,
    pre_top: float = 130.0,
    level: float = 100.0,
    base_weeks: int = 45,
    base_swing: float = 4.0,
    base_volume: int = 100_000,
    breakout_close: float = 107.0,
    breakout_volume: int = 320_000,
    rising_run: bool = False,
    still_falling: bool = False,
    trailing_weeks: int = 0,
) -> list[tuple[float, float, float, float, int]]:
    """A Stage 4 decline, a long flat Stage 1 base, then the breakout week.

    Every keyword breaks exactly one of the six firing conditions, so a test
    can show which gate did the rejecting:

    * ``breakout_close``  — rule 2 (a close above the top of the base)
    * ``breakout_volume`` — rule 6 (at least 2x the prior ten weeks)
    * ``base_swing``      — rule 1 (a tight sideways range)
    * ``still_falling``   — rule 4 (the 30-week MA has stopped falling)
    * ``rising_run``      — rule 5 (the MA is not already advancing), i.e. the
      same breakout out of a base that sits on top of a run, which is
      Bulkowski's late-Stage-2 buy rather than Weinstein's transition
    * ``trailing_weeks``  — quiet weeks after the breakout, for recency
    """
    rows: list[tuple[float, float, float, float, int]] = []

    if rising_run:
        # A steady advance into the base, so the 30-week MA is still climbing
        # hard when the breakout comes.
        for i in range(decline_weeks):
            c = level - 45.0 + 45.0 * (i + 1) / decline_weeks
            rows.append((c - 1.0, c + 1.5, c - 2.0, c, base_volume))
    else:
        # The Stage 4 decline the base forms after.
        for i in range(decline_weeks):
            c = pre_top - (pre_top - level) * (i + 1) / decline_weeks
            rows.append((c + 1.0, c + 1.5, c - 1.5, c, base_volume))

    # The Stage 1 base: a flat range oscillating around ``level``.
    for i in range(base_weeks):
        c = level + (base_swing if i % 2 else -base_swing)
        drift = -0.8 * (i + 1) if still_falling else 0.0
        c += drift
        rows.append((c, c + 1.0, c - 1.0, c, base_volume))

    # The breakout week.
    bc = breakout_close + (-0.8 * base_weeks if still_falling else 0.0)
    rows.append((bc - 4.0, bc + 0.5, bc - 4.5, bc, breakout_volume))

    # Quiet weeks after it.
    for _ in range(trailing_weeks):
        rows.append((bc - 0.5, bc + 0.5, bc - 1.5, bc - 0.5, base_volume))
    return rows


def _weinstein_bars(**kwargs) -> list[StooqDailyQuote]:
    return _weekly(_weinstein_rows(**kwargs))


def _method():
    return get_method("weinstein")


# ── Registration ──────────────────────────────────────────────────────────────


class TestWeinsteinRegistration:
    def test_registered_last_and_long_only(self) -> None:
        ids = method_ids()
        assert "weinstein" in ids
        # Display order: after the VSA methods (vsa3 is 60, weinstein 70).
        assert ids.index("weinstein") > ids.index("vsa3")
        m = _method()
        assert m.direction == "Bullish"
        assert m.name and m.description and m.source and m.source_url

    def test_source_names_weinstein(self) -> None:
        assert "Weinstein" in _method().source


# ── The setup ─────────────────────────────────────────────────────────────────


class TestWeinsteinFiring:
    def test_complete_setup_fires(self) -> None:
        r = _method().evaluate(_weinstein_bars())
        assert r.available is True
        assert r.fired is True
        assert r.days_since == 0
        assert r.score == 100  # all six posture rules stand
        assert r.detail is not None
        assert r.detail.startswith("Stage 2 breakout")
        assert "vol" in r.detail

    def test_no_close_above_the_base_top_does_not_fire(self) -> None:
        # Rule 2: a rally inside the base, however heavy, is not a breakout.
        r = _method().evaluate(_weinstein_bars(breakout_close=103.0))
        assert r.available is True
        assert r.fired is False
        assert r.days_since == NEVER_FIRED

    def test_volume_under_two_times_does_not_fire(self) -> None:
        # Rule 6: the same breakout without the demand behind it.
        r = _method().evaluate(_weinstein_bars(breakout_volume=150_000))
        assert r.fired is False
        assert r.days_since == NEVER_FIRED

    def test_falling_30_week_ma_does_not_fire(self) -> None:
        # Rule 4: still Stage 4 — the decline has not finished.
        bars = _weinstein_bars(still_falling=True, breakout_close=107.0)
        r = _method().evaluate(bars)
        assert r.fired is False

    def test_mature_stage2_advance_does_not_fire(self) -> None:
        """Rule 5 — the whole point of the method.

        The same breakout bar out of the same tight range fires when the
        30-week MA has flattened and is REFUSED when the range is a pause on
        top of a run still in progress: that is Bulkowski's late-Stage-2 buy
        (+4.1% and 57% winners) rather than Weinstein's transition (+13.2% and
        69%). The two are structurally different by necessity — an MA only goes
        flat once the prior move has rolled out of its window — so what the
        fixtures hold constant is the breakout, not the length of the base.
        """
        flat = _method().evaluate(_weinstein_bars())
        assert flat.fired is True

        bars = _weinstein_bars(rising_run=True, decline_weeks=35, base_weeks=12)
        run = _method().evaluate(bars)
        assert run.available is True
        assert run.fired is False

        # Pin WHY it was refused, so this cannot start passing for some other
        # reason: everything else about the breakout is in order, and only the
        # MA's slope disqualifies it.
        weekly = W._completed_weeks(bars)
        c = [float(q.close) for q in weekly]
        h = [float(q.high) for q in weekly]
        low = [float(q.low) for q in weekly]
        v = [float(q.volume) for q in weekly]
        i = len(weekly) - 1
        ma, ma_prev = W._ma_pair(c, i)
        assert ma > ma_prev * (1.0 + W._MA_MAX_RISE)  # the rise cap bites
        assert c[i] > max(h[i - W._BASE_WEEKS : i])  # it did clear the range
        assert W._base_is_tight(h, low, i)  # the range was tight
        assert v[i] >= W._mean(v, i - W._VOL_WEEKS, i) * W._VOL_MULT  # on volume

    def test_untight_base_does_not_fire(self) -> None:
        # Rule 1: a 40%-wide swinging range is not a base.
        r = _method().evaluate(_weinstein_bars(base_swing=22.0, breakout_close=126.0))
        assert r.fired is False

    def test_zero_volume_baseline_fails_closed(self) -> None:
        # A suspended stock has no demand to measure against; the volume test
        # must fail rather than pass vacuously.
        rows = _weinstein_rows(base_volume=0, breakout_volume=1)
        r = _method().evaluate(_weekly(rows))
        assert r.fired is False


# ── Recency and the score ─────────────────────────────────────────────────────


class TestWeinsteinRecency:
    def test_recent_breakout_keeps_its_score_and_reports_its_age(self) -> None:
        r = _method().evaluate(_weinstein_bars(trailing_weeks=2))
        assert r.fired is False  # it fired two weeks ago, not this week
        assert r.days_since == 14
        # The base is measured at the breakout week, not at today — otherwise
        # the run-up would read as "no base" exactly when the setup triggered.
        assert r.score == 100
        assert r.detail is not None
        assert "Broke out 14d ago" in r.detail

    def test_old_breakout_is_no_longer_fresh(self) -> None:
        r = _method().evaluate(_weinstein_bars(trailing_weeks=8))
        assert r.days_since == 56
        assert r.score < 100  # the "fresh breakout" rule has lapsed

    def test_no_breakout_in_range_reports_never(self) -> None:
        r = _method().evaluate(_weinstein_bars(trailing_weeks=30))
        assert r.days_since == NEVER_FIRED
        assert r.fired is False

    def test_stock_below_its_30_week_average_says_so(self) -> None:
        rows = _weinstein_rows(decline_weeks=40, base_weeks=20, still_falling=True)
        r = _method().evaluate(_weekly(rows))
        assert r.available is True
        assert r.fired is False
        assert r.detail is not None
        assert "below 30w MA" in r.detail
        assert r.score <= 50


# ── Weekly mechanics ──────────────────────────────────────────────────────────


class TestWeinsteinWeeklyMechanics:
    def test_forming_week_is_ignored(self) -> None:
        """A part-built week must not change the read or add a firing.

        Weinstein buys a weekly *close*, and a Monday-to-Wednesday stub carries
        a fraction of a week's volume — exactly the input the 2x volume test
        cannot answer.
        """
        bars = _daily(_weinstein_rows())
        full = _method().evaluate(bars)
        assert full.fired is True
        # Three sessions of the following week, ending on a Wednesday.
        friday = bars[-1].date
        partial = [
            _bar(friday + timedelta(days=n), 107.0, 108.0, 106.0, 107.5, 40_000)
            for n in (3, 4, 5)
        ]
        with_stub = _method().evaluate([*bars, *partial])
        assert with_stub.score == full.score
        assert with_stub.days_since == 5  # measured from the newest daily bar
        assert with_stub.fired is False  # last week's close, not this week's
        assert _method().signals([*bars, *partial]) == _method().signals(bars)

    def test_a_partial_week_cannot_itself_fire(self) -> None:
        """A huge two-day surge above the base top is not yet a breakout week."""
        bars = _daily(_weinstein_rows(breakout_close=103.0))  # no breakout yet
        assert _method().evaluate(bars).days_since == NEVER_FIRED
        friday = bars[-1].date
        surge = [
            _bar(friday + timedelta(days=3), 103.0, 109.0, 103.0, 108.5, 700_000),
            _bar(friday + timedelta(days=4), 108.5, 112.0, 108.0, 111.0, 800_000),
        ]
        r = _method().evaluate([*bars, *surge])
        assert r.fired is False
        assert r.days_since == NEVER_FIRED
        assert _method().signals([*bars, *surge]) == []

    def test_daily_bars_are_aggregated_into_the_same_weekly_candle(self) -> None:
        """Five real sessions a week give the same answer as one weekly bar.

        Most fixtures write one Friday bar per week for control; this pins that
        the method reads an ordinary daily series the same way.
        """
        rows = _weinstein_rows()
        weekly_only = _weekly(rows)
        spread = _daily(rows)
        assert _method().evaluate(spread).fired is True
        assert [s.date for s in _method().signals(spread)] == [
            s.date for s in _method().signals(weekly_only)
        ]


# ── The chart overlay ─────────────────────────────────────────────────────────


class TestWeinsteinSignals:
    def test_marks_the_breakout_week_on_a_real_session(self) -> None:
        bars = _weinstein_bars(trailing_weeks=3)
        sigs = _method().signals(bars)
        assert len(sigs) == 1
        s = sigs[0]
        assert s.type == "Bullish"
        assert s.label == "Stage 2 breakout"
        # Dated to a session that exists in the daily series, so the marker
        # lands on the chart and the back-test can index it.
        assert s.date in {b.date for b in bars}
        assert s.date == bars[-4].date

    def test_one_marker_per_move(self) -> None:
        """Two breakout weeks back to back are one entry, not two."""
        rows = _weinstein_rows()
        rows.append((107.0, 113.0, 106.5, 112.0, 400_000))  # a second new high
        sigs = _method().signals(_weekly(rows))
        assert len(sigs) == 1

    def test_a_second_breakout_week_is_not_fired_again(self) -> None:
        """The Dashboard's "fired" and the chart's marker name the same week.

        The second of two breakout weeks in a row is the same move: the chart
        leaves it unmarked, so ``evaluate`` must not call it "fired" either —
        it reports the first week's age instead.
        """
        rows = _weinstein_rows()
        rows.append((107.0, 113.0, 106.5, 112.0, 400_000))  # a second new high
        bars = _weekly(rows)
        weekly = W._completed_weeks(bars)
        cols = (
            [float(q.close) for q in weekly],
            [float(q.high) for q in weekly],
            [float(q.low) for q in weekly],
            [float(q.volume) for q in weekly],
        )
        last = len(weekly) - 1
        assert W._breakout_fired(*cols, last - 1) and W._breakout_fired(*cols, last)

        r = _method().evaluate(bars)
        assert r.fired is False
        assert r.days_since == 7
        assert _method().evaluate(bars[:-1]).fired is True
        assert [s.date for s in _method().signals(bars)] == [bars[-2].date]

    def test_no_markers_without_the_setup(self) -> None:
        assert _method().signals(_weinstein_bars(breakout_volume=120_000)) == []

    def test_evaluate_and_signals_agree(self) -> None:
        """No look-ahead: what ``signals`` marks is what ``evaluate`` saw then.

        Truncating the series at each week and asking ``evaluate`` must fire on
        exactly the weeks ``signals`` marks over the whole series.
        """
        bars = _weinstein_bars(trailing_weeks=6)
        marked = {s.date for s in _method().signals(bars)}
        fired_live = set()
        for i in range(len(bars)):
            r = _method().evaluate(bars[: i + 1])
            if r.available and r.fired:
                fired_live.add(bars[i].date)
        assert fired_live == marked


# ── Guards ────────────────────────────────────────────────────────────────────


class TestWeinsteinGuards:
    def test_too_little_history_is_unavailable(self) -> None:
        r = _method().evaluate(_weekly([(100, 101, 99, 100, 1000)] * 30))
        assert r.available is False
        assert r.score == 0
        assert r.fired is False

    def test_empty_series_is_unavailable(self) -> None:
        assert _method().evaluate([]).available is False
        assert _method().signals([]) == []

    def test_frozen_and_degenerate_series_do_not_raise(self) -> None:
        flat = _weekly([(100, 100, 100, 100, 0)] * 60)
        r = _method().evaluate(flat)
        assert r.available is True
        assert r.fired is False
        assert _method().signals(flat) == []

    def test_unsorted_input_is_handled(self) -> None:
        bars = _weinstein_bars()
        shuffled = [*bars[40:], *bars[:40]]
        assert _method().evaluate(shuffled).fired is True


# ── The verified real example ─────────────────────────────────────────────────


class TestWeinsteinDomDevelopment:
    """Dom Development (DOM), the breakout of the week of 2022-12-19.

    ``agent/ROADMAP.md`` #28 records this one against raw weekly Yahoo data:
    the week closed above a five-month base on 122,201 shares, 6.9x the prior
    ten-week average, with the 30-week average flat — and the stock rose ~44%
    over the next four months. The same roadmap entry records that the stock's
    *continuation* breakout in July 2023 did far worse, which is what rule 5 is
    there to refuse.
    """

    def test_fires_on_the_verified_breakout_week(self) -> None:
        sigs = _method().signals(dom_weekly_bars())
        assert [s.date for s in sigs] == [BREAKOUT_WEEK]

    def test_the_reading_at_the_time(self) -> None:
        upto = [b for b in dom_weekly_bars() if b.date <= BREAKOUT_WEEK]
        r = _method().evaluate(upto)
        assert r.fired is True
        assert r.score == 100
        # The roadmap's measured figure: 6.9x the prior ten-week average.
        assert r.detail == "Stage 2 breakout x6.9 vol"

    def test_refuses_the_later_continuation_breakout(self) -> None:
        upto = [b for b in dom_weekly_bars() if b.date <= CONTINUATION_WEEK]
        r = _method().evaluate(upto)
        assert r.fired is False
        # It cleared the prior high on 3.8x volume, so only the stage rules can
        # have refused it: by then the 30-week average was climbing ~18% per
        # ten weeks and the range behind it was no longer a base.
        weekly = [float(b.close) for b in upto]
        ma, ma_prev = W._ma_pair(weekly, len(weekly) - 1)
        assert ma > ma_prev * (1.0 + W._MA_MAX_RISE)
