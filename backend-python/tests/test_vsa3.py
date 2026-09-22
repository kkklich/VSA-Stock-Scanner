"""Tests for VSA 3 (app/analysis/methods/vsa3.py) — the seven-layer loop.

The main fixture is one complete setup, built bar by bar: a weekly uptrend on
bullish volume, an impulse, a quiet pullback to the 50% level ended by a
Stopping Volume accent, a Two Bar Reversal, and a No Supply confirmed by a
Bullish Engulfing — the three-signal sequence absorption -> absorption -> test.
Every keyword breaks exactly one layer, so a test can show which one rejected.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.analysis.methods import get_method, method_ids
from app.analysis.methods import vsa3 as v3
from app.analysis.methods.base import NEVER_FIRED
from app.models import StooqDailyQuote

_Row = tuple[float, float, float, float, int]  # open, high, low, close, volume


def _weekdays(n: int, start: date = date(2025, 1, 6)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _to_bars(rows: list[_Row]) -> list[StooqDailyQuote]:
    """Rows on consecutive weekdays, so the weekly resampling sees real weeks."""
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


def _bar(i: int, o: float, h: float, low: float, c: float, v: int = 200_000) -> StooqDailyQuote:
    """One fully specified bar, ``i`` days after a fixed epoch (detector tests)."""
    return StooqDailyQuote(
        date=date(2026, 1, 1) + timedelta(days=i),
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(low)),
        close=Decimal(str(c)),
        volume=v,
    )


def _advance(up_vol: int = 300_000, down_vol: int = 150_000) -> tuple[list[_Row], float]:
    """A staircase advance (ten bars up, six down, nine times) and an impulse.

    The staircase gives the weekly chart its uptrend and — up-waves trading
    twice the volume of down-waves — the daily chart its bullish volume.
    """
    rows: list[_Row] = []
    c = 100.0
    for _ in range(9):
        for _ in range(10):
            o, c = c, c + 1.0
            rows.append((o, c + 0.3, o - 0.3, c, up_vol))
        for _ in range(6):
            o, c = c, c - 0.8
            rows.append((o, o + 0.3, c - 0.3, c, down_vol))
    for _ in range(12):
        o, c = c, c + 1.2
        rows.append((o, c + 0.3, o - 0.3, c, 300_000))
    return rows, c


def _scenario(
    *,
    tbr: bool = True,
    up_vol: int = 300_000,
    down_vol: int = 150_000,
    weakness_at_peak: bool = False,
    confirm_reach: float = 0.3,
    tail: int = 0,
) -> list[StooqDailyQuote]:
    """One complete Scenario 5, with a keyword to break each layer."""
    rows, c = _advance(up_vol, down_vol)
    origin_low = min(r[2] for r in rows[-18:-12])
    if weakness_at_peak:
        # Effort without result at the top: a wide bar on the highest volume
        # of the move, pushed well above the last close and shut near its low.
        o = rows[-1][0]
        rows[-1] = (o, o + 3.0, o - 0.3, o + 0.3, 320_000)
        c = o + 0.3
    peak_high = max(r[1] for r in rows[-12:])
    target = peak_high - 0.5 * (peak_high - origin_low)  # the 50% level

    # The approach: eight quiet bars on fading volume, down to the level.
    step = (c - (target + 1.2)) / 8
    for k in range(8):
        o, c = c, c - step
        rows.append((o, o + 0.2, c - 0.2, c, 150_000 - k * 5_000))
    # The accent: a Stopping Volume on the level — a down bar closing low on
    # raised volume, then an up bar closing high inside its lower part.
    o, c = c, target + 0.15
    rows.append((o, o + 0.1, target, c, 330_000))
    o, c = c, target + 0.8
    rows.append((o, c + 0.05, target + 0.1, c, 150_000))
    o, c = c, c + 0.4
    rows.append((o, c + 0.1, o - 0.1, c, 120_000))
    if tbr:
        # A Two Bar Reversal on raised volume: the up bar closes above the red
        # bar's open, on more volume than it.
        o1 = c
        o, c = c, target + 0.4
        rows.append((o, o + 0.05, target + 0.3, c, 180_000))
        o, c = c, o1 + 0.1
        rows.append((o, c + 0.05, o - 0.1, c, 240_000))
    # No Supply: a narrow down bar on pink volume...
    ns_open = c
    o, c = c, c - 0.5
    rows.append((o, o + 0.1, c - 0.05, c, 90_000))
    # ...confirmed by an up bar on more volume, which also engulfs its body.
    o, c = c - 0.05, ns_open + confirm_reach
    rows.append((o, c + 0.05, o - 0.05, c, 160_000))
    for _ in range(tail):
        o, c = c, c + 0.1
        rows.append((o, c + 0.2, o - 0.2, c, 110_000))
    return _to_bars(rows)


def _read(bars: list[StooqDailyQuote]) -> tuple[v3._Engine, int, v3._Leg]:
    eng = v3._Engine(bars)
    i = len(bars) - 1
    leg = eng.leg(i)
    assert leg is not None
    return eng, i, leg


# ── Registry ──────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_vsa3_is_registered_after_vsa2(self) -> None:
        ids = method_ids()
        # order: ... glinicki (40) < vsa2 (50) < vsa3 (60)
        assert ids.index("vsa3") > ids.index("vsa2")
        v2, m = get_method("vsa2"), get_method("vsa3")
        assert v2 is not None and m is not None
        assert m.name == "VSA V3"
        assert m.description and m.source and m.source_url
        assert m.direction == "Bullish"  # long-only
        # Same author and course as V2, read from a different layer of it.
        assert m.source != v2.source
        assert "transcripts" in m.source


# ── The complete setup ────────────────────────────────────────────────────────


class TestSetup:
    def test_complete_setup_fires(self) -> None:
        result = get_method("vsa3").evaluate(_scenario())
        assert result.available is True
        assert result.fired is True
        assert result.days_since == 0
        assert result.detail is not None
        assert result.detail.startswith("Bullish Engulfing + No Supply @ 50%")
        assert "R/R" in result.detail
        assert result.score == 100  # all seven layers stand

    def test_every_layer_holds_on_the_fixture(self) -> None:
        eng, i, leg = _read(_scenario())
        assert eng.weekly_trend(i) == "up"
        assert eng.volume_character(i) == "bullish"
        assert eng.place(leg, i) == "50%"
        assert eng.no_supply_at_peak(leg, i) is True
        assert eng.correction(leg, i) == (True, "Stopping Volume")
        seq = eng.sequence(leg, i)
        assert seq is not None
        assert [s.label for s in seq] == ["Stopping Volume", "Two Bar Reversal", "No Supply"]

    def test_signals_mark_the_firing_without_looking_ahead(self) -> None:
        bars = _scenario()
        overlay = get_method("vsa3").signals(bars)
        fired = [s for s in overlay if s.type == "Bullish"]
        assert [(s.label, s.date) for s in fired] == [
            ("Bullish Engulfing + No Supply", bars[-1].date)
        ]
        # Anything else on the chart is a near miss, never a second entry.
        assert {s.type for s in overlay} <= {"Bullish", "Watch"}
        # Whatever happens afterwards cannot move a marker already printed.
        later = get_method("vsa3").signals(_scenario(tail=6))
        assert fired[0] in later

    def test_recency_reported_after_the_setup(self) -> None:
        bars = _scenario(tail=4)
        result = get_method("vsa3").evaluate(bars)
        assert result.fired is False
        assert result.days_since == (bars[-1].date - bars[-5].date).days
        assert result.detail == f"Bullish Engulfing + No Supply {result.days_since}d ago"

    def test_two_signals_are_not_a_sequence(self) -> None:
        # Without the Two Bar Reversal, the pullback's low carries only the
        # Stopping Volume and the No Supply. Everything else still stands, so it
        # is the sequence gate — "three signals following one another" — that
        # refuses the trade: the course says to wait for the next signal.
        bars = _scenario(tbr=False)
        eng, i, leg = _read(bars)
        assert eng.place(leg, i) is not None
        assert eng.correction(leg, i) == (True, "Stopping Volume")
        assert eng.sequence(leg, i) is None
        result = get_method("vsa3").evaluate(bars)
        assert result.fired is False
        assert result.score == round(5 / 7 * 100)
        # The reader is told the method saw the pattern, and why it said no.
        assert result.detail == (
            "Bullish Engulfing + No Supply today, not taken: no 3-signal sequence"
        )

    def test_bearish_volume_is_never_played(self) -> None:
        # The same prices with the volume swapped: the down-waves now trade
        # twice the up-waves. "Never play against the volume in the scale you
        # play" — nothing else about the picture changed.
        bars = _scenario(up_vol=150_000, down_vol=300_000)
        eng, i, leg = _read(bars)
        assert eng.volume_character(i) == "bearish"
        assert eng.weekly_trend(i) == "up"
        assert get_method("vsa3").evaluate(bars).fired is False

    def test_weakness_at_the_peak_kills_the_setup(self) -> None:
        bars = _scenario(weakness_at_peak=True)
        eng, i, leg = _read(bars)
        assert eng.weakness(leg.peak) is not None
        assert eng.no_supply_at_peak(leg, i) is False
        assert get_method("vsa3").evaluate(bars).fired is False

    def test_reward_to_risk_below_three_to_one_is_rejected(self) -> None:
        # The confirmation bar closes 3 points up: the stop (under the
        # formation) is far and the peak is near. Every reading of the market
        # still holds — six of seven layers — and arithmetic alone refuses it.
        bars = _scenario(confirm_reach=3.0)
        eng, i, leg = _read(bars)
        formation = v3._formation_at(eng.s, i)
        assert formation is not None
        rr = (eng.s.highs[leg.peak] - formation.entry) / (formation.entry - formation.stop)
        assert rr < 3.0
        result = get_method("vsa3").evaluate(bars)
        assert result.fired is False
        assert result.score == round(6 / 7 * 100)
        assert result.detail == f"Bullish Engulfing + No Supply today, not taken: R/R {rr:.1f}:1"

    def test_a_correction_without_its_accent_waits(self) -> None:
        # One bar before the Stopping Volume completes, the pullback is quiet
        # and fading — corrective — but nothing has ended it yet.
        bars = _scenario()
        eng = v3._Engine(bars)
        accent_start = next(
            j for j in range(len(bars)) if (s := eng.strength(j)) and s.label == "Stopping Volume"
        ) - 1
        truncated = bars[: accent_start + 1]
        eng, i, leg = _read(truncated)
        assert eng.correction(leg, i) == (True, None)
        assert get_method("vsa3").evaluate(truncated).fired is False


# ── A real case: Alior Bank, 15.09.2026 ───────────────────────────────────────


def _alior(until: date | None = None) -> list[StooqDailyQuote]:
    from tests.data_alr_2026 import ALR_BARS

    bars = [
        StooqDailyQuote(
            date=date.fromisoformat(d),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(low)),
            close=Decimal(str(c)),
            volume=v,
        )
        for d, o, h, low, c, v in ALR_BARS
    ]
    return [b for b in bars if until is None or b.date <= until]


class TestAliorHammer:
    """The owner's example: a Hammer at the low of Alior's pullback.

    The method must SEE it — the Hammer, the Shakeout on 2.5x average volume
    that confirms it, the end of an ABC correction as the place — and refuse it
    for exactly the two reasons the course gives: 3:1 is not on offer to the
    04.08 peak (entry 132.00, stop 127.50 under the shadow, target 143.70 —
    2.6:1), and no test has followed the Shakeout to close a sequence.
    """

    def test_the_hammer_is_seen_and_refused_for_two_reasons(self) -> None:
        bars = _alior(until=date(2026, 9, 15))
        eng = v3._Engine(bars)
        found = v3._assess(eng, len(bars) - 1)
        assert found is not None
        assert (found.formation, found.signal, found.place) == ("Hammer", "Shakeout", "ABC")
        assert found.missing == ("no 3-signal sequence", "R/R 2.6:1")
        result = get_method("vsa3").evaluate(bars)
        assert result.fired is False
        assert result.detail == (
            "Hammer + Shakeout today, not taken: no 3-signal sequence, R/R 2.6:1"
        )

    def test_the_second_low_is_a_textbook_wfo_once_price_reacts(self) -> None:
        # 01.09 traded 605k at the first low; 15.09 undercut it on less (497k)
        # but more than every bar between; the Shakeout sits on it; and 17.09
        # closed above its high — all eight conditions.
        bars = _alior(until=date(2026, 9, 17))
        eng = v3._Engine(bars)
        i = len(bars) - 1
        leg = eng.leg(i)
        assert leg is not None
        assert eng.wfo(leg, i) is True

    def test_nothing_fires_and_the_newest_candidate_is_reported(self) -> None:
        bars = _alior()
        assert [s for s in get_method("vsa3").signals(bars) if s.type == "Bullish"] == []
        # By 22.09 a newer pattern at the low (21.09) is the one reported.
        result = get_method("vsa3").evaluate(bars)
        assert result.detail == (
            "Piercing Line + Two Bar Reversal 1d ago, not taken: "
            "no 3-signal sequence, R/R 0.4:1"
        )

    def test_the_hammer_is_marked_on_the_chart_as_a_near_miss(self) -> None:
        # The complaint that started this: the chart showed nothing at all, so
        # the method looked blind to a textbook hammer. It now marks the bar —
        # as a "Watch", not a trade — and says what was missing.
        overlay = get_method("vsa3").signals(_alior())
        watch = [s for s in overlay if s.date == date(2026, 9, 15)]
        assert len(watch) == 1
        assert watch[0].type == "Watch"
        assert watch[0].label == "Hammer + Shakeout · no sequence, R/R 2.6:1"


# ── The superior timeframe ────────────────────────────────────────────────────


def _weeks(highs: list[float], lows: list[float]) -> list[v3._Week]:
    return [v3._Week(h, low, (h + low) / 2) for h, low in zip(highs, lows, strict=True)]


class TestWeeklyTrend:
    def test_higher_high_and_higher_low_is_an_uptrend(self) -> None:
        older = _weeks([110.0] * 13, [100.0] * 13)
        recent = _weeks([115.0] * 13, [104.0] * 13)
        assert v3._weekly_trend(older + recent) == "up"
        assert v3._weekly_trend(recent + older) == "down"

    def test_a_steady_advance_is_an_uptrend(self) -> None:
        # Every week's low above the last: no weekly swing low ever prints, which
        # is why the trend is read over two quarters, not over swing points.
        weeks = _weeks([100.0 + k for k in range(26)], [95.0 + k for k in range(26)])
        assert v3._weekly_trend(weeks) == "up"

    def test_an_expanding_or_contracting_range_is_undecided(self) -> None:
        older = _weeks([110.0] * 13, [100.0] * 13)
        wider = _weeks([112.0] * 13, [98.0] * 13)
        narrower = _weeks([108.0] * 13, [102.0] * 13)
        assert v3._weekly_trend(older + wider) == "undecided"
        assert v3._weekly_trend(older + narrower) == "undecided"

    def test_under_half_a_year_is_undecided(self) -> None:
        weeks = _weeks([100.0 + k for k in range(25)], [95.0 + k for k in range(25)])
        assert v3._weekly_trend(weeks) == "undecided"


# ── The place: WFO and ABC ────────────────────────────────────────────────────


def _wfo_bars(*, loud_bar_between: bool = False) -> list[StooqDailyQuote]:
    """A pullback to D1 on heavy volume, a bounce, and a lower D2 on less."""
    rows, c = _advance()
    for k in range(5):
        o, c = c, c - 0.9
        rows.append((o, o + 0.2, c - 0.2, c, 140_000 - k * 5_000))
    o, c = c, c - 1.0
    low1 = c - 0.3
    rows.append((o, o + 0.2, low1, c, 600_000))  # D1, on high volume
    for k in range(4):
        o, c = c, c + 0.9
        volume = 300_000 if (loud_bar_between and k == 1) else 110_000
        rows.append((o, c + 0.2, o - 0.2, c, volume))
    for _ in range(3):
        o, c = c, c - 1.0
        rows.append((o, o + 0.2, c - 0.2, c, 100_000))
    o = c
    rows.append((o, o + 0.2, low1 - 1.4, o - 0.1, 250_000))  # D2: a Shakeout
    o, c = o - 0.1, o + 1.2
    rows.append((o, c + 0.1, o - 0.2, c, 180_000))  # the reaction
    return _to_bars(rows)


def _abc_bars(*, c_volume: int = 120_000) -> list[StooqDailyQuote]:
    """A three-wave pullback: A down, B up, C down below A."""
    rows, c = _advance()
    for _ in range(5):
        o, c = c, c - 1.0
        rows.append((o, o + 0.2, c - 0.2, c, 140_000))
    for _ in range(3):
        o, c = c, c + 1.3
        rows.append((o, c + 0.2, o - 0.2, c, 130_000))
    for _ in range(6):
        o, c = c, c - 1.2
        rows.append((o, o + 0.2, c - 0.2, c, c_volume))
    o, c = c, c + 0.3
    rows.append((o, c + 0.1, o - 0.1, c, 110_000))
    return _to_bars(rows)


class TestPlace:
    def test_bullish_wfo(self) -> None:
        eng, i, leg = _read(_wfo_bars())
        assert eng.strength(leg.halt) is not None  # condition 7: a signal at D2
        assert eng.wfo(leg, i) is True

    def test_wfo_second_low_must_outtrade_every_bar_between(self) -> None:
        # Condition 6, "the one easiest to miss": if any bar between the two
        # lows traded more than D2, it is not a WFO at all.
        eng, i, leg = _read(_wfo_bars(loud_bar_between=True))
        assert eng.wfo(leg, i) is False

    def test_end_of_an_abc_correction(self) -> None:
        eng, i, leg = _read(_abc_bars())
        assert eng.abc(leg, i) is True

    def test_abc_needs_a_c_wave_on_corrective_volume(self) -> None:
        eng, i, leg = _read(_abc_bars(c_volume=350_000))
        assert eng.abc(leg, i) is False


# ── Signals and the sequence ──────────────────────────────────────────────────


def _sig(category: str, volume: float = 100_000.0, label: str = "X") -> v3._Signal:
    return v3._Signal(label, category, 0, 0, 0.0, volume)


class TestSequence:
    def test_the_courses_sequences_are_valid(self) -> None:
        ok = v3._valid_sequence
        clim, absb, test = "climactic", "absorbing", "testing"
        assert ok(_sig(clim), _sig(absb), _sig(test))  # SA -> SZP -> ST
        assert ok(_sig(absb), _sig(absb), _sig(test))  # SV -> SV -> Test
        # absorption -> test -> a test on still lower volume
        assert ok(_sig(absb), _sig(test, 200_000), _sig(test, 100_000))
        # accumulation or absorption -> test -> a Shakeout on large volume
        assert ok(_sig(clim), _sig(test), _sig(absb, label="Shakeout"))

    def test_senseless_sequences_are_refused(self) -> None:
        ok = v3._valid_sequence
        clim, absb, test = "climactic", "absorbing", "testing"
        assert not ok(_sig(test), _sig(absb), _sig(test))  # opens with a test
        assert not ok(_sig(test), _sig(test), _sig(clim))  # the reversed order
        assert not ok(_sig(absb), _sig(test, 100_000), _sig(test, 200_000))  # louder test
        assert not ok(_sig(clim), _sig(absb), _sig(absb))  # never tested
        assert not ok(_sig(absb), _sig(test), _sig(absb, label="Two Bar Reversal"))


def _flat(n: int = 40) -> list[StooqDailyQuote]:
    return [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(n)]


class TestSignals:
    def test_pink_volume_and_the_up_bar_are_the_courses_own_rules(self) -> None:
        bars = [
            _bar(0, 100.0, 101.0, 99.0, 100.0, 300_000),
            _bar(1, 100.0, 101.0, 99.0, 100.0, 200_000),
            _bar(2, 101.0, 101.2, 100.2, 100.5, 100_000),  # red body, higher close
        ]
        s = v3._Series.build(bars)
        assert s.is_pink(2) is True  # lower than each of the previous two
        # An up bar closes above the PREVIOUS CLOSE, whatever its colour.
        assert s.is_up_bar(2) is True
        assert s.is_pink(1) is False  # only one earlier bar to compare with

    def test_two_bar_reversal_volume_decides_what_it_is(self) -> None:
        def pair(v1: int, v2: int) -> v3._Signal | None:
            bars = [*_flat(), _bar(40, 100.0, 100.2, 97.8, 98.0, v1)]
            bars.append(_bar(41, 98.0, 100.3, 97.9, 100.1, v2))
            return v3._two_bar_reversal(v3._Series.build(bars), 41)

        loud = pair(200_000, 300_000)
        assert loud is not None and loud.category == "absorbing"
        quiet = pair(100_000, 120_000)
        assert quiet is not None and quiet.category == "testing"
        # "V2 > V1 is a necessary condition" — a quieter up bar is not one.
        assert pair(300_000, 200_000) is None

    def test_no_supply_is_confirmed_by_a_louder_up_bar(self) -> None:
        def pair(confirm_volume: int) -> v3._Signal | None:
            bars = [*_flat(), _bar(40, 100.0, 100.3, 99.4, 99.5, 150_000)]
            bars.append(_bar(41, 99.5, 99.6, 99.0, 99.1, 90_000))  # narrow, pink
            bars.append(_bar(42, 99.1, 100.0, 99.0, 99.8, confirm_volume))
            return v3._no_supply(v3._Series.build(bars), 42)

        signal = pair(120_000)
        assert signal is not None
        assert (signal.label, signal.start, signal.bar) == ("No Supply", 41, 42)
        # Without the increase "the confirmation is ambiguous and he passes".
        assert pair(80_000) is None

    def test_a_test_needs_earlier_absorption_in_its_zone(self) -> None:
        # "A test with no link to the left side of the chart carries no
        # information": the same quiet bar with a lower shadow is a Test after
        # a Shakeout at that price, and nothing without one.
        def bars_with(shakeout: bool) -> list[StooqDailyQuote]:
            bars = _flat()
            if shakeout:
                bars.append(_bar(40, 99.5, 100.4, 97.5, 100.2, 300_000))
            else:
                bars.append(_bar(40, 100.0, 101.0, 99.0, 100.0))
            bars += [_bar(41 + k, 100.0, 101.0, 99.0, 100.0) for k in range(3)]
            bars.append(_bar(44, 99.9, 100.3, 98.1, 100.2, 100_000))  # the test
            bars.append(_bar(45, 100.2, 100.9, 100.0, 100.6, 150_000))  # up bar
            return bars

        eng = v3._Engine(bars_with(shakeout=True))
        assert eng.strength(40) is not None and eng.strength(40).label == "Shakeout"
        test = eng.strength(45)
        assert test is not None and test.label == "Test"
        assert v3._Engine(bars_with(shakeout=False)).strength(45) is None


# ── Guards ────────────────────────────────────────────────────────────────────


class TestGuards:
    def test_downtrend_never_fires_and_scores_low(self) -> None:
        # A steady collapse: no pullback to buy, a weekly downtrend, and a score
        # under the analytics summary's bullish-lean threshold.
        rows = [
            (c + 0.8, c + 1.2, c - 0.4, c, 300_000 if k % 3 else 700_000)
            for k, c in ((k, 400.0 - k * 1.2) for k in range(200))
        ]
        bars = _to_bars(rows)
        result = get_method("vsa3").evaluate(bars)
        assert result.fired is False
        assert result.days_since == NEVER_FIRED
        assert result.score < 50
        assert get_method("vsa3").signals(bars) == []

    def test_new_highs_report_no_pullback(self) -> None:
        closes = [100.0 + k * 0.6 for k in range(200)]
        rows = [(c - 0.5, c + 0.4, c - 0.7, c, 200_000) for c in closes]
        result = get_method("vsa3").evaluate(_to_bars(rows))
        assert result.available is True
        assert result.fired is False
        assert result.detail == "No pullback setup"

    def test_short_history_is_unavailable(self) -> None:
        short = _scenario()[:120]
        assert get_method("vsa3").evaluate(short).available is False
        assert get_method("vsa3").signals(short) == []

    def test_frozen_and_empty_series_never_raise(self) -> None:
        frozen = [_bar(i, 10.0, 10.0, 10.0, 10.0, 0) for i in range(200)]
        assert get_method("vsa3").evaluate(frozen).fired is False
        assert get_method("vsa3").signals(frozen) == []
        assert get_method("vsa3").evaluate([]).available is False
        assert get_method("vsa3").signals([]) == []
