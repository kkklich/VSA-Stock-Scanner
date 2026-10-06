"""Weinstein Stage 1->2 breakout — a weekly, volume-based, long-only method.

Source: Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets*
(1988). Weinstein reads every chart on the **weekly** timeframe and splits a
stock's life into four stages around its **30-week moving average**:

    Stage 1  basing    — after a decline the stock goes sideways for months and
                         the 30-week MA loses its downward slope and flattens.
    Stage 2  advancing — it breaks out of that base and runs. **Buy here.**
    Stage 3  topping   — it goes sideways again, at the top.
    Stage 4  declining — it falls. Stay away.

The whole method is about buying the moment **Stage 1 turns into Stage 2** —
the breakout out of a long, boring base — which is exactly the kind of setup
this app is for: volume-confirmed, held for weeks-to-months, and long-only.

A breakout **fires** on a completed weekly bar when all of these hold:

    1. The prior ~20 weeks formed a tight sideways range (the Stage 1 base).
    2. The week closes **above the top of that base** — the breakout itself.
    3. The week closes **above the 30-week moving average**.
    4. The 30-week MA has **stopped falling** (it is no lower than it was ten
       weeks ago) — Weinstein's test that Stage 4 is over.
    5. The 30-week MA is **not already in a mature advance** (it has not risen
       more than 10% over those ten weeks) — see "Why the rise cap" below.
    6. Weekly volume is **at least 2x the average of the prior ten weeks** —
       the demand that separates a real breakout from a drift through
       resistance.

**Evidence.** Thomas Bulkowski sorted 440 of his own real trades (1987-2010,
net of costs) by the stage he bought in (thepatternsite.com/Stages.html):
buys at the Stage 1->2 breakout returned **+13.2% with 69% winners** (n=127);
buys well inside Stage 2 returned **+4.1% with 57% winners** (n=116); Stage 3
and 4 buys lost money. Those are one trader's discretionary trades rather than
a mechanical test, so this method still has to prove itself on the app's own
back-test gate (``GET /api/stocks/methods/weinstein/backtest``).

**Why the rise cap (rule 5).** Rules 1-4 alone would also fire on a stock that
has already run a long way and merely paused: a flat 20-week base sitting on
top of a steep advance still has a steeply *rising* 30-week MA. That is
Bulkowski's late-Stage-2 buy, the one that earned a third as much. Capping the
MA's ten-week rise is what keeps this method on the **transition** Weinstein
actually buys, and it is what makes it a different question from the Minervini
Trend Template (which deliberately fires while a stock is already in Stage 2,
and which fails this app's GPW back-test gate).

**Why weekly.** Weinstein's stages, his moving average and his volume test are
all defined on weekly bars, so running them on daily ones would be a different
rule wearing his name. The weekly candles are aggregated from the daily bars
the app already stores (``app.analysis.weekly.resample_weekly``) — no new data
source and nothing extra to download. The **forming week is dropped**: a
part-built weekly bar carries a fraction of a real week's volume (measured on a
Monday: 0.20x the 20-week average), which would make the 2x volume test
unanswerable, and Weinstein buys on a weekly *close*. So during the week the
method reports the last completed week's read: a breakout week shows as
"fired" on its closing session (and over the weekend), and from Monday on as
"broke out N days ago" — the age is counted from the newest daily bar.

**Not gated: the prior decline.** Weinstein's Stage 1 follows a Stage 4
decline. That is not a separate condition here, because the stock may have been
basing for a year or more and the decline would then sit outside the window the
app holds — and rules 4 and 5 already pin the MA to the flat, post-decline
shape that defines Stage 1. Rejecting long bases to enforce a condition the
data often cannot see would cost more than it buys.

KNOWN SCOPE: the thresholds above are Weinstein's own numbers (30-week MA, 2x
volume) plus two mechanical readings of his prose (how tight a base is, how
flat a flat MA is). The method must clear the app's GPW back-test gate at a
multi-week horizon before its score is trusted with money — a base breakout
takes weeks to pay, so judging it at ten sessions would be judging it before
the trade has happened.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    register_method,
)
from app.analysis.vsa import VsaConfig
from app.analysis.weekly import resample_weekly, trailing_week_is_complete
from app.models import StooqDailyQuote

# Weinstein's moving average: 30 WEEKS, the spine of the whole method.
_MA_WEEKS = 30
# The Stage 1 base: the sideways range immediately before the breakout week.
# Weinstein asks for "several months"; 20 weeks is a touch under five.
_BASE_WEEKS = 20
# How tight that range must be to count as a base rather than a stock still
# trending: high->low within this fraction of the base top.
_BASE_MAX_DEPTH = 0.30
# The span over which the 30-week MA must have stopped falling (~2.5 months).
_MA_FLAT_WEEKS = 10
# ...and over which it must NOT have risen more than this, or the stock is
# already well inside Stage 2 (see "Why the rise cap" in the module docstring).
_MA_MAX_RISE = 0.10
# Volume baseline: the average weekly volume of the prior ten weeks, the window
# the verified GPW example in agent/ROADMAP.md #28 was measured against.
_VOL_WEEKS = 10
# Weinstein's breakout volume test: at least twice that baseline.
_VOL_MULT = 2.0
# Posture rule: price no more than this far above the base top still counts as
# "in the buy zone". Beyond it the Stage 1->2 entry has been and gone and the
# buy is Bulkowski's late-Stage-2 one.
_MAX_EXTENSION = 0.20
# Posture rule: a breakout within this many weeks is a "fresh" one.
_RECENT_WEEKS = 4
# How far back to scan for the most recent breakout when reporting days_since.
_RECENCY_SCAN_WEEKS = 26
# Posture-checklist size the score is scaled against.
_TOTAL_RULES = 6
# Minimum completed weekly bars to evaluate at all. The binding constraint is
# rules 4/5, which need the 30-week MA as it stood _MA_FLAT_WEEKS ago: 30 + 10
# (~40 weeks, so a stock listed less than a year ago is correctly unavailable).
_MIN_WEEKS = _MA_WEEKS + _MA_FLAT_WEEKS


def _completed_weeks(bars: Sequence[StooqDailyQuote]) -> list[StooqDailyQuote]:
    """Weekly candles from daily bars, with the still-forming week dropped.

    The forming week is dropped because Weinstein's entry is a weekly *close*
    above the base on a full week's volume; a Monday-to-Wednesday stub has
    neither, and letting it through would answer the 2x volume test with a
    fifth of a week's volume.
    """
    weekly = resample_weekly(bars)
    if weekly and not trailing_week_is_complete(bars):
        weekly = weekly[:-1]
    return weekly


def _sma(values: Sequence[float], length: int, end_idx: int) -> float | None:
    """Simple moving average over ``length`` bars ending at ``end_idx`` (or None)."""
    start = end_idx - length + 1
    if start < 0:
        return None
    return sum(values[start : end_idx + 1]) / length


def _mean(values: Sequence[float], start: int, end: int) -> float:
    """Mean of ``values[start:end]`` (0.0 for an empty slice)."""
    seg = values[start:end]
    return sum(seg) / len(seg) if seg else 0.0


def _base_is_tight(highs: Sequence[float], lows: Sequence[float], idx: int) -> bool:
    """Did the ``_BASE_WEEKS`` weeks *before* ``idx`` form a tight sideways range?"""
    if idx < _BASE_WEEKS:
        return False
    top = max(highs[idx - _BASE_WEEKS : idx])
    low = min(lows[idx - _BASE_WEEKS : idx])
    if top <= 0 or low <= 0:
        return False
    return (top - low) / top <= _BASE_MAX_DEPTH


def _ma_pair(closes: Sequence[float], idx: int) -> tuple[float, float] | None:
    """The 30-week MA now and ``_MA_FLAT_WEEKS`` weeks ago, or None if unknowable."""
    ma = _sma(closes, _MA_WEEKS, idx)
    ma_prev = _sma(closes, _MA_WEEKS, idx - _MA_FLAT_WEEKS)
    if ma is None or ma_prev is None or ma_prev <= 0 or ma <= 0:
        return None
    return ma, ma_prev


def _breakout_fired(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    idx: int,
) -> bool:
    """Whether a Stage 1->2 breakout fires on completed weekly bar ``idx``.

    All six conditions from the module docstring must hold; they are checked
    cheapest-first so the common "no breakout" case costs almost nothing.
    """
    if idx < _MIN_WEEKS - 1:
        return False

    pair = _ma_pair(closes, idx)
    if pair is None:
        return False
    ma, ma_prev = pair

    close = closes[idx]
    # 3: the week closes above the 30-week MA (the Stage 2 side of the line).
    if close <= ma:
        return False
    # 4: the MA has stopped falling — Stage 4 is over.
    if ma < ma_prev:
        return False
    # 5: ...but has not already run away, which would make this a pause inside
    #    a mature Stage 2 rather than the transition out of Stage 1.
    if ma > ma_prev * (1.0 + _MA_MAX_RISE):
        return False

    base_top = max(highs[idx - _BASE_WEEKS : idx])
    # 2: the breakout itself — a weekly close above the top of the base.
    if base_top <= 0 or close <= base_top:
        return False
    # 1: that range really was a base, not a leg of a trend.
    if not _base_is_tight(highs, lows, idx):
        return False

    # 6: at least twice the prior ten weeks' average volume. A zero baseline
    #    (a suspended stock with no trading behind it) fails closed rather than
    #    making the test vacuous — the lesson of the VSA 2 halted-stock audit.
    base_vol = _mean(volumes, idx - _VOL_WEEKS, idx)
    if base_vol <= 0:
        return False
    return volumes[idx] >= base_vol * _VOL_MULT


def _posture_rules(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    last_idx: int,
    anchor: int,
    fresh: bool,
) -> int:
    """Count the Stage 1->2 posture rules satisfied (0.._TOTAL_RULES).

    Three rules describe the **base** and are measured at ``anchor``; three
    describe **where the stock stands now** and are measured at ``last_idx``.

    ``anchor`` is the week the breakout fired on when that was recent, and the
    latest completed week otherwise. Anchoring matters: once a stock breaks out,
    the twenty weeks behind it include the breakout run, so measuring the base
    at the latest week would report "no base" precisely when the setup has just
    triggered — scoring the method lowest at the moment it fires.
    """
    pair = _ma_pair(closes, anchor)
    ma_anchor, ma_prev = pair if pair else (None, None)
    ma_now = _sma(closes, _MA_WEEKS, last_idx)
    base_top = (
        max(highs[anchor - _BASE_WEEKS : anchor]) if anchor >= _BASE_WEEKS else 0.0
    )
    close = closes[last_idx]

    checks = (
        # 1 a tight Stage 1 base
        _base_is_tight(highs, lows, anchor),
        # 2 the 30-week MA has stopped falling
        ma_anchor is not None and ma_prev is not None and ma_anchor >= ma_prev,
        # 3 ...and is not already in a mature advance
        ma_anchor is not None
        and ma_prev is not None
        and ma_anchor <= ma_prev * (1.0 + _MA_MAX_RISE),
        # 4 price is above the 30-week MA (below it is Weinstein's sell)
        ma_now is not None and close > ma_now,
        # 5 still in the buy zone rather than extended past it
        base_top > 0 and close <= base_top * (1.0 + _MAX_EXTENSION),
        # 6 a fresh breakout
        fresh,
    )
    return sum(1 for ok in checks if ok)


@register_method
class WeinsteinStageBreakout(TradingMethod):
    id = "weinstein"
    order = 70
    name = "Weinstein Stage 2"
    description = (
        "Stan Weinstein's stage analysis, read on the weekly chart: after a "
        "decline a stock goes sideways for months while its 30-week moving "
        "average flattens (Stage 1), then breaks out of that base and advances "
        "(Stage 2). The setup fires on the week that closes above the top of "
        "the base and above the 30-week average, on at least twice the prior "
        "ten weeks' volume — and only while that average is still flat, so it "
        "catches the transition rather than a stock already well into its run. "
        "The score is how much of that picture is in place now. Long-only. "
        "(Bulkowski's 440 trades put breakout-stage buys at +13.2% and 69% "
        "winners versus +4.1% and 57% for late Stage-2 buys; the method still "
        "needs a GPW back-test before it should guide real money.)"
    )
    source = (
        "Stan Weinstein — Secrets for Profiting in Bull and Bear Markets (1988); "
        "stage evidence: Thomas Bulkowski, 440 trades 1987-2010"
    )
    source_url = "https://thepatternsite.com/Stages.html"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
        *,
        rs_rank: float | None = None,  # cross-sectional; not used by this method
    ) -> MethodResult:
        if not bars:
            return MethodResult.unavailable("Not enough history")

        weekly = _completed_weeks(bars)
        if len(weekly) < _MIN_WEEKS:
            return MethodResult.unavailable("Not enough history")

        closes = [float(q.close) for q in weekly]
        highs = [float(q.high) for q in weekly]
        lows = [float(q.low) for q in weekly]
        volumes = [float(q.volume) for q in weekly]
        last_idx = len(weekly) - 1
        # The age is measured from the newest DAILY bar, so mid-week the read
        # correctly says "broke out 3 days ago" rather than "today".
        last_date = max(b.date for b in bars)

        # The newest week a breakout STARTED on — the week ``signals`` marks. A
        # run can print two breakout weeks in a row (~10% of breakout weeks on
        # GPW history); the second is the same move, so it is neither "fired"
        # nor a fresh date here, just as it carries no marker on the chart.
        days_since = NEVER_FIRED
        fired_idx: int | None = None
        floor = max(_MIN_WEEKS - 1, last_idx - _RECENCY_SCAN_WEEKS)
        for i in range(last_idx, floor - 1, -1):
            if _breakout_fired(closes, highs, lows, volumes, i) and not _breakout_fired(
                closes, highs, lows, volumes, i - 1
            ):
                days_since = (last_date - weekly[i].date).days
                fired_idx = i
                break

        fresh = days_since <= _RECENT_WEEKS * 7
        anchor = fired_idx if fired_idx is not None and fresh else last_idx
        passed = _posture_rules(closes, highs, lows, last_idx, anchor, fresh)
        score = round(passed / _TOTAL_RULES * 100)
        fired = days_since == 0

        if fired:
            base_vol = _mean(volumes, last_idx - _VOL_WEEKS, last_idx)
            mult = volumes[last_idx] / base_vol if base_vol > 0 else 0.0
            detail = f"Stage 2 breakout x{mult:.1f} vol"
        elif days_since != NEVER_FIRED:
            detail = f"Broke out {days_since}d ago, {passed}/{_TOTAL_RULES}"
        else:
            ma_now = _sma(closes, _MA_WEEKS, last_idx)
            below = ma_now is not None and closes[last_idx] <= ma_now
            where = "below 30w MA" if below else "setup"
            detail = f"{passed}/{_TOTAL_RULES} {where}"

        return MethodResult(
            score=score,
            days_since=days_since,
            fired=fired,
            detail=detail,
            available=True,
        )

    def signals(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> list[MethodSignal]:
        """A marker on the week each Stage 1->2 breakout *turns on* (oldest first).

        Markers are dated to the breakout week's last trading session — a real
        daily bar — so they land on the daily chart and the back-test can index
        them like any other signal. A run can print two breakout weeks in a row
        (the second clears a base that now contains the first); marking only
        where a breakout turns on keeps one marker per move, as the Volume
        Breakout and Minervini overlays do.
        """
        weekly = _completed_weeks(bars)
        if len(weekly) < _MIN_WEEKS:
            return []

        closes = [float(q.close) for q in weekly]
        highs = [float(q.high) for q in weekly]
        lows = [float(q.low) for q in weekly]
        volumes = [float(q.volume) for q in weekly]

        out: list[MethodSignal] = []
        prev = False
        for i in range(_MIN_WEEKS - 1, len(weekly)):
            fired = _breakout_fired(closes, highs, lows, volumes, i)
            if fired and not prev:
                out.append(
                    MethodSignal(
                        date=weekly[i].date, label="Stage 2 breakout", type="Bullish"
                    )
                )
            prev = fired
        return out
