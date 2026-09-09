"""Detecting corporate actions (splits, dividends) in a stored price history.

Why this exists
---------------
Yahoo Finance serves *adjusted* prices: the moment a company splits its shares
or pays a dividend, Yahoo rewrites the stock's **entire** past history to the
new scale, so that today's price and a price from five years ago stay directly
comparable.

This app stores what Yahoo served **at the time it asked**, and the nightly
ingest only asks for the last few days. So a corporate action leaves the
database holding two different scales at once: the handful of bars fetched
after the action are on the new scale, everything older is still on the old one.

For a 1:10 split that is not a rounding difference — it is a stored history in
which the stock appears to have lost 90% of its value in a single session, on a
volume spike, without ever trading down. That is a textbook VSA "selling
climax" that never happened, and it would poison the rating, the signals, the
52-week range, the returns and the back-tests for as long as the bad bar stayed
inside the analysis window.

How it is detected
------------------
No corporate-action feed is needed. The evidence is already in hand: whenever
the ingest fetches a window that overlaps bars the database already has, the
two must agree bar for bar. If they do not — if the overlapping bars are off by
the same factor — the provider has restated the series, and the stored history
has to be re-fetched in full rather than topped up.

Only **prices** are compared, deliberately. Volume is restated by a split too,
but Yahoo also revises a session's volume slightly for a day or two after the
close (late-reported trades), and that ordinary revision is exactly what the
ingest's few-day re-fetch window already handles by overwriting those bars. A
volume difference alone is therefore not evidence of a corporate action, while
a price difference is.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

from app.models import StooqDailyQuote

# A stored bar and a freshly fetched one may differ by this much and still count
# as "the same bar". Prices are stored to 4 decimal places, so the real rounding
# noise is far below this; the threshold is set by what matters downstream
# instead. A 0.5% step in the middle of a price series is smaller than an
# ordinary day's range and changes no VSA reading, whereas every split (2:1 at
# the very least) and every dividend worth adjusting for is far larger.
DEFAULT_TOLERANCE = 0.005

# How many overlapping bars must disagree before the history is re-fetched.
#
# One is enough, on purpose. The two failure modes are not symmetric: a missed
# split leaves a permanently corrupted history that manufactures false signals,
# while an unnecessary re-fetch costs one HTTP request and rewrites the ticker's
# bars with the provider's current values — which is the right answer to "the
# provider no longer reports what we stored" whatever the cause turns out to be.
DEFAULT_MIN_MISMATCH = 1


@dataclass(frozen=True, slots=True)
class AdjustmentCheck:
    """The verdict on one ticker's stored history versus a fresh fetch.

    Attributes:
        adjusted:    True when the stored bars must be re-fetched in full.
        ratio:       Fetched price divided by stored price on the bars that
                     disagree (their median). ``0.25`` means the provider now
                     reports a quarter of what is stored — a 1:4 split.
                     ``None`` when nothing disagreed.
        compared:    How many bars the two series had in common.
        mismatched:  How many of those disagreed beyond the tolerance.
        consistent:  True when every disagreeing bar is off by the *same*
                     factor — the signature of a corporate action, as opposed
                     to a provider correcting individual figures.
        first_date:  Oldest disagreeing bar.
        last_date:   Newest disagreeing bar.
        reason:      Plain-language explanation, written into the log.
    """

    adjusted: bool
    ratio: float | None = None
    compared: int = 0
    mismatched: int = 0
    consistent: bool = True
    first_date: date | None = None
    last_date: date | None = None
    reason: str = "no overlapping bars to compare"


def detect_adjustment(
    stored: list[StooqDailyQuote],
    fetched: list[StooqDailyQuote],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    min_mismatch: int = DEFAULT_MIN_MISMATCH,
) -> AdjustmentCheck:
    """Compare a stored history against a fresh fetch covering the same dates.

    Args:
        stored:       Bars already in the database.
        fetched:      Bars just downloaded from the data provider.
        tolerance:    Relative difference below which two prices are "the same".
        min_mismatch: How many bars must disagree before this reports an
                      adjustment.

    Returns:
        An :class:`AdjustmentCheck`. ``adjusted`` is False whenever the two
        agree, whenever they do not overlap at all, and whenever fewer than
        ``min_mismatch`` bars disagree — in all three cases the caller should
        write the fetched bars as usual.
    """
    if not stored or not fetched:
        return AdjustmentCheck(adjusted=False)

    by_date = {q.date: q for q in fetched}

    ratios: list[tuple[date, float]] = []
    for bar in stored:
        fresh = by_date.get(bar.date)
        if fresh is None:
            continue
        old = float(bar.close)
        new = float(fresh.close)
        # A zero or negative close is not a price; it cannot anchor a ratio.
        if old <= 0.0 or new <= 0.0:
            continue
        ratios.append((bar.date, new / old))

    if not ratios:
        return AdjustmentCheck(adjusted=False)

    off = [(d, r) for d, r in ratios if abs(r - 1.0) > tolerance]
    if len(off) < min_mismatch:
        return AdjustmentCheck(
            adjusted=False,
            compared=len(ratios),
            mismatched=len(off),
            reason=f"{len(ratios)} overlapping bars agree with the stored history",
        )

    factor = statistics.median(r for _, r in off)
    # A corporate action rescales every bar before its ex-date by one factor.
    # Bars that disagree by *different* amounts are the provider correcting
    # individual figures instead — still a reason to re-fetch, but not a split.
    consistent = all(abs(r / factor - 1.0) <= tolerance for _, r in off)
    dates = [d for d, _ in off]

    return AdjustmentCheck(
        adjusted=True,
        ratio=factor,
        compared=len(ratios),
        mismatched=len(off),
        consistent=consistent,
        first_date=min(dates),
        last_date=max(dates),
        reason=describe_adjustment(factor, len(off), len(ratios), consistent),
    )


def describe_adjustment(
    ratio: float,
    mismatched: int,
    compared: int,
    consistent: bool,
) -> str:
    """One line of plain language explaining what changed, for the log."""
    where = f"{mismatched} of {compared} overlapping bars"
    if not consistent:
        return (
            f"{where} differ from the stored history by varying amounts "
            "(the data provider restated individual figures)"
        )
    return f"{where} were restated {_ratio_phrase(ratio)}"


def _ratio_phrase(ratio: float) -> str:
    """Render an adjustment factor the way a person would describe it.

    ``0.25`` becomes ``x0.2500 (looks like a 1:4 split)``. A split is recognised
    by the factor sitting close to a simple whole-number ratio; anything else is
    reported as a plain factor, which is what a dividend adjustment looks like.
    """
    base = f"x{ratio:.4f}"
    if ratio <= 0.0:
        return base

    # A forward split divides prices (1:4 gives x0.25); a reverse split
    # multiplies them (4:1 gives x4). Test the whole-number side of whichever
    # this is.
    forward = ratio < 1.0
    whole = (1.0 / ratio) if forward else ratio
    nearest = round(whole)
    if nearest >= 2 and abs(whole - nearest) <= 0.02 * nearest:
        split = f"1:{nearest}" if forward else f"{nearest}:1"
        return f"{base} (looks like a {split} split)"
    return f"{base} (dividend or other adjustment)"
