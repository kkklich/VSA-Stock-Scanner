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

The ``score`` is *how many of the rules the stock currently satisfies*, scaled
to 0–100 (all of them = a full trend-template match); a "recent example" means
the structural rules lined up on a recent bar. The setup is long-only.

Rule 8 — Minervini's IBD-style **relative-strength rank ≥ 70 versus the
universe** — is cross-sectional (it compares a stock to every other), so it is
supplied by the caller as ``rs_rank`` (a 0–100 percentile). The ranking service
computes it across the scanned universe and passes it in, making the score out
of 8; a standalone evaluation with no universe (the single-stock page, tests,
the back-test) receives no ``rs_rank`` and falls back to the 7 structural rules,
saying so in ``detail``. Because RS rank is only known for the latest session,
it folds into the score, while ``fired``/recency track the structural template.

KNOWN SCOPE: this is still a framework example, not yet a back-test-gated,
shippable scanner — the roadmap requires proving each method on stored GPW
history before it ranks money.
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

# Total structural rules scored (rules 1-7). Minervini's 8th rule — an
# IBD-style relative-strength rank vs. the market — is cross-sectional and is
# applied only in the ranking path (see ``evaluate``'s ``rs_rank`` parameter),
# where the whole universe is known; it is NOT one of these structural rules.
_TOTAL_RULES = 7
# Minervini's rule 8: relative-strength rank (0-100 percentile) at least this.
_RS_RANK_MIN = 70.0
# Minimum bars to evaluate at all. Rules 6-7 need a genuine 52-week window
# (``_WEEK52``), which is the binding constraint (it exceeds the 200-day MA +
# trend lookback the earlier rules need). Below this the stock is too newly
# listed / too thinly stored to judge, and the method reports "unavailable".
# A stock with 220-251 bars — enough for the moving averages but not a real
# year — is therefore (correctly) unavailable rather than judged on a short
# window; the standard ~260-session production fetch clears this comfortably.
_MIN_BARS = _WEEK52  # 252
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

    # Rules 6-7 compare price to the 52-week high/low, so they need a genuine
    # 52-week window. Do NOT clamp a short window to the start of the series:
    # in production only ~260 sessions are stored, so validating rules 6-7
    # against a sub-52-week window would report a three-month high as a fresh
    # 52-week high (the same falsehood the ranking's 52-week context guards
    # against). When there aren't ``_WEEK52`` prior bars, the bar is not
    # judgeable — return None so the recency scan and ``signals()`` skip it and
    # ``evaluate`` reports "unavailable".
    window_start = idx - _WEEK52 + 1
    if window_start < 0:
        return None
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
        "high, plus (in the ranking) a relative-strength rank in the top 30% of "
        "the market. The score is how many of the rules line up (a full match "
        "when all do); a recent example means the structural template lined up "
        "on a recent session. Long-only. (The method still needs a GPW back-test "
        "before it should guide real money.)"
    )
    source = "Mark Minervini — Trade Like a Stock Market Wizard (2013)"
    source_url = "https://www.minervini.com/"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
        *,
        rs_rank: float | None = None,
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")

        closes = [float(q.close) for q in bars]
        highs = [float(q.high) for q in bars]
        lows = [float(q.low) for q in bars]
        last_idx = len(bars) - 1

        structural = _rules_passed(closes, highs, lows, last_idx)
        if structural is None:
            return MethodResult.unavailable("Not enough history")

        # Rule 8 — the cross-sectional relative-strength rank (>= 70 percentile
        # vs. the scanned universe). It is only knowable for the latest session
        # (RS rank is not stored per historical bar), so it folds into the SCORE
        # and detail; the ``fired``/``days_since`` marker tracks the *structural*
        # template (the chartable entry the ``signals()`` overlay draws), which
        # keeps the ``fired == (days_since == 0)`` contract intact. When no
        # ``rs_rank`` is supplied (single-stock page, tests, back-test), the
        # method falls back to the 7 structural rules and says so in ``detail``.
        if rs_rank is not None:
            passed = structural + (1 if rs_rank >= _RS_RANK_MIN else 0)
            total = _TOTAL_RULES + 1  # 8: the full canonical template
            detail = f"{passed}/{total} rules"
        else:
            passed = structural
            total = _TOTAL_RULES
            detail = f"{passed}/{total} structural"
        score = round(passed / total * 100)

        # Recency: the most recent bar on which all seven structural rules held.
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
            fired=structural == _TOTAL_RULES,
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
        # Seed the prior state from the FIRST evaluable bar without emitting it,
        # then only emit genuine off->on transitions. Otherwise a template that
        # is already ON at the left edge of the window (its true entry lies
        # before the data we hold) would be mis-reported as a fresh entry here.
        first = _MIN_BARS - 1
        prev_full = _rules_passed(closes, highs, lows, first) == _TOTAL_RULES
        for i in range(_MIN_BARS, len(bars)):
            full = _rules_passed(closes, highs, lows, i) == _TOTAL_RULES
            if full and not prev_full:
                out.append(
                    MethodSignal(
                        date=bars[i].date, label="Trend Template", type="Bullish"
                    )
                )
            prev_full = full
        return out
