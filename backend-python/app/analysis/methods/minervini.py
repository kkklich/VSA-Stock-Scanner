"""Minervini Trend Template — the first concrete example method.

Source: Mark Minervini, *Trade Like a Stock Market Wizard* (2013). Minervini is
a two-time U.S. Investing Champion — a real, independently verifiable
competition record — which is exactly the evidence standard the vetting
playbook (``agent/TRADING-METHODS-RESEARCH.md``) requires.

The "Trend Template" is Minervini's mechanical filter for a stock in a
confirmed Stage-2 uptrend. It reduces cleanly to end-of-day price + moving
averages, so it fits the data we already store. This implementation covers the
**price / moving-average structure (rules 1–7)**:

    1. Price is above both the 150-day and the 200-day moving average.
    2. The 150-day MA is above the 200-day MA.
    3. The 200-day MA is trending up (higher than it was ~1 month ago).
    4. The 50-day MA is above both the 150-day and the 200-day MA.
    5. Price is above the 50-day MA.
    6. Price is at least 30% above its 52-week low.
    7. Price is within 25% of its 52-week high.

The ``score`` is *how many of the seven rules the stock currently satisfies*,
scaled to 0–100 (all seven = a full trend-template match); a "recent example"
means every rule lined up on a recent bar. The setup is long-only.

KNOWN SCOPE: Minervini's eighth rule — an IBD-style **relative-strength rank ≥
70 versus the market** — is cross-sectional (it compares a stock to the whole
universe) and needs a market/index series we do not yet store, so it is a
planned follow-up (see ``agent/ROADMAP.md`` 23a). This is a faithful example of
the framework, not yet a back-test-gated, shippable scanner: the roadmap
requires proving each method on stored GPW history before it ranks money.
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

# Moving-average lengths (trading sessions), per the trend template.
_SMA_SHORT = 50
_SMA_MID = 150
_SMA_LONG = 200
# "Trending up" = the 200-day MA is higher than it was this many sessions ago
# (Minervini asks for the 200-day MA rising for at least a month; ~20 sessions).
_TREND_LOOKBACK = 20
# 52-week window in trading sessions (~252) for the high/low bounds.
_WEEK52 = 252
# Rule 6: price at least 30% above the 52-week low.
_MIN_ABOVE_LOW = 0.30
# Rule 7: price within 25% of the 52-week high (>= 75% of the high).
_MAX_BELOW_HIGH = 0.25

# Total structural rules scored.
_TOTAL_RULES = 7
# Minimum bars to evaluate at all: a 200-day MA plus enough room to also read it
# ``_TREND_LOOKBACK`` sessions back (rule 3). Below this the stock is too newly
# listed / too thinly stored to judge, and the method reports "unavailable".
_MIN_BARS = _SMA_LONG + _TREND_LOOKBACK  # 220
# How far back to look for the most recent full-template bar (recency).
_RECENCY_SCAN = 90


def _sma(closes: Sequence[float], length: int, end_idx: int) -> float | None:
    """Simple moving average of ``closes`` over ``length`` bars ending at ``end_idx``.

    Returns ``None`` when there are not enough bars before ``end_idx``.
    """
    start = end_idx - length + 1
    if start < 0:
        return None
    window = closes[start : end_idx + 1]
    return sum(window) / length


def _rules_passed(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    idx: int,
) -> int | None:
    """Count how many of the 7 trend-template rules hold as of bar ``idx``.

    Returns ``None`` when bar ``idx`` does not have enough prior history to
    compute the required moving averages.
    """
    price = closes[idx]
    sma50 = _sma(closes, _SMA_SHORT, idx)
    sma150 = _sma(closes, _SMA_MID, idx)
    sma200 = _sma(closes, _SMA_LONG, idx)
    sma200_prev = _sma(closes, _SMA_LONG, idx - _TREND_LOOKBACK)
    if None in (sma50, sma150, sma200, sma200_prev):
        return None

    window_start = max(0, idx - _WEEK52 + 1)
    high_52w = max(highs[window_start : idx + 1])
    low_52w = min(lows[window_start : idx + 1])
    if low_52w <= 0 or high_52w <= 0:
        return None

    checks = (
        price > sma150 and price > sma200,          # 1
        sma150 > sma200,                             # 2
        sma200 > sma200_prev,                        # 3
        sma50 > sma150 and sma50 > sma200,           # 4
        price > sma50,                               # 5
        price >= low_52w * (1.0 + _MIN_ABOVE_LOW),   # 6
        price >= high_52w * (1.0 - _MAX_BELOW_HIGH),  # 7
    )
    return sum(1 for ok in checks if ok)


@register_method
class MinerviniTrendTemplate(TradingMethod):
    id = "minervini"
    order = 20
    name = "Minervini Trend Template"
    description = (
        "Mark Minervini's mechanical filter for a stock in a confirmed Stage-2 "
        "uptrend: price above rising 50/150/200-day moving averages stacked in "
        "the right order, well off the 52-week low and close to the 52-week "
        "high. The score is how many of the seven structural rules line up "
        "(all seven = a full trend-template match); a recent example means they "
        "all lined up on a recent session. Long-only. (Relative-strength rank "
        "vs. the market — Minervini's 8th rule — is a planned addition, and the "
        "method still needs a GPW back-test before it should guide real money.)"
    )
    source = "Mark Minervini — Trade Like a Stock Market Wizard (2013)"
    source_url = "https://www.minervini.com/"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")

        closes = [float(q.close) for q in bars]
        highs = [float(q.high) for q in bars]
        lows = [float(q.low) for q in bars]
        last_idx = len(bars) - 1

        passed = _rules_passed(closes, highs, lows, last_idx)
        if passed is None:
            return MethodResult.unavailable("Not enough history")

        score = round(passed / _TOTAL_RULES * 100)
        detail = f"{passed}/{_TOTAL_RULES} rules"

        # Recency: the most recent bar on which all seven rules held.
        days_since = NEVER_FIRED
        last_date = bars[last_idx].date
        floor = max(_MIN_BARS - 1, last_idx - _RECENCY_SCAN)
        for i in range(last_idx, floor - 1, -1):
            if _rules_passed(closes, highs, lows, i) == _TOTAL_RULES:
                days_since = (last_date - bars[i].date).days
                break

        return MethodResult(
            score=score,
            days_since=days_since,
            fired=passed == _TOTAL_RULES,
            detail=detail,
            available=True,
        )

    def signals(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> list[MethodSignal]:
        """A marker on every bar where the full 7/7 trend template *turns on*.

        The template can stay satisfied for long stretches; marking every such
        bar would paint a solid band. Instead a marker is placed only where the
        stock *enters* a full-template state (the previous evaluable bar had
        fewer than seven rules), which reads as the entry trigger.
        """
        if len(bars) < _MIN_BARS:
            return []

        closes = [float(q.close) for q in bars]
        highs = [float(q.high) for q in bars]
        lows = [float(q.low) for q in bars]

        out: list[MethodSignal] = []
        prev_full = False
        for i in range(_MIN_BARS - 1, len(bars)):
            full = _rules_passed(closes, highs, lows, i) == _TOTAL_RULES
            if full and not prev_full:
                out.append(
                    MethodSignal(
                        date=bars[i].date, label="Trend Template", type="Bullish"
                    )
                )
            prev_full = full
        return out
