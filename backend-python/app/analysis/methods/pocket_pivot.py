"""Pocket Pivot — a volume-based, medium-term, long-only buy INSIDE the base.

Source: Gil Morales & Chris Kacher, *Trade Like an O'Neil Disciple* (Wiley,
2010), chapter 4, and *In the Trading Cockpit with the O'Neil Disciples*
(2012); Kacher's "Ten Rules for Trading Pocket Pivots" (virtueofselfish
investing.com). Both authors ran money at William O'Neil + Co. The pocket
pivot dates from the mid-2000s: a reprinted interview with Kacher puts it in
2005, when choppy markets kept failing ordinary new-high breakouts — though in
a paragraph not clearly marked as his own words.

The idea in one line: **a day whose buying volume is bigger than any selling
day's volume of the last two weeks, while the stock sits quietly on its moving
average** — the footprint of an institution accumulating *before* the stock
breaks out, which lets the buyer get in lower than the breakout buyer does.
The book calls it "an early base breakout indicator, which is designed to find
buyable pivot points within a stock's base" (p. 128).

That makes it a different question from every other method in the app. The
Volume Breakout and Weinstein methods buy the breakout *above* the base, on
volume measured against an average; the pocket pivot buys *inside* it, and its
volume test is a comparison of demand with supply — up-day volume against the
heaviest down-day volume — which is VSA's own way of reading a bar.

A pocket pivot **fires** on a bar when all six hold:

    1. It is an **up day** (close above the prior close) — the "up-volume" the
       rule is about.
    2. Its volume is **at least the largest down-day volume of the prior ten
       sessions** — the book, p. 133: "up-volume equal to or greater than the
       largest down-volume day over the prior 10 days". A window with no down
       day, or only zero-volume ones, has nothing to beat and fails closed.
    3. It closes **above the 50-day and the 200-day moving averages** — p. 133,
       "pocket pivots should only be bought when they occur above the 50-day
       moving average", and Kacher's rule 7, "do not buy pocket pivots if the
       stock is under a critical moving average such as the 50-dma or
       200-dma". (His "very rare" exception, a stock well under its 50-day
       finding support at the 200-day, is not taken.)
    4. It comes **up off or up through the 10-day or the 50-day line** — the
       day's low is at, under, or within 2% of that moving average and the
       close is above it. Kacher's rule 10: "If the pivot occurs right near
       its 10-dma, it can be bought, otherwise it is extended and should be
       avoided." *The 2% is this app's reading of "right near"; the authors
       give no number.*
    5. **Volume was quiet going in** — the five sessions before it averaged
       less than the prior fifty (p. 133: volume should turn "quiet over the
       previous several days"). *Five for "several" is this app's reading.*
    6. It does **not follow a wedge** — Kacher's rule 9, "avoid buying pocket
       pivots that occur after wedging patterns", i.e. a stock that has been
       "wedging" upward instead of drifting down into the pivot. Read here as
       the five sessions before it making a higher low on at least four of
       five days *and* closing higher overall. *The count is this app's
       reading; the authors define the wedge only by picture.*

Rules 5 and 6 together are the book's picture of the pivot: a quiet pull-back
or pause on the moving average, then one day of demand heavier than any recent
supply. A hard sell-off that "shoots straight back up in a V" (Kacher's rule
8, which the authors call failure-prone) is refused by rule 5, because a hard
sell-off does not happen on quiet volume. Kacher's rule 6 — no pocket pivot in
a "multi-month downtrend (5 months or longer)" — is only approximated, by rule
3's 200-day line: a stock above its 200-day line is rarely in such a
downtrend, but the rule does not check for one, and a sharp bounce above a
200-day line that is still falling passes it.

**What is not encoded.** The authors also ask for leading fundamentals (their
rule 2 — this app ranks every listed company, so it is left to the reader)
and a "constructive" base, which they describe by picture only; rules 3-6 are
the mechanical part of that picture.

**Evidence — read this before trusting it.** The authors' headline record
(Kacher's personal account, +18,241% in 1996-2002, which Kacher reports was
verified by KPMG) *predates* the pocket pivot, so it is not evidence for this
rule. Kacher himself says
"about half of high quality stocks showing pocket pivots ... won't work", about
the same as base breakouts, and no independent test of the rule was found. It
is a well-specified practitioner method from documented money managers, not a
proven edge: it has to earn trust on this app's own measurements.

``fired`` means a pocket pivot starts on the latest bar — the bar the chart
marks; ``days_since`` counts calendar days since the most recent such start in
the last 60 sessions. A second pivot day in a row belongs to the same move and
carries no marker, so it reads as "1d ago", not as a new firing. The
``score`` (0-100) reads the *posture* now
— above both averages, sitting at a buy line, quiet volume, no wedge, a fresh
pivot — so a stock settling quietly onto its 10-day line scores well before
the volume arrives. Under its 200-day line the score is capped at 50, because
the authors buy no pocket pivot there, so the method never leans bullish in
the analytics summary on such a stock. Long-only.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import accumulate
from math import isfinite, lcm

from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    register_method,
)
from app.analysis.vsa import VsaConfig
from app.models import StooqDailyQuote

# Rule 2: the window whose heaviest DOWN day the pivot's volume must match —
# "the largest down-volume day over the prior 10 days" (book, p. 133).
_DOWN_WINDOW = 10
# The moving averages the authors read the pivot against.
_SMA_FAST = 10
_SMA_MID = 50
_SMA_SLOW = 200
# Rule 4: how close to a moving average the day's low must come to count as
# "right near" it — this app's reading, the authors give no number.
_MA_TOUCH = 0.02
# Rule 5: "quiet over the previous several days" — the five sessions before the
# pivot against the fifty before it (this app's reading of "several").
_QUIET_DAYS = 5
_QUIET_BASELINE = 50
# Rule 6: a wedge is the five sessions before the pivot making a higher low on
# at least four of them while the close rises (this app's reading).
_WEDGE_DAYS = 5
_WEDGE_MIN_RISING = 4
# Posture: a pivot this many calendar days ago still counts as "fresh".
_RECENT_FIRED = 10
# How far back (sessions) to scan for the most recent pivot for days_since.
_RECENCY_SCAN = 60
# Posture-checklist size the score is scaled against.
_TOTAL_RULES = 6
# Minimum bars: the 200-day moving average on the bar being judged. Every
# other window (50-session baseline, ten-day down window) fits inside it.
_MIN_BARS = _SMA_SLOW


class _Series:
    """One stock's OHLCV as float lists, plus running sums for O(1) averages.

    The back-test and the chart overlay judge every bar of several years of
    history; recomputing a 200-bar average per bar would make that quadratic.

    Whether a close is *above* its average is decided exactly, in integers
    (``closes_above``), never by comparing it with the float ``sma``. A float
    running sum drifts: on a stock whose price has not moved at all — a
    suspended stock printing 12.35 day after day — the 50-day ``sma`` comes
    out as 12.349999999999909, a hair under the price, so a strict
    ``close > sma`` read a frozen stock as trading above its averages. A
    tolerance cannot fix that: measured on 2026-09-27 over every stored GPW
    bar, the drift reaches 6.8e-8 of the average (a stock whose adjusted early
    prices were huge), while real gaps between a close and its average go as
    small as 7.6e-9 — the two overlap.
    """

    __slots__ = ("close", "low", "volume", "_csum", "_vsum", "_cexact", "_cexact_sum")

    def __init__(self, bars: Sequence[StooqDailyQuote]) -> None:
        self.close = [float(q.close) for q in bars]
        self.low = [float(q.low) for q in bars]
        self.volume = [float(q.volume) for q in bars]
        self._csum = [0.0, *accumulate(self.close)]
        self._vsum = [0.0, *accumulate(self.volume)]
        # The closes again, exactly: each price as a whole number on one
        # common scale (stored prices have four decimals, so 1/10,000), with
        # integer running sums — still O(1) per average. A NaN or infinite
        # close has no such ratio: callers check ``_finite_closes`` first.
        ratios = [q.close.as_integer_ratio() for q in bars]
        scale = lcm(*{den for _, den in ratios})
        self._cexact = [num * (scale // den) for num, den in ratios]
        self._cexact_sum = [0, *accumulate(self._cexact)]

    def sma(self, length: int, idx: int) -> float | None:
        """Moving average of the ``length`` closes ending at ``idx`` (inclusive).

        A float, good for measuring distance from the line (rule 4's 2%); to
        ask whether a close is above it, use ``closes_above``.
        """
        start = idx - length + 1
        if start < 0 or idx >= len(self.close):
            return None
        return (self._csum[idx + 1] - self._csum[start]) / length

    def closes_above(self, length: int, idx: int) -> bool:
        """Does bar ``idx`` close above its ``length``-bar moving average? Exact.

        ``length`` x the close against the window's sum, both in integers, so
        a close level with its average (a frozen price) is never read as above
        it. False when there are fewer than ``length`` bars.
        """
        start = idx - length + 1
        if start < 0 or idx >= len(self._cexact):
            return False
        window = self._cexact_sum[idx + 1] - self._cexact_sum[start]
        return self._cexact[idx] * length > window

    def mean_volume(self, start: int, end: int) -> float:
        """Mean volume of bars ``start`` .. ``end - 1`` (0.0 when empty)."""
        if start < 0 or end <= start:
            return 0.0
        return (self._vsum[end] - self._vsum[start]) / (end - start)


def _finite_closes(bars: Sequence[StooqDailyQuote]) -> bool:
    """Is every close a finite number — can ``_Series`` be built at all?

    Its exact sums need each close's integer ratio, and a NaN or an infinite
    price has none (``as_integer_ratio`` raises where the old float sums
    carried the NaN along). Validation refuses such a price, but a bar built
    without it can still hold one, and a method must never raise on malformed
    input — so the caller answers "unavailable", or no markers, instead.
    """
    return all(isfinite(float(q.close)) for q in bars)


def _largest_down_volume(s: _Series, idx: int) -> float:
    """The heaviest down-day volume among the ``_DOWN_WINDOW`` bars before ``idx``.

    A down day is a close below the prior close. 0.0 when the window holds no
    down day (or only zero-volume ones) — there is then no supply to beat.
    """
    best = 0.0
    for j in range(max(1, idx - _DOWN_WINDOW), idx):
        if s.close[j] < s.close[j - 1] and s.volume[j] > best:
            best = s.volume[j]
    return best


def _line_touched(s: _Series, idx: int) -> int | None:
    """The moving average (10 or 50) bar ``idx`` comes up off or through, or None.

    Rule 4: the day's low is at, below or within ``_MA_TOUCH`` of the line, and
    the close is above it (decided exactly — see ``_Series``). The 10-day line
    is preferred when both qualify — it is the authors' main case (a
    "continuation" pocket pivot).
    """
    low = s.low[idx]
    for length in (_SMA_FAST, _SMA_MID):
        ma = s.sma(length, idx)
        if (
            ma is not None
            and ma > 0
            and s.closes_above(length, idx)
            and low <= ma * (1.0 + _MA_TOUCH)
        ):
            return length
    return None


def _quiet_into(s: _Series, idx: int) -> bool:
    """Rule 5: the sessions before ``idx`` traded under the prior baseline."""
    if idx < _QUIET_DAYS + _QUIET_BASELINE:
        return False
    recent = s.mean_volume(idx - _QUIET_DAYS, idx)
    baseline = s.mean_volume(idx - _QUIET_DAYS - _QUIET_BASELINE, idx - _QUIET_DAYS)
    return baseline > 0 and recent < baseline


def _wedging_into(s: _Series, idx: int) -> bool:
    """Rule 6: did the sessions before ``idx`` wedge upward rather than drift down?"""
    if idx < _WEDGE_DAYS + 1:
        return False
    first = idx - _WEDGE_DAYS  # the first of the sessions before the pivot
    rising = sum(1 for k in range(first, idx) if s.low[k] > s.low[k - 1])
    return rising >= _WEDGE_MIN_RISING and s.close[idx - 1] > s.close[first - 1]


def _above_trend(s: _Series, idx: int) -> tuple[bool, bool]:
    """(close above the 50-day MA, close above the 200-day MA) on bar ``idx``.

    Decided exactly (see ``_Series``): a frozen price is level with its
    averages, not above them.
    """
    return s.closes_above(_SMA_MID, idx), s.closes_above(_SMA_SLOW, idx)


def _pivot_line(s: _Series, idx: int) -> int | None:
    """If a pocket pivot fires on bar ``idx``, the line it came off (10/50), else None.

    The six rules of the module docstring, cheapest first so the common "no
    pivot" bar costs almost nothing.
    """
    if idx < _MIN_BARS - 1 or idx >= len(s.close):
        return None
    # 1: an up day.
    if s.close[idx] <= s.close[idx - 1]:
        return None
    # 2: demand heavier than any supply of the last ten sessions. Fails closed
    #    when there is no down-day volume to beat (the lesson of the VSA 2
    #    halted-stock audit: a vacuous test must not pass).
    top_down = _largest_down_volume(s, idx)
    if top_down <= 0 or s.volume[idx] < top_down:
        return None
    # 3: above the 50-day and the 200-day moving averages.
    above50, above200 = _above_trend(s, idx)
    if not (above50 and above200):
        return None
    # 4: up off or up through the 10-day or 50-day line, not extended from it.
    line = _line_touched(s, idx)
    if line is None:
        return None
    # 5: volume was quiet going in; 6: and the stock drifted, it did not wedge.
    if not _quiet_into(s, idx) or _wedging_into(s, idx):
        return None
    return line


def _posture_rules(s: _Series, idx: int, fresh: bool) -> int:
    """Count the pocket-pivot posture rules satisfied on bar ``idx`` (0.._TOTAL_RULES).

    The quiet-volume and wedge checks look at the sessions *before* ``idx`` —
    the same windows the firing rules use — so a pivot on the latest bar is
    not marked down for its own volume.
    """
    above50, above200 = _above_trend(s, idx)
    checks = (
        above50,                           # 1 above the 50-day line
        above200,                          # 2 above the 200-day line
        _line_touched(s, idx) is not None,  # 3 at a buy line, not extended
        _quiet_into(s, idx),               # 4 quiet volume going in
        not _wedging_into(s, idx),         # 5 no wedge into it
        fresh,                             # 6 a fresh pocket pivot
    )
    return sum(1 for ok in checks if ok)


@register_method
class PocketPivot(TradingMethod):
    id = "pocket_pivot"
    order = 80
    name = "Pocket Pivot"
    description = (
        "Gil Morales and Chris Kacher's pocket pivot, an early buy inside the "
        "base instead of at the breakout: an up day whose volume is at least "
        "the heaviest selling day's volume of the previous ten sessions, while "
        "the stock sits above its 50- and 200-day averages and comes up off or "
        "through its 10- or 50-day line, after a few quiet days that did not "
        "wedge upward. The score is how much of that picture is in place now. "
        "Long-only. (The authors' audited record predates this rule and Kacher "
        "says about half of pocket pivots fail; it has no independent test and "
        "should prove itself on this app's measurements before it guides real "
        "money.)"
    )
    source = (
        "Gil Morales & Chris Kacher — Trade Like an O'Neil Disciple (2010), "
        "ch. 4; Kacher's Ten Rules for Trading Pocket Pivots"
    )
    source_url = "https://www.virtueofselfishinvesting.com/"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
        *,
        rs_rank: float | None = None,  # cross-sectional; not used by this method
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")
        if not _finite_closes(bars):
            return MethodResult.unavailable("Invalid price data")

        s = _Series(bars)
        last_idx = len(bars) - 1
        last_date = bars[last_idx].date

        # Recency counts only the bars the chart marks: a pivot that *starts*
        # there, the bar before it not being one (as in ``signals``, a bar
        # before the first one judged counts as none). The second day of a run
        # of pivot days is the same move, so it reads as the first day's age,
        # and "fired" always means a marker on the latest bar.
        days_since = NEVER_FIRED
        floor = max(_MIN_BARS - 1, last_idx - _RECENCY_SCAN)
        pivot_here = _pivot_line(s, last_idx) is not None
        for i in range(last_idx, floor - 1, -1):
            pivot_before = _pivot_line(s, i - 1) is not None
            if pivot_here and not pivot_before:
                days_since = (last_date - bars[i].date).days
                break
            pivot_here = pivot_before

        fresh = days_since <= _RECENT_FIRED
        passed = _posture_rules(s, last_idx, fresh)
        score = round(passed / _TOTAL_RULES * 100)
        _, above200 = _above_trend(s, last_idx)
        if not above200:
            # Kacher's rule 7: no pocket pivot is bought under the 200-day line,
            # so however much else is in place the method stays neutral there
            # (the analytics summary reads anything above 50 as a bullish lean).
            score = min(score, 50)
        fired = days_since == 0

        if fired:
            top_down = _largest_down_volume(s, last_idx)
            mult = s.volume[last_idx] / top_down if top_down > 0 else 0.0
            detail = f"Pocket pivot x{mult:.1f} down-vol"
        elif days_since != NEVER_FIRED:
            detail = f"Pocket pivot {days_since}d ago, {passed}/{_TOTAL_RULES}"
            if not above200:
                # Say why the score is capped at 50 now. (The analytics
                # summary shows only the part before the first ", ".)
                detail += " below 200d MA"
        else:
            where = "setup" if above200 else "below 200d MA"
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
        """A marker on each bar a pocket pivot *turns on* (oldest first).

        The label names the line it came off — "10d" (the authors' continuation
        pivot off the 10-day line) or "50d" (one off the 50-day, typically out
        of a deeper base). Two pivot days in a row are one move and get one
        marker, as the other methods' overlays do; ``evaluate`` counts its
        recency from the same bars, so "fired" means a marker on the last bar.
        """
        if len(bars) < _MIN_BARS or not _finite_closes(bars):
            return []

        s = _Series(bars)
        out: list[MethodSignal] = []
        prev = False
        for i in range(_MIN_BARS - 1, len(bars)):
            line = _pivot_line(s, i)
            if line is not None and not prev:
                out.append(
                    MethodSignal(
                        date=bars[i].date, label=f"Pocket Pivot {line}d", type="Bullish"
                    )
                )
            prev = line is not None
        return out
