"""Volume-confirmed breakout — a volume-based, medium-term, long-only method.

Source: the classic base-breakout rule shared by William O'Neil (*How to Make
Money in Stocks*, the CANSLIM method / Investor's Business Daily) and Mark
Minervini (*Trade Like a Stock Market Wizard*, the VCP). Both buy the same event:
after a stock builds a quiet base — a sideways range where volume dries up —
price breaks out to a new multi-week high on a burst of volume well above its own
average, the footprint of institutions accumulating. It is the price/volume
expression of the VSA "Sign of Strength", so it sits naturally next to the app's
VSA engine, and it satisfies the owner's brief: volume-driven, held over
weeks-to-months, and long-only (it profits from the rise).

This reduces to end-of-day OHLCV, so it fits the data the app already stores. A
breakout **fires** on a bar when all of these hold:

    1. Close breaks above the highest high of the prior 50 sessions — a new
       ~10-week base high (the breakout itself).
    2. Volume is at least 1.5x the average of the prior 50 sessions — O'Neil's
       "40-50% above average" test for institutional demand.
    3. The close sits in the upper half of the bar's range — demand won the
       session, not a failed poke through resistance.
    4. It breaks out of a REAL base: volume dried up going into the pivot (a
       quiet, coiling base — measured on the bar before the breakout so its own
       volume spike can't defeat the test) and the prior ~50 sessions formed a
       tight consolidation (depth within O'Neil's ~12-33% base range), not a
       news gap or a stock already running vertically with no base underneath.

``fired`` is a breakout on the latest bar; ``days_since`` is how many calendar
days ago the most recent breakout fired. The ``score`` (0-100) is a softer read of how
good the breakout *posture* is right now — a five-part checklist (uptrend, the
50-day above the 150-day, price near its 52-week high, a coiling/volume-dry-up
base, and a fresh breakout) — so a stock tightening just under new highs scores
well even a few days before it triggers, while a stock deep in a downtrend scores
near zero (and so never leans bullish in the analytics summary). Long-only.

KNOWN SCOPE: like the Minervini template, this is a faithful example of the
framework, not yet a back-test-gated, shippable signal — the roadmap (item 23,
``agent/ROADMAP.md``) requires proving each method on stored GPW history before
it guides real money. The thresholds above are the literature's defaults, not
GPW-tuned ones.
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
from app.models import StooqDailyQuote

# Breakout window: close must clear the highest high of the prior 50 sessions
# (~10 trading weeks — a medium-term base).
_LOOKBACK = 50
# Volume baseline: the average of the prior 50 sessions the breakout must beat.
_BASELINE = 50
# Volume expansion multiple — O'Neil's "40-50% above average" institutional test.
_VOL_MULT = 1.5
# Moving-average lengths (trading sessions) used by the trend filters.
_SMA_SHORT = 50
_SMA_MID = 150
# 52-week window (~252 sessions) for the "near the high" posture rule.
_WEEK52 = 252
# Posture rule 3: price within 15% of the 52-week high (>= 85% of it).
_NEAR_HIGH = 0.15
# Volume-dry-up ("coiling base") test: the mean volume of the last _VDU_RECENT
# sessions is no higher than the mean of the _VDU_PRIOR sessions before them.
_VDU_RECENT = 10
_VDU_PRIOR = 40
# Base-tightness cap: the prior _LOOKBACK sessions must span less than this
# fraction (high→low) to count as a real consolidation rather than a vertical
# run. O'Neil's proper bases are ~12-33% deep; 35% leaves a little slack.
_BASE_MAX_DEPTH = 0.35
# Posture rule 5: a breakout this many calendar days ago still counts as "fresh".
_RECENT_FIRED = 10
# How far back to scan for the most recent breakout when reporting days_since.
_RECENCY_SCAN = 60
# Posture-checklist size the score is scaled against.
_TOTAL_RULES = 5
# Minimum bars to evaluate at all — enough for the 150-day MA used in the score.
# Below this the stock is too newly listed / too thinly stored to judge.
_MIN_BARS = _SMA_MID + 10  # 160


def _sma(closes: Sequence[float], length: int, end_idx: int) -> float | None:
    """Simple moving average over ``length`` bars ending at ``end_idx`` (or None)."""
    start = end_idx - length + 1
    if start < 0:
        return None
    return sum(closes[start : end_idx + 1]) / length


def _mean(values: Sequence[float], start: int, end: int) -> float:
    """Mean of ``values[start:end]`` (0.0 for an empty slice)."""
    seg = values[start:end]
    return sum(seg) / len(seg) if seg else 0.0


def _breakout_fired(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    idx: int,
) -> bool:
    """Whether a volume-confirmed breakout fires on bar ``idx``.

    Three conditions actually bind:

        1. Close breaks above the highest high of the prior 50 sessions — a new
           base high (the breakout itself).
        2. Volume is at least ``_VOL_MULT`` times the average of the prior 50
           sessions — O'Neil's "40-50% above average" institutional demand test.
        3. The close sits in the upper half of the bar's range — demand won the
           session, not a failed poke through resistance.

    Two conditions that used to be listed here — "it is an up day"
    (``close > closes[idx-1]``) and "close is above the 50-day MA"
    (``close > sma50``) — were *mathematically always true* whenever condition 1
    holds: the prior-50-session high is >= every one of those prior closes, and
    the 50-day MA is an average of 50 closes each below a close that itself
    exceeds that high. They added nothing and have been removed.
    """
    if idx < max(_LOOKBACK, _BASELINE, _SMA_SHORT):
        return False
    ceiling = max(highs[idx - _LOOKBACK : idx])  # prior base high (excl. today)
    base_vol = _mean(volumes, idx - _BASELINE, idx)
    if base_vol <= 0:
        return False

    close = closes[idx]
    rng = highs[idx] - lows[idx]
    # A zero-range (halted / limit-locked) bar has no meaningful close position,
    # so it must NOT count as a strong close.
    strong_close = (close - lows[idx]) / rng >= 0.5 if rng > 0 else False
    if not (
        close > ceiling                              # 1: new base high
        and volumes[idx] >= base_vol * _VOL_MULT     # 2: volume expansion
        and strong_close                             # 3: closes strong
    ):
        return False

    # 4: a real base under the pivot, not a news gap or a stock already running.
    #   * Volume dried up going INTO the pivot — measured on the bar BEFORE the
    #     breakout, so the breakout's own volume spike cannot defeat the test.
    if not _volume_dry_up(volumes, idx - 1):
        return False
    #   * The prior base is a tight consolidation, not a vertical run: its depth
    #     (high→low over the prior _LOOKBACK sessions) is within O'Neil's range.
    base_low = min(lows[idx - _LOOKBACK : idx])
    depth = (ceiling - base_low) / ceiling if ceiling > 0 else 1.0
    if depth > _BASE_MAX_DEPTH:
        return False
    return True


def _volume_dry_up(volumes: Sequence[float], idx: int) -> bool:
    """Whether volume has contracted into bar ``idx`` (a coiling base / VDU)."""
    if idx + 1 < _VDU_RECENT + _VDU_PRIOR:
        return False
    recent = _mean(volumes, idx - _VDU_RECENT + 1, idx + 1)
    prior = _mean(volumes, idx - _VDU_RECENT - _VDU_PRIOR + 1, idx - _VDU_RECENT + 1)
    return prior > 0 and recent <= prior


def _posture_rules(
    closes: Sequence[float],
    highs: Sequence[float],
    volumes: Sequence[float],
    idx: int,
    days_since: int,
) -> int:
    """Count the breakout-posture rules satisfied on bar ``idx`` (0.._TOTAL_RULES)."""
    sma50 = _sma(closes, _SMA_SHORT, idx)
    sma150 = _sma(closes, _SMA_MID, idx)
    win_start = max(0, idx - _WEEK52 + 1)
    high_52w = max(highs[win_start : idx + 1])
    close = closes[idx]

    checks = (
        sma50 is not None and close > sma50,                          # 1 uptrend
        sma50 is not None and sma150 is not None and sma50 > sma150,  # 2 structure
        high_52w > 0 and close >= high_52w * (1.0 - _NEAR_HIGH),      # 3 near high
        # 4 coiling base — evaluated on the bar BEFORE ``idx`` so that when
        # ``idx`` is itself the breakout, its volume spike does not defeat the
        # volume-dry-up test (which measures the quiet base leading in).
        _volume_dry_up(volumes, idx - 1),
        days_since <= _RECENT_FIRED,                                 # 5 fresh breakout
    )
    return sum(1 for ok in checks if ok)


@register_method
class VolumeBreakout(TradingMethod):
    id = "breakout"
    order = 30
    name = "Volume Breakout"
    description = (
        "A volume-confirmed breakout, the way William O'Neil (CANSLIM) and Mark "
        "Minervini (VCP) buy one: after a stock builds a quiet base where volume "
        "dries up, price breaks out to a new ~10-week high on volume at least "
        "50% above its own average — institutions stepping in — closing strong "
        "and above its 50-day average. The score rates the current breakout "
        "posture (uptrend, near the 52-week high, a tight/coiling base and a "
        "fresh breakout); a recent example means a genuine volume breakout fired "
        "in the last couple of weeks. Long-only. (Thresholds are the "
        "literature's defaults; the method still needs a GPW back-test before it "
        "should guide real money.)"
    )
    source = (
        "William O'Neil — How to Make Money in Stocks (CANSLIM); "
        "Mark Minervini — Trade Like a Stock Market Wizard (VCP)"
    )
    source_url = "https://www.investors.com/"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
        *,
        rs_rank: float | None = None,  # cross-sectional; not used by this method
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")

        closes = [float(q.close) for q in bars]
        highs = [float(q.high) for q in bars]
        lows = [float(q.low) for q in bars]
        volumes = [float(q.volume) for q in bars]
        last_idx = len(bars) - 1
        last_date = bars[last_idx].date

        # Recency: the most recent bar a breakout fired on. days_since == 0 (a
        # breakout on the last bar) is exactly ``fired``.
        days_since = NEVER_FIRED
        floor = max(_MIN_BARS - 1, last_idx - _RECENCY_SCAN)
        for i in range(last_idx, floor - 1, -1):
            if _breakout_fired(closes, highs, lows, volumes, i):
                days_since = (last_date - bars[i].date).days
                break

        passed = _posture_rules(closes, highs, volumes, last_idx, days_since)
        score = round(passed / _TOTAL_RULES * 100)
        fired = days_since == 0

        if fired:
            base_vol = _mean(volumes, last_idx - _BASELINE, last_idx)
            mult = volumes[last_idx] / base_vol if base_vol > 0 else 0.0
            detail = f"Breakout x{mult:.1f} vol"
        elif days_since != NEVER_FIRED:
            detail = f"Broke out {days_since}d ago"
        else:
            detail = f"{passed}/{_TOTAL_RULES} setup"

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
        """A marker on the first bar of each volume breakout (oldest first).

        A strong thrust can print several new-high, high-volume bars in a row;
        marking only where a breakout *turns on* (the prior bar was not itself a
        breakout) keeps one clean marker per move, matching how the Minervini
        overlay marks its entries.
        """
        if len(bars) < _MIN_BARS:
            return []

        closes = [float(q.close) for q in bars]
        highs = [float(q.high) for q in bars]
        lows = [float(q.low) for q in bars]
        volumes = [float(q.volume) for q in bars]

        out: list[MethodSignal] = []
        prev = False
        for i in range(_MIN_BARS - 1, len(bars)):
            fired = _breakout_fired(closes, highs, lows, volumes, i)
            if fired and not prev:
                out.append(
                    MethodSignal(
                        date=bars[i].date, label="Volume Breakout", type="Bullish"
                    )
                )
            prev = fired
        return out
