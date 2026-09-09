"""Tests for the multi-timeframe (weekly) VSA analysis."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analysis.vsa import (
    SignalName,
    SignalType,
    VsaSignal,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.analysis.weekly import (
    _MAX_WEEKLY_BARS,
    _MIN_WEEKLY_BARS,
    _WEEKLY_HALF_LIFE_DAYS,
    WeeklyView,
    compute_weekly_view,
    resample_weekly,
    trailing_week_is_complete,
    weekly_agreement,
)
from app.models import StooqDailyQuote

# The VSA engine's own default half-life, in calendar days. It was chosen for
# DAILY bars (~21 sessions of memory) and is what the weekly read used to
# inherit — the comparison the tests below turn on.
_DAILY_HALF_LIFE_DAYS = 30


def _bar(
    d: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=date.fromisoformat(d),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _daily_series(n_days: int, base_price: float = 100.0) -> list[StooqDailyQuote]:
    """Bland daily bars over ``n_days`` consecutive calendar days (no signals)."""
    start = date(2025, 1, 6)  # a Monday
    return [
        _bar(
            (start + timedelta(days=i)).isoformat(),
            base_price,
            base_price + 1,
            base_price - 1,
            base_price,
            50_000,
        )
        for i in range(n_days)
    ]


# ── resample_weekly ───────────────────────────────────────────────────────────


def test_resample_weekly_empty() -> None:
    assert resample_weekly([]) == []


def test_resample_weekly_aggregates_ohlcv_and_groups_across_year_boundary() -> None:
    # Mon 2025-12-29 → Sun 2026-01-04 is ISO week 2026-W01, so these three bars
    # (which straddle the calendar-year boundary) must collapse into ONE weekly
    # candle — a common off-by-one bug if you group by (calendar year, week).
    bars = [
        _bar("2025-12-29", 10, 12, 9, 11, 100),  # Mon
        _bar("2025-12-31", 11, 15, 10, 13, 200),  # Wed
        _bar("2026-01-02", 13, 14, 8, 9, 150),  # Fri
        _bar("2026-01-05", 9, 11, 8, 10, 50),  # next Mon (ISO 2026-W02)
    ]
    weekly = resample_weekly(bars)
    assert len(weekly) == 2

    w1 = weekly[0]
    assert w1.date == date(2026, 1, 2)  # last session of the week
    assert w1.open == Decimal("10")  # first open
    assert w1.high == Decimal("15")  # max high
    assert w1.low == Decimal("8")  # min low
    assert w1.close == Decimal("9")  # last close
    assert w1.volume == 450  # summed

    w2 = weekly[1]
    assert w2.date == date(2026, 1, 5)
    assert w2.volume == 50


def test_resample_weekly_sorts_unordered_input() -> None:
    bars = [
        _bar("2025-01-08", 11, 15, 10, 13, 200),  # Wed
        _bar("2025-01-06", 10, 12, 9, 11, 100),  # Mon (earlier)
    ]
    weekly = resample_weekly(bars)
    assert len(weekly) == 1
    # open comes from the chronologically first bar even though it was passed last
    assert weekly[0].open == Decimal("10")
    assert weekly[0].close == Decimal("13")


# ── weekly_agreement ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("daily", "weekly", "expected"),
    [
        ("Strong Buy", "Buy", "confirms"),
        ("Buy", "Strong Buy", "confirms"),
        ("Strong Sell", "Sell", "confirms"),
        ("Sell", "Strong Sell", "confirms"),
        ("Strong Buy", "Sell", "conflicts"),
        ("Buy", "Strong Sell", "conflicts"),
        ("Strong Sell", "Buy", "conflicts"),
        ("Buy", "Hold", "neutral"),
        ("Hold", "Strong Buy", "neutral"),
        ("Hold", "Hold", "neutral"),
    ],
)
def test_weekly_agreement(daily: str, weekly: str, expected: str) -> None:
    assert weekly_agreement(daily, weekly) == expected


# ── compute_weekly_view ───────────────────────────────────────────────────────


def test_weekly_view_unavailable_when_history_too_short() -> None:
    # A couple of weeks of daily bars is nowhere near _MIN_WEEKLY_BARS.
    view = compute_weekly_view(_daily_series(10))
    assert view == WeeklyView(available=False, weekly_bars=view.weekly_bars)
    assert view.available is False
    assert view.rating is None
    assert view.verdict is None
    assert view.weekly_bars < _MIN_WEEKLY_BARS


def test_weekly_view_available_on_long_bland_history() -> None:
    # ~37 ISO weeks of bland bars: enough weekly context to run the engine, but
    # no VSA structure — so a neutral (Hold / rating 50) reading.
    view = compute_weekly_view(_daily_series(260))
    assert view.available is True
    assert view.weekly_bars >= _MIN_WEEKLY_BARS
    assert view.rating == 50
    assert view.verdict == "Hold"


def test_weekly_view_empty_history() -> None:
    view = compute_weekly_view([])
    assert view.available is False
    assert view.weekly_bars == 0


# ── Weekly-scale fixtures ─────────────────────────────────────────────────────
#
# Two shapes are used below.
#
# ``_one_bar_per_week`` puts a single bar in each ISO week, so a weekly candle
# is byte-for-byte the daily bar that made it — the clearest way to say "this
# WEEK looked like this" in a test.
#
# ``_weekday_series`` is the realistic shape (Mon–Fri), used where the point is
# how weeks are assembled rather than what they contain.

_FIRST_MONDAY = date(2025, 1, 6)
_FIRST_WEDNESDAY = date(2025, 1, 8)

# A wide up-bar closing near its high on 2.4x normal volume: the Sign of
# Strength shape from ``test_vsa.py``, here occupying a whole week.
_STRENGTH_WEEK = (99.5, 108.0, 99.2, 107.5, 120_000)
_BLAND_WEEK = (100.0, 101.0, 99.0, 100.0, 50_000)

# The same Sign-of-Strength week split across five daily bars: opens at 99.5 on
# Monday, closes at 107.5 on Friday, spans 99.2–108.0, and the five volumes sum
# to the weekly 120,000. Aggregated by ``resample_weekly`` it reproduces
# ``_STRENGTH_WEEK`` exactly.
_STRENGTH_DAYS = [
    (99.5, 100.0, 99.2, 99.8),
    (99.8, 102.0, 99.5, 101.5),
    (101.5, 104.0, 101.0, 103.5),
    (103.5, 106.0, 103.0, 105.5),
    (105.5, 108.0, 105.0, 107.5),
]


def _one_bar_per_week(
    weeks: int, strength_at: int | None = None
) -> list[StooqDailyQuote]:
    """One Wednesday bar per ISO week; ``strength_at`` is a bullish week's index."""
    out: list[StooqDailyQuote] = []
    for w in range(weeks):
        d = _FIRST_WEDNESDAY + timedelta(weeks=w)
        o, h, low, c, v = _STRENGTH_WEEK if w == strength_at else _BLAND_WEEK
        out.append(_bar(d.isoformat(), o, h, low, c, v))
    return out


def _weekday_series(
    weeks: int,
    strength_at: int | None = None,
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4),
) -> list[StooqDailyQuote]:
    """Daily bars on the given weekdays of each week (0 = Monday)."""
    out: list[StooqDailyQuote] = []
    for w in range(weeks):
        for j, weekday in enumerate(weekdays):
            d = _FIRST_MONDAY + timedelta(weeks=w, days=weekday)
            if strength_at == w:
                o, h, low, c = _STRENGTH_DAYS[j]
                out.append(_bar(d.isoformat(), o, h, low, c, 24_000))
            else:
                out.append(_bar(d.isoformat(), 100.0, 101.0, 99.0, 100.0, 10_000))
    return out


# ── The weekly-scaled half-life ───────────────────────────────────────────────


class TestWeeklyHalfLife:
    """A weekly signal must be remembered for weeks, not for a month of days.

    The VSA engine's default half-life is 30 CALENDAR DAYS, chosen for daily
    bars (~21 sessions of memory). Applied unchanged to weekly candles it is
    4.3 *bars* — so the weekly view looked back no further than the daily one
    and answered "neutral" almost always, which is the opposite of what a
    higher-timeframe confirmation is for.

    Every assertion below is on a verdict or a rating, never on a decayed
    float, so the thresholds can be tuned without rewriting the tests.
    """

    # Eight weeks: far enough back that the daily half-life has all but
    # forgotten the signal, recent enough that a weekly reader has not.
    _WEEKS_BACK = 8
    _AS_OF = date(2026, 1, 7)

    @classmethod
    def _one_bullish_week_ago(cls, weeks_back: int) -> list[VsaSignal]:
        return [
            VsaSignal(
                date=cls._AS_OF - timedelta(weeks=weeks_back),
                signal_name=SignalName.SOS,
                type=SignalType.BULLISH,
                strength=1.0,
            )
        ]

    def test_scaling_is_stated_as_one_week_per_daily_day(self) -> None:
        # The intent, in one line: a WEEK of weekly bars should decay like a
        # DAY of daily bars.
        assert _WEEKLY_HALF_LIFE_DAYS == _DAILY_HALF_LIFE_DAYS * 7

    def test_eight_week_old_signal_still_leans_buy(self) -> None:
        signals = self._one_bullish_week_ago(self._WEEKS_BACK)
        verdict, _ = verdict_from_signals(
            signals, self._AS_OF, _WEEKLY_HALF_LIFE_DAYS
        )
        assert verdict in {"Buy", "Strong Buy"}
        assert compute_rating(signals, self._AS_OF, _WEEKLY_HALF_LIFE_DAYS) > 60

    def test_the_daily_half_life_would_have_faded_it_to_hold(self) -> None:
        """The regression this guards against, stated explicitly."""
        signals = self._one_bullish_week_ago(self._WEEKS_BACK)
        verdict, _ = verdict_from_signals(signals, self._AS_OF, _DAILY_HALF_LIFE_DAYS)
        assert verdict == "Hold"

    def test_weekly_view_reports_the_lean_end_to_end(self) -> None:
        # 45 weekly candles, one of strength eight weeks before the last.
        view = compute_weekly_view(_one_bar_per_week(45, strength_at=36))
        assert view.available is True
        assert view.verdict in {"Buy", "Strong Buy"}
        assert view.rating is not None and view.rating > 60

    def test_the_same_series_reads_hold_under_the_daily_half_life(self) -> None:
        # Same bars, same engine, only the half-life differs — so this pins the
        # half-life as the cause, not the fixture.
        weekly = resample_weekly(_one_bar_per_week(45, strength_at=36))
        signals = detect_signals(weekly)
        assert signals, "fixture no longer produces a weekly signal"

        verdict, _ = verdict_from_signals(
            signals, weekly[-1].date, _DAILY_HALF_LIFE_DAYS
        )
        assert verdict == "Hold"

    def test_rating_and_verdict_agree_on_direction(self) -> None:
        # ``verdict_from_signals``'s docstring requires the same half-life in
        # both: they read one decayed net score, and a mismatch is how a
        # "rating 90 with a Sell badge" contradiction is born.
        view = compute_weekly_view(_one_bar_per_week(45, strength_at=44))
        assert view.rating is not None
        assert (view.rating > 50) is (view.verdict in {"Buy", "Strong Buy"})

    def test_a_very_old_signal_still_decays_away(self) -> None:
        # The longer memory must not become no memory at all.
        stale = self._one_bullish_week_ago(weeks_back=200)
        verdict, _ = verdict_from_signals(stale, self._AS_OF, _WEEKLY_HALF_LIFE_DAYS)
        assert verdict == "Hold"


# ── The still-forming week is excluded from the read ──────────────────────────


class TestTrailingWeekIsComplete:
    def test_a_week_ending_on_friday_is_finished(self) -> None:
        quotes = _weekday_series(4)
        assert quotes[-1].date.weekday() == 4
        assert trailing_week_is_complete(quotes) is True

    def test_a_week_that_has_only_reached_monday_is_still_forming(self) -> None:
        quotes = _weekday_series(4)[:-4]  # drop Tue–Fri of the last week
        assert quotes[-1].date.weekday() == 0
        assert trailing_week_is_complete(quotes) is False

    def test_a_thin_stock_whose_normal_week_is_three_sessions(self) -> None:
        # Mon/Tue/Wed only — it never prints a Friday, so the Friday cue can
        # never fire and the session-count cue has to carry the decision.
        quotes = _weekday_series(6, weekdays=(0, 1, 2))
        assert quotes[-1].date.weekday() == 2
        assert trailing_week_is_complete(quotes) is True

        # …and the same stock one session into a new week is not finished.
        partial = quotes[:-2]
        assert partial[-1].date.weekday() == 0
        assert trailing_week_is_complete(partial) is False

    def test_a_week_short_of_this_stocks_norm_is_treated_as_forming(self) -> None:
        # A five-session stock that has only printed Mon–Thu. On an ordinary
        # Thursday evening that is exactly right (the week is not over). On the
        # rarer Friday-holiday week it is conservative — one genuinely finished
        # week is skipped rather than risk analysing a part-built bar — so the
        # weekly read simply stays a week behind until the next full Friday.
        quotes = _weekday_series(6)[:-1]
        assert quotes[-1].date.weekday() == 3
        assert trailing_week_is_complete(quotes) is False

    def test_a_single_week_has_nothing_to_compare_against(self) -> None:
        # One Monday-to-Thursday week and no history: treated as forming,
        # because there is no "typical week" for this stock yet.
        quotes = _weekday_series(1)[:-1]
        assert trailing_week_is_complete(quotes) is False

    def test_empty_history_is_not_a_complete_week(self) -> None:
        assert trailing_week_is_complete([]) is False


class TestFormingWeekExcluded:
    """``resample_weekly`` keeps the forming week; ``compute_weekly_view`` drops it.

    That split is deliberate and both halves are pinned here, because the chart
    depends on one and the verdict on the other. A chart's ``1w`` timeframe must
    show the week in progress — the user wants to see today. A *detector* must
    not: a part-built weekly bar carries a fraction of a real week's volume and
    range, and "volume below average" plus "spread below average" are the hard
    gates on No Demand and the Successful Test.
    """

    def test_resample_weekly_still_keeps_the_week_in_progress(self) -> None:
        base = _weekday_series(6)
        monday = _bar(
            (_FIRST_MONDAY + timedelta(weeks=6)).isoformat(),
            100.0, 101.0, 99.0, 100.0, 10_000,
        )

        with_forming = resample_weekly(base + [monday])
        assert len(with_forming) == len(resample_weekly(base)) + 1
        assert with_forming[-1].date == monday.date

    def test_a_complete_week_is_analysed_unchanged(self) -> None:
        quotes = _weekday_series(45, strength_at=36)
        assert trailing_week_is_complete(quotes) is True

        view = compute_weekly_view(quotes)
        assert view.available is True
        assert view.weekly_bars == 45  # every week counted, none dropped
        assert view.verdict in {"Buy", "Strong Buy"}

    def test_one_extra_monday_does_not_shift_the_read(self) -> None:
        base = _weekday_series(45, strength_at=36)
        before = compute_weekly_view(base)

        monday = _bar(
            (_FIRST_MONDAY + timedelta(weeks=45)).isoformat(),
            100.0, 101.0, 99.0, 100.0, 10_000,
        )
        after = compute_weekly_view(base + [monday])

        assert after == before  # verdict, rating AND the analysed bar count

    def test_a_dramatic_monday_cannot_flip_the_weekly_badge(self) -> None:
        """The case that makes this worth guarding.

        One Monday of selling, read as if it were a whole week, is a wide
        down-bar on twenty times the usual volume — a textbook Sign of Weakness.
        Analysing it would turn a neutral weekly badge into "Sell" on a Monday
        evening and back again by Friday.
        """
        base = _weekday_series(40)
        monday = _bar(
            (_FIRST_MONDAY + timedelta(weeks=40)).isoformat(),
            100.0, 100.5, 88.0, 89.0, 200_000,
        )

        # What the engine would say if the forming bar were analysed…
        forming_weekly = resample_weekly(base + [monday])[-_MAX_WEEKLY_BARS:]
        would_be, _ = verdict_from_signals(
            detect_signals(forming_weekly),
            forming_weekly[-1].date,
            _WEEKLY_HALF_LIFE_DAYS,
        )
        assert would_be == "Sell", "fixture no longer produces a phantom signal"

        # …and what it actually says.
        assert compute_weekly_view(base + [monday]) == compute_weekly_view(base)

    def test_the_forming_week_is_not_counted_in_weekly_bars(self) -> None:
        # ``weekly_bars`` reports what was ANALYSED, so a caller reading it is
        # never told about a bar the verdict did not see.
        base = _weekday_series(40)
        monday = _bar(
            (_FIRST_MONDAY + timedelta(weeks=40)).isoformat(),
            100.0, 101.0, 99.0, 100.0, 10_000,
        )
        assert compute_weekly_view(base + [monday]).weekly_bars == 40


class TestWeeklyWindowCap:
    def test_the_analysed_window_is_capped_at_a_year_of_weeks(self) -> None:
        # The weekly read must depend on this module, not on however much
        # history the caller happened to fetch — otherwise widening the fetch
        # window for unrelated reasons would silently move every weekly rating.
        short = compute_weekly_view(_one_bar_per_week(_MAX_WEEKLY_BARS + 5))
        long = compute_weekly_view(_one_bar_per_week(_MAX_WEEKLY_BARS + 200))

        assert short.weekly_bars == _MAX_WEEKLY_BARS
        assert long.weekly_bars == _MAX_WEEKLY_BARS
        assert long.rating == short.rating
        assert long.verdict == short.verdict
