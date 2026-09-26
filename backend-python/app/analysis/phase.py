"""Wyckoff/VSA background phase analysis — is this stock under accumulation or distribution?

Roadmap #15a. ``vsa.py`` detects patterns bar by bar; this module reads the
*background* those patterns sit in, which Master the Markets treats as the thing
that decides what a pattern means at all:

    "Do not view lack of demand in isolation – try to take a holistic view when
    reading the market.  You should always look to the background." (p.32)

    "Taken in isolation the actions at (c) & (d) mean little, but because you
    have seen absorption volume in the background, they now become strong buy
    signals." (p.88)

The engine already had a background proxy: the close against a 30-bar moving
average. That reads *price direction* and nothing else, and price direction is
not what Williams means. The clearest demonstration is the up-thrust:

    "Up-thrusts are usually seen after a rise in the market, where the market
    has now become overbought and there is weakness in the background." (p.~74)

A rise *and* weakness — two things a single moving average cannot separate,
because to it "price is high" and "the background is strong" are the same
reading. Distribution is defined in the book by volume, not by price:

    "there is little, or no, major distribution phase in the background, which
    is normally indicated by high volume on up-bars near a market top.  There
    is no buying climax in the background either." (p.~90, the shake-out chart)

So this module classifies the background from **volume pressure** and the
**effort-vs-result** evidence Williams names, positioned within the recent
range, into the four Wyckoff phases plus "neutral" when the evidence is thin.

Every column is computed from bars strictly *before* the bar being judged
(``.shift(1)``), so a phase reading can never see its own bar or the future.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.models import StooqDailyQuote


class Phase(enum.StrEnum):
    """The background a signal is read against (Master the Markets pp.20–21)."""

    ACCUMULATION = "accumulation"
    MARKUP = "markup"
    DISTRIBUTION = "distribution"
    MARKDOWN = "markdown"
    # Not enough history, or the evidence does not clearly say. Treated
    # everywhere as "do not judge", never as a weak version of another phase.
    NEUTRAL = "neutral"


# How many prior sessions form "the background". Matches the trend lookback in
# vsa.py so the two reads describe the same stretch of chart, and is long
# enough to contain a real accumulation range (Williams describes these as
# weeks-to-months affairs) while still fitting the engine's 120-bar analysis
# slice with warm-up to spare.
_LOOKBACK = 30

# The shortest background that may be judged at all. Below this the phase is
# NEUTRAL: a handful of bars cannot show an accumulation campaign, and guessing
# from them is exactly the error this module exists to stop.
_MIN_BARS = 20

# "High volume" for the absorption / climax evidence, as a multiple of the
# window's own average volume. Williams never numbers it; 1.5× is the same
# threshold the engine's own high-volume rules use, so the background and the
# signals agree on what "high volume" means.
_HIGH_VOL_MULT = 1.5

# Where a bar's close must sit within its own range to count as closing
# "on the highs" / "on the lows" (0 = low, 1 = high).
_CLOSE_STRONG = 0.6
_CLOSE_WEAK = 0.4

# Where the current price must sit within the window's high-low range to be
# "near the top" / "near the bottom" of it.
_RANGE_UPPER = 0.6
_RANGE_LOWER = 0.4

# Neutral band around 1.0 for the up-volume / down-volume ratio. Inside it,
# volume is not concentrating on either side and the pressure reading abstains.
_PRESSURE_BAND = 0.15

# How much the window's close-to-close move must be, as a fraction, to count as
# a genuine advance or decline rather than a drift. Accumulation "usually
# happens after a bear move has taken place" (p.20), so the prior move is part
# of the evidence, not decoration.
_MOVE_BAND = 0.05

# How many pieces of qualifying evidence a phase needs before it is called.
# One high-volume up-bar near a top is an incident; several are a campaign.
_MIN_EVIDENCE = 2

# What share of the window must be quiet bars in the trend's own direction for
# "volume drying up" to count as one piece of evidence. Applied identically to
# both sides (quiet down-bars for accumulation, quiet up-bars for distribution).
_QUIET_SHARE = 0.25


def add_phase_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add the per-bar background evidence columns to an OHLCV frame, in place.

    Expects the columns ``high``, ``low``, ``close``, ``volume`` and
    ``close_pos`` (the close's position within its own spread, NaN on a
    zero-spread bar) that ``vsa.detect_signals`` already builds.

    Every column is shifted by one bar, so the value on row *i* describes the
    background *leading into* bar *i* and never includes bar *i* itself.
    """
    up = df["close"] > df["close"].shift(1)
    down = df["close"] < df["close"].shift(1)

    # Every window below carries ``min_periods=_MIN_BARS`` so the evidence
    # warms up at the same point the classifier is willing to judge. With
    # pandas' default (min_periods = the full window) the averages stay NaN for
    # the first 30 bars and the rolling *counts* of evidence built on them stay
    # empty for 30 more — a stock with 50 bars of history would report "enough
    # background" while no absorption or climax bar could ever be counted.
    def _roll(series: pd.Series) -> pd.core.window.rolling.Rolling:
        return series.rolling(_LOOKBACK, min_periods=_MIN_BARS)

    # Volume pressure: does volume concentrate on up-bars or down-bars?
    # "What is Bullish & Bearish Volume" (p.19) — volume arriving on up-bars is
    # demand, on down-bars supply.
    up_vol = _roll(df["volume"].where(up, 0.0)).sum().shift(1)
    down_vol = _roll(df["volume"].where(down, 0.0)).sum().shift(1)
    df["phase_up_vol"] = up_vol
    df["phase_down_vol"] = down_vol
    df["phase_pressure"] = (up_vol / down_vol).where(down_vol > 0)

    avg_vol = _roll(df["volume"]).mean().shift(1)
    high_vol = df["volume"] > avg_vol * _HIGH_VOL_MULT

    # Absorption (strength in the background): a high-volume DOWN-bar that
    # closes in the upper part of its range. Williams, of exactly this bar:
    # "we have a high volume down-day closing on the highs.  If the high volume
    # had been selling, how can it close on the highs?  (Demand is overcoming
    # the supply)" (p.42). This is the evidence that turns a later test into a
    # "strong buy signal".
    absorption_bar = high_vol & down & (df["close_pos"] >= _CLOSE_STRONG)
    df["phase_absorption"] = _roll(absorption_bar.astype(float)).sum().shift(1)

    # Climax / distribution (weakness in the background): a high-volume UP-bar
    # that fails to close strongly — the book's own definition of a
    # distribution phase, "high volume on up-bars near a market top", and of the
    # buying climax that accompanies it.
    climax_bar = high_vol & up & (df["close_pos"] <= _CLOSE_WEAK)
    df["phase_climax"] = _roll(climax_bar.astype(float)).sum().shift(1)

    # Supply drying up on down-bars: "If you begin to notice the volume drying
    # up on down-bars, this is evidence that the amount of selling pressure is
    # reducing" (p.31). Counted as quiet down-bars — below the window average.
    quiet_down = down & (df["volume"] < avg_vol)
    df["phase_quiet_down"] = _roll(quiet_down.astype(float)).sum().shift(1)

    # Demand drying up on up-bars — the exact mirror, and just as explicit:
    # "This weakness is shown by a decrease in trading volume, as the stock or
    # Index attempts to go up (no demand) ... This action will confirm any
    # signs of weakness in the background that you have detected" (p.88); and
    # "no way a market can rally up through an old trading top ... on this lack
    # of demand" (p.32). Without this the distribution side had one evidence
    # source fewer than the accumulation side, and read 5.6× rarer on GPW
    # history for that reason alone rather than because tops are rarer.
    quiet_up = up & (df["volume"] < avg_vol)
    df["phase_quiet_up"] = _roll(quiet_up.astype(float)).sum().shift(1)

    # Where price sits inside the window's own range, and how far the window
    # travelled. Both from prior bars only.
    win_high = _roll(df["high"]).max().shift(1)
    win_low = _roll(df["low"]).min().shift(1)
    span = win_high - win_low
    prev_close = df["close"].shift(1)
    df["phase_range_pos"] = ((prev_close - win_low) / span).where(span > 0)

    # The window's own starting close. ``shift(_LOOKBACK)`` would be NaN for
    # every bar before the window is full, which would silence the prior-move
    # evidence exactly where the warm-up above was fixed; indexing the window's
    # first bar keeps it defined from _MIN_BARS onward. The index is always
    # behind the current bar, so this still cannot look ahead.
    positions = np.arange(len(df))
    window_start = np.maximum(positions - _LOOKBACK, 0)
    window_open = pd.Series(df["close"].to_numpy()[window_start], index=df.index)
    df["phase_move"] = ((prev_close - window_open) / window_open).where(window_open > 0)

    # How many bars of real history back this row, so the classifier can
    # abstain instead of reading a phase off a nearly empty window.
    df["phase_bars"] = df["close"].rolling(_LOOKBACK, min_periods=1).count().shift(1)
    return df


def classify_row(row: pd.Series) -> Phase:
    """The background phase leading into one bar.

    Returns ``Phase.NEUTRAL`` whenever the evidence does not clearly say —
    which is the honest answer far more often than not, and is what stops this
    module from inventing a Wyckoff narrative for every sideways drift.
    """
    bars = row.get("phase_bars")
    if bars is None or pd.isna(bars) or bars < _MIN_BARS:
        return Phase.NEUTRAL

    pos = row.get("phase_range_pos")
    move = row.get("phase_move")
    pressure = row.get("phase_pressure")
    absorption = row.get("phase_absorption")
    climax = row.get("phase_climax")
    quiet_down = row.get("phase_quiet_down")
    if pos is None or pd.isna(pos) or move is None or pd.isna(move):
        return Phase.NEUTRAL

    quiet_up = row.get("phase_quiet_up")
    absorption = 0.0 if absorption is None or pd.isna(absorption) else float(absorption)
    climax = 0.0 if climax is None or pd.isna(climax) else float(climax)
    quiet_down = 0.0 if quiet_down is None or pd.isna(quiet_down) else float(quiet_down)
    quiet_up = 0.0 if quiet_up is None or pd.isna(quiet_up) else float(quiet_up)

    # Volume pressure as a three-way lean, abstaining inside the neutral band
    # and when one side of the window had no volume at all.
    if pressure is None or pd.isna(pressure):
        lean = 0
    elif pressure >= 1.0 + _PRESSURE_BAND:
        lean = 1
    elif pressure <= 1.0 - _PRESSURE_BAND:
        lean = -1
    else:
        lean = 0

    rising = move >= _MOVE_BAND
    falling = move <= -_MOVE_BAND

    # ── Trending, and carried by volume ──────────────────────────────────────
    # Checked BEFORE the range-position phases. An advance that is still
    # advancing, with demand behind it and no climax evidence, is mark-up — not
    # a top — even though price is by definition high in its own range. Reading
    # it as distribution is the error a range-position test makes on its own:
    # measured on GPW history it discarded bullish signals whose median 30-bar
    # background was +4.7% and still rising, and those were the *better* half
    # (+4.90pp of baseline-excess at 30 sessions against +0.64pp for the ones
    # kept). Williams' distribution is a market that "has now become overbought"
    # and has stopped going up; a running advance has not.
    if rising and lean > 0 and climax < _MIN_EVIDENCE:
        return Phase.MARKUP
    if falling and lean < 0 and absorption < _MIN_EVIDENCE:
        return Phase.MARKDOWN

    # ── Distribution ─────────────────────────────────────────────────────────
    # "high volume on up-bars near a market top" (p.90), after a rise, with
    # demand no longer carrying the volume. Checked before mark-up, because a
    # distribution range is by construction the top of an advance and would
    # otherwise be read as a healthy one.
    if pos >= _RANGE_UPPER and not falling:
        evidence = climax + (1 if lean < 0 else 0)
        if quiet_up >= _LOOKBACK * _QUIET_SHARE:
            evidence += 1
        if evidence >= _MIN_EVIDENCE:
            return Phase.DISTRIBUTION

    # ── Accumulation ─────────────────────────────────────────────────────────
    # Buying "after a bear move has taken place" (p.20), low in the range, with
    # absorption or with selling pressure drying up — the supply being removed.
    if pos <= _RANGE_LOWER and not rising:
        evidence = absorption + (1 if lean > 0 else 0)
        if quiet_down >= _LOOKBACK * _QUIET_SHARE:
            evidence += 1
        if evidence >= _MIN_EVIDENCE:
            return Phase.ACCUMULATION

    # Anything else — including a move whose volume disagrees with it — is left
    # NEUTRAL rather than forced into a label: an advance on falling volume is
    # precisely the case Williams warns is not what it looks like, and saying
    # so is more honest than naming a phase for it.
    return Phase.NEUTRAL


def classify_bars(bars: Sequence[StooqDailyQuote]) -> Phase:
    """The background phase leading into the LAST bar of a series.

    Convenience wrapper for callers that hold quotes rather than a frame (the
    per-stock cards, tests). Returns ``Phase.NEUTRAL`` on too little history.
    """
    if len(bars) < _MIN_BARS + 1:
        return Phase.NEUTRAL

    df = pd.DataFrame(
        [
            {
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
                "date": b.date,
            }
            for b in bars
        ]
    ).sort_values("date").reset_index(drop=True)
    df["spread"] = df["high"] - df["low"]
    df["close_pos"] = ((df["close"] - df["low"]) / df["spread"]).where(df["spread"] > 0)
    add_phase_columns(df)
    return classify_row(df.iloc[-1])


# ── How a phase bears on a signal ────────────────────────────────────────────

# Signals of strength (Spring, Test, SOS) and of weakness (Upthrust, No Demand,
# SOW) each want a background that supports them:
#
#   "Testing is a good sign of strength (as long as you have strength in the
#    background)." (p.34)
#   "Up-thrusts are usually seen after a rise in the market, where the market
#    has now become overbought and there is weakness in the background."
#
# CONFIRMS   — the textbook location for this signal; it reads at full strength.
# ALLOWS     — nothing in the background argues either way; the signal stands
#              but at reduced weight ("taken in isolation ... mean little").
# CONTRADICTS— the background says the opposite of what the signal claims.
_BULLISH_STANCE: dict[Phase, str] = {
    Phase.ACCUMULATION: "confirms",
    Phase.MARKUP: "confirms",
    Phase.NEUTRAL: "allows",
    Phase.MARKDOWN: "allows",  # a test inside a decline may be the turn itself
    Phase.DISTRIBUTION: "contradicts",
}

_BEARISH_STANCE: dict[Phase, str] = {
    Phase.DISTRIBUTION: "confirms",
    Phase.MARKDOWN: "confirms",
    Phase.NEUTRAL: "allows",
    Phase.MARKUP: "allows",  # an upthrust inside an advance may be the turn
    Phase.ACCUMULATION: "contradicts",
}

# What "allows" costs a signal. Williams is explicit that an unconfirmed
# pattern is not worthless, just not the strong version — so it keeps most of
# its weight rather than being silenced.
_ALLOWS_WEIGHT = 0.75

# What "contradicts" costs it. Deliberately NOT zero, for two reasons. Williams
# says an unsupported pattern "means little", not that it is absent — and a
# dropped signal also disappears from the stock chart, so the reader loses the
# bar rather than being told to distrust it. Down-weighting keeps the marker on
# the chart and moves the doubt into the rating, where it belongs. Measured on
# GPW history, deleting them outright also made the engine worse: the deleted
# bullish signals were the better-performing half.
_CONTRADICTS_WEIGHT = 0.35


def stance(phase: Phase, bullish: bool) -> str:
    """Whether the background confirms, allows or contradicts a signal."""
    table = _BULLISH_STANCE if bullish else _BEARISH_STANCE
    return table.get(phase, "allows")


def strength_multiplier(phase: Phase, bullish: bool) -> float:
    """Factor to apply to a detected signal's strength, given its background.

    Always > 0: a contradicting background discounts a signal heavily but never
    erases it, so the pattern still appears on the chart and only its weight in
    the rating changes.
    """
    verdict = stance(phase, bullish)
    if verdict == "confirms":
        return 1.0
    if verdict == "allows":
        return _ALLOWS_WEIGHT
    return _CONTRADICTS_WEIGHT
