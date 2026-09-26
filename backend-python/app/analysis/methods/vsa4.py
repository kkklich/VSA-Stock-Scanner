"""VSA V4 — the owner's own VSA program, run as a trading method.

Source: the "VSA - kompendium i program Python" package Krzysztof supplied on
2026-09-24 — a compendium of Rafał Glinicki's 30-lesson VSA course (XTB
*Investing Masters*) and his four 2018 webinars, synthesised from the lesson
transcripts and maps with every rule marked [K] course / [M] map /
[F] formalisation / [L] gap, plus a standard-library Python program that
formalises it. The program is vendored unchanged in ``app/analysis/vsa4``;
this module only adapts it to the app's method contract.

**What it trades** — the compendium's §5 "test as a process" and §6 sequences
(lessons 21, 23), exactly as the program's ``long_setup_confirmation``:

    1. a **primary strength** signal: Bag Holding, Selling Climax, Stopping
       Volume, Shakeout, Two Bar Reversal or a bullish WFO;
    2. within 30 sessions, a **secondary test**: No Supply or Test (a retest of
       the strength's zone on low volume);
    3. within 3 sessions of the test, a **confirmation**: an Up Bar closing
       above the test bar's high on more volume than it.

A weakness signal, or a low more than a tick under the strength's level,
cancels the sequence (the program's invalidation). The program then enters at
the next open with a structural stop under the sequence and a 3R target — that
part is the stock page's trade simulation (``adapter.simulate``).

How V4 differs from V2/V3, which read the same course: V2 and V3 mechanise
lesson 29's Scenario 5 (a pullback to a measured place, a candle formation,
R/R ≥ 3 to the prior peak) and are rare by construction (V3 completes ~4 times
in the whole stored history). V4 is the sequence from lessons 21/23 without
the Scenario-5 layers — the program says so itself ("nie implementuje całego
scenariusza nr 5") — so it fires far more often: 2.3 times per ticker-year on
GPW history. It is also **two-sided**: the program detects the weakness
mirror (primary weakness → No Demand → a Down Bar closing under it), which
this method reports as bearish context and draws as bearish chart markers,
while its entry — the thing ``fired`` and the back-test judge — stays long.

**Score** — where the program's sequence stands after the last close. It
climbs as the long sequence builds and drops below the nothing-in-play 35 when
the weakness mirror is in play, because the program reads both sides:

    100  a long setup confirmed on the last bar (``fired``)
     85  one confirmed in the last 10 sessions whose stop and 3R target are
         both still untouched (the trade is live)
     65  a No Supply / Test after a strength, awaiting its confirmation bar
     50  a strength signal in the background, awaiting a test
     35  neither side has anything in play
     20  a weakness signal in the background
     10  a No Demand after a weakness, awaiting its confirmation bar
      5  a short setup confirmed in the last 10 sessions, still live
      0  a short setup confirmed on the last bar

The first matching line wins, long side first at each stage.

**Window.** The program's state at a bar depends on at most ~110 bars before
it (20-bar baselines, a 40-bar test look-back over strength flags that may be
WFOs, which themselves look 40 bars back for the previous pivot, plus the
30-session sequence window). ``evaluate`` therefore analyses only the last
``_EVAL_BARS`` sessions — the engine costs ~85 ms per 1,000 bars, ten times
the other methods — and reads recency only from bars more than
``_WARMUP_BARS`` into that slice, which are computed exactly as on the whole
history (``tests/test_vsa4.py`` pins this on real bars).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    register_method,
)
from app.analysis.vsa import VsaConfig
from app.analysis.vsa4.adapter import (
    analyze_quotes,
    label,
    sequence_state,
    setup_label,
)
from app.analysis.vsa4.engine import Config
from app.models import StooqDailyQuote

# Minimum stored sessions to evaluate at all (two months): the program's
# baselines need 20 bars and its trend read 21, and a sequence needs room for a
# strength, a test and a confirmation after that. The program's own 45-bar
# sample completes its setup on bar 27.
_MIN_BARS = 40
# How many of an analysed slice's first bars may still depend on history
# before it (the ~110-bar bound in the module docstring, rounded up)...
_WARMUP_BARS = 120
# ...and the slice ``evaluate`` analyses: the warm-up plus 40 exact sessions
# (~8 weeks) to read recency from. That covers everything the score looks at
# (a background leg is at most 30 sessions old) and the dashboard's "fired
# recently" chip (15 days); an older setup reads as "not recently". The
# engine costs ~85 ms per 1,000 bars, so the slice, not the stored history,
# sets what this method adds to a ranking build (~14 ms a stock).
_EVAL_BARS = _WARMUP_BARS + 40
# A confirmed setup this recent (sessions), stop and target untouched, is live.
_LIVE_SESSIONS = 10

_SCORE_FIRED = 100
_SCORE_LIVE = 85
_SCORE_PENDING = 65
_SCORE_BACKGROUND = 50
_SCORE_NEUTRAL = 35
_SCORE_WEAK_BACKGROUND = 20
_SCORE_WEAK_PENDING = 10
_SCORE_SHORT_LIVE = 5
_SCORE_SHORT_FIRED = 0


def _fmt_price(value: float) -> str:
    """A stop level at a sensible precision (penny stocks need four places)."""
    return f"{value:.2f}" if abs(value) >= 1 else f"{value:.4f}"


def _trade_live(
    rows: list[dict[str, Any]],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    i: int,
    direction: int,
    reward_risk: float,
) -> bool:
    """Is the setup confirmed on bar ``i`` still an open trade at the last bar?

    Mirrors the program's own trade: entry at the next bar's open, the setup's
    stop, a target ``reward_risk`` times the entry-to-stop distance away. Live
    means neither level has been touched since the entry (and the entry did
    not gap through the stop, which the program treats as "no trade").
    """
    stop = rows[i].get("setup_stop_level")
    if stop is None or i + 1 >= len(opens):
        return False
    entry = opens[i + 1]
    distance = direction * (entry - float(stop))
    if distance <= 0:
        return False
    target = entry + direction * distance * reward_risk
    for j in range(i + 1, len(opens)):
        if direction > 0 and (lows[j] <= stop or highs[j] >= target):
            return False
        if direction < 0 and (highs[j] >= stop or lows[j] <= target):
            return False
    return True


@register_method
class Vsa4(TradingMethod):
    id = "vsa4"
    order = 65
    name = "VSA V4"
    description = (
        "Rafal Glinicki's VSA course as formalised by the owner's own Python "
        "program (the \"VSA - kompendium\" package): the test-as-a-process "
        "sequence from lessons 21 and 23. It fires when a signal of strength "
        "(Bag Holding, Selling Climax, Stopping Volume, Shakeout, Two Bar "
        "Reversal or a bullish WFO) is followed within 30 sessions by a quiet "
        "retest — No Supply or a Test of the strength's zone on low volume — "
        "and, within three sessions of that test, an up bar closes above the "
        "test's high on more volume. A weakness signal or a break under the "
        "strength's low cancels it. The score says where that sequence stands "
        "today: 50 = a strength waiting for its test, 65 = a test waiting for "
        "confirmation, 100 = confirmed today, 35 = nothing in play, and lower "
        "when the weakness mirror is in play. "
        "The stock page's trade simulation runs the same program's own "
        "back-tester: next-open entry, a stop under the sequence, a 3:1 target. "
        "Long entries; the weakness mirror is shown as bearish context."
    )
    source = (
        "Rafal Glinicki — \"Analiza ceny i wolumenu\" (XTB Investing Masters, "
        "30 lessons) and his 2018 VSA course (4 lessons), as synthesised and "
        "formalised in the owner's \"VSA - kompendium i program Python\" "
        "(2026-09-24): lessons 7-13 (signals), 21 (testing), 23-26 "
        "(sequences, WFO)"
    )
    source_url = "https://www.xtb.com/pl/edukacja/investing-masters"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,  # the program's own thresholds; unused
        *,
        rs_rank: float | None = None,  # cross-sectional; not used by this method
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")
        cut = len(bars) > _EVAL_BARS
        window = list(bars)[-_EVAL_BARS:] if cut else list(bars)
        try:
            ebars, dates, rows = analyze_quotes(window)
        except ValueError:  # VSAError: data the adapter could not repair
            return MethodResult.unavailable("Invalid price data")
        if len(rows) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")

        last = len(rows) - 1
        last_date = dates[last]
        first_exact = _WARMUP_BARS if cut else 0
        opens = [b.open for b in ebars]
        highs = [b.high for b in ebars]
        lows = [b.low for b in ebars]
        rr = Config().reward_risk  # the program's 3R, which config_for keeps

        # Newest confirmed setup on each side within the exact region.
        long_i = next(
            (i for i in range(last, first_exact - 1, -1) if rows[i]["long_setup_confirmation"]),
            None,
        )
        short_i = next(
            (i for i in range(last, first_exact - 1, -1) if rows[i]["short_setup_confirmation"]),
            None,
        )
        days_since = NEVER_FIRED if long_i is None else (last_date - dates[long_i]).days
        state = sequence_state(rows[last])

        def recent_live(i: int | None, direction: int) -> bool:
            return (
                i is not None
                and last - i <= _LIVE_SESSIONS
                and _trade_live(rows, opens, highs, lows, i, direction, rr)
            )

        if long_i == last:
            score = _SCORE_FIRED
            stop = float(rows[last]["setup_stop_level"])
            detail = f"{setup_label(rows[last])} confirmed, stop {_fmt_price(stop)}"
        elif short_i == last:
            score = _SCORE_SHORT_FIRED
            detail = f"Weakness: {setup_label(rows[last])} confirmed"
        elif recent_live(long_i, +1):
            score = _SCORE_LIVE
            detail = f"{setup_label(rows[long_i])} {days_since}d ago, trade live"
        elif recent_live(short_i, -1):
            score = _SCORE_SHORT_LIVE
            age = (last_date - dates[short_i]).days
            detail = f"Weakness: {setup_label(rows[short_i])} {age}d ago"
        elif state.long_pending is not None:
            score = _SCORE_PENDING
            leg = state.long_pending
            detail = f"{label(leg.primary)} → {label(leg.secondary)}, awaiting confirmation"
        elif state.short_pending is not None:
            score = _SCORE_WEAK_PENDING
            leg = state.short_pending
            detail = f"Weakness: {label(leg.primary)} → {label(leg.secondary)} pending"
        elif state.long_background is not None:
            score = _SCORE_BACKGROUND
            leg = state.long_background
            age = (last_date - leg.on).days
            detail = f"Strength: {label(leg.primary)} {age}d ago, awaiting a test"
        elif state.short_background is not None:
            score = _SCORE_WEAK_BACKGROUND
            leg = state.short_background
            age = (last_date - leg.on).days
            detail = f"Weakness: {label(leg.primary)} {age}d ago"
        else:
            score = _SCORE_NEUTRAL
            detail = f"Last setup {days_since}d ago" if long_i is not None else "No sequence"

        return MethodResult(
            score=score,
            days_since=days_since,
            fired=days_since == 0,
            detail=detail,
            available=True,
        )

    def signals(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> list[MethodSignal]:
        """Chart markers, oldest first.

        * ``"Bullish"`` — every confirmed long setup (the program's
          ``long_setup_confirmation``), labelled "primary → test". The only
          kind the back-test judges.
        * ``"Bearish"`` — every confirmed short setup, the weakness mirror.
          Context, never a trade here.
        * ``"Watch"`` — the test the program is waiting on right now, if any:
          a strength and a No Supply/Test are in place and the next bar or two
          can still confirm it. It marks what the score's "awaiting
          confirmation" refers to, so the chart and the dashboard agree.
        """
        if len(bars) < _MIN_BARS:
            return []
        try:
            _, dates, rows = analyze_quotes(bars)
        except ValueError:
            return []
        out: list[MethodSignal] = []
        for d, row in zip(dates, rows, strict=True):
            if row["long_setup_confirmation"]:
                out.append(MethodSignal(date=d, label=setup_label(row), type="Bullish"))
            elif row["short_setup_confirmation"]:
                out.append(MethodSignal(date=d, label=setup_label(row), type="Bearish"))
        if rows:
            pending = sequence_state(rows[-1]).long_pending
            if pending is not None:
                out.append(
                    MethodSignal(
                        date=pending.on,
                        label=(
                            f"{label(pending.primary)} → {label(pending.secondary)}"
                            " · awaiting confirmation"
                        ),
                        type="Watch",
                    )
                )
                out.sort(key=lambda s: s.date)
        return out
