"""VSA 3 — the whole Glinicki decision loop, from the 34-transcript compendium.

Source: *Kompendium VSA*, a synthesis of the **transcripts** of Rafal Glinicki's
30-lesson XTB *Investing Masters* course "Analiza ceny i wolumenu" plus the four
lessons of his 2018 VSA course (34 recordings in all). It is the same author and
the same course as the one behind earlier VSA V2, but a different reading of
it: V2 was built from the slides (the image layer — only lesson 1 of the 30 had
a transcript then), this one from what is *said* in every lesson. The spoken
material fills in most of what the slides left blank, and that is what this
method adds:

    * the CATEGORY of every signal. The slides never said which of the fourteen
      signals were climactic, absorbing or testing, so V2 could not build the
      course's three-signal sequence. The transcripts do (lessons 7-20), so the
      sequence is tracked here (lessons 23-24) as a high-confidence booster;
    * the SUPERIOR TIMEFRAME. "Wyzsza skala czasowa jest zawsze nadrzedna"
      (lessons 1, 29): the trend is assessed on the higher interval first, with
      three outcomes — up, down, or an undecided market, where "brak pozycji
      jest pozycja". On end-of-day bars the higher interval is the weekly chart;
    * BULLISH VOLUME (lesson 6): volume grows on the up-waves and shrinks on the
      down-waves. "Nigdy nie graj przeciwko wolumenowi w skali, w ktorej grasz";
    * the ACCENT (lesson 27). A correction on expiring volume that just stops is
      not played — the stop would be too far. "Gra sie korekte z akcentem": the
      quiet pullback must end in one sharp move on clearly raised volume;
    * the FULL WFO (lessons 25-26): eight necessary conditions, including the
      one "easiest to miss" — the second extreme's volume must exceed every bar
      between the two extremes — and a recognisable VSA signal at the second;
    * a working definition of the ABC CORRECTION, the third route to a WM that
      V2 had to leave out. The course still never defines it; the compendium
      proposes "a three-wave pullback whose C wave ends on corrective volume",
      and that proposal is what runs here, marked as such.

The setup is lesson 29's Scenario 5 (long), run through the course's own
decision loop (compendium section 15). A bar FIRES when the six core criteria hold:

    0. TREND   The weekly chart (completed weeks only) is in an uptrend: its
               last quarter made a higher high AND a higher low than the one
               before.
    1. BACKGROUND  Daily volume is not bearish: the up-waves do not trade on
               less volume than the down-waves.
    2. PLACE   The pullback halted in a WM: a 38.2 / 41.4 / 50 / 61.8
               retracement of the last impulse (lesson 22), a bullish WFO, or
               the end of an ABC correction.
    3. NO SUPPLY AT PEAK  "Brak podazy w szczycie": no climactic or absorbing signal of
               weakness at the peak the pullback fell from (Supply Coming In
               excepted — the course says it "rarely makes the top by itself").
    4. CORRECTION  The approach to the WM ran on corrective volume — lighter,
               fading volume or ended by an accent (Stopping Volume, Shakeout,
               Two Bar Reversal, or Hammer on volume).
    5. FORMATION + SIGNAL  A bullish candle formation completes at the low AND
               a VSA signal of strength confirms it ("potwierdzona" — together,
               never either). Exception since the 2026-09-24 relaxation: a
               Hammer with no signal is accepted on its own volume, and is
               then labelled "high volume" / "low volume", not as a signal.
    6. R/R     The trade still offers at least 3:1 to the peak, with the stop
               under the whole formation, shadows included.

BOOSTERS:
    * SEQUENCE: Three signals of strength in the price zone (climax/absorption
      first, test last) boost the score to 100 with a "(3-sig seq)" badge.
    * WFO: A volume divergence at the low also boosts confidence to 100.

(Layer 3 of the course's loop is the bar measurement itself — spread, close
position, up/down bar, pink volume — which every rule below reads.)

PROVENANCE. The compendium marks every rule, and the markers are honoured here:

    [Z] said verbatim in a recording. Seven numbers in this file are of that
        kind and nothing else is: the close-position terciles (1/3 and 2/3),
        the pink-volume rule (V_t < V_t-1 AND V_t < V_t-2), the Hammer's body
        of at most 1/3 of the range, the 50%-of-the-body Piercing rule, the four
        retracement levels, three signals in a sequence, and R/R 3:1.
    [F] the compiler's formalisation of a spoken rule (the wave split behind
        bullish volume, the triple's category order, "a shadow counts from a
        third of the range").
    [L] a gap the course leaves open — every "wide", "narrow", "high", "near"
        and "clearly lower" below. Each such constant is marked and is a
        calibration choice, not a claim about the source.

WHERE THE TRANSCRIPTS DISAGREE WITH V2's SLIDE READING, V3 follows the
transcripts, which is the point of a new method rather than a V2 edit:

    * close position is judged in THIRDS ("chodzi o 1 trzecia", lesson 14), not
      the 30/70 split V2 read off a slide;
    * the Two Bar Reversal of strength needs the up bar's volume to EXCEED the
      down bar's ("V2 > V1 — warunek konieczny", lesson 11). V2 reads the slide's
      two short volume bars and demands both be quiet; here a quiet pair is the
      TESTING variant and a loud one the ABSORBING variant, as lesson 11 says;
    * the Morning Star's stop goes under the LOWEST point of all three candles
      ("wraz z cieniami", lesson 3), not under the middle candle;
    * "ultra-high volume" is a volume never seen further left in the window —
      "niewidziany do tej pory po lewej stronie" — not a multiple of an average.

WHAT IS STILL NOT IMPLEMENTED, on purpose: the psychophysical self-check, the
position sizing and the daily entry limits (they are about the trader, not the
chart); the choice of an "optimal exit" (it happens after entry); and the
higher-scale target for a higher-order correction (the target is always this
scale's peak). The course also recommends that a script REPORT rather than
decide — "niech skrypt liczy ... a decyzje podejmuje czlowiek" — which is what
the score is for: it says how many of the loop's layers stand today, so a stock
waiting for its last signal is visible before the setup completes.

MEASURED NOW (2026-09-27, all six markets, 1,010 companies): the relaxed loop
completes **394 times** in the whole stored history; 75 of them are Hammers
accepted on their own volume (see layer 5). Everything below this paragraph
describes the STRICT version as built on 2026-09-22 — the three-signal
sequence a hard gate, the accent required, the geometry zone 3% — which the
2026-09-24 relaxation replaced; it is kept as the record of that decision.

MEASURED (2026-09-22, the local database, all six markets: 1,014 companies,
276,103 judged bars). The loop completes FOUR times in the whole stored history
(three of them on the GPW). Per completed candle formation:

    41331  a bullish formation completed
    22701  ...with a live pullback off a measured impulse
     9635  ...still offering 3:1
     8179  ...at the correction's low
     4912  ...on a weekly uptrend
     2740  ...with daily volume not bearish
      945  ...in a WM (geometry 392, ABC 513, WFO 40)
      562  ...with no supply at the peak
      222  ...on corrective volume
       84  ...ended by an accent
       55  ...confirmed by a VSA signal
        4  ...closing a three-signal sequence

The sequence is the binding layer: a daily pullback's low is a handful of bars,
and the course's sequences are read on intraday charts where the low holds
dozens. That strictness is the owner's choice, made with these numbers in front
of him (2026-09-22) — relaxing the sequence alone, or the sequence and the
weekly trend, was measured and not adopted. With so few firings the back-test
gate (``GET /api/stocks/methods/vsa3/backtest``) reads "insufficient" by
construction, so the score has no measured edge behind it: judge it as the
scanner the course asks for, not as a proven signal.

Like every other method here it reproduces the source's own rules (Glinicki
teaches on intraday FX and index charts; VSA is interval-agnostic and the
course says so) rather than GPW-tuned ones.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    register_method,
)
from app.analysis.vsa import VsaConfig
from app.models import StooqDailyQuote

# ── Measurement layer (compendium section 02) ─────────────────────────────────
# Rolling reference windows. The course never gives one — "everything is
# relative to the bars on the left" [L] — and calls this "the most important
# design decision". 20 sessions is the average the course puts on screen.
_VOL_MA = 20
_SPREAD_MA = 20
# Close position in thirds of the bar [Z]: CP >= 2/3 is a high close, CP <= 1/3
# a low one, anything between a middle close.
_HIGH_CLOSE = 2.0 / 3.0
_LOW_CLOSE = 1.0 / 3.0
# Pink volume [Z]: "volume lower than the previous two bars", N = 2.
_PINK_N = 2
# "Ultra-high" volume is a volume "not seen so far on the left of the chart" —
# the maximum of a window, not a multiple of the average (the compendium lists
# the average-based version among its implementation traps). The window's
# length is not given [L].
_ULTRA_WINDOW = 30
# Spread classes against the 20-session average spread [L].
_WIDE = 1.2
_NARROW = 0.7
# Volume classes against the 20-session average [L]. "Significant" (znaczny)
# is anything from the average up, "low" is below it.
_HIGH_VOL = 1.5
_ELEVATED_VOL = 1.2
# A shadow that counts as a shadow: at least one of the course's thirds [F]...
_SHADOW = 1.0 / 3.0
# ...and a LONG one, half the bar [L] (Upthrust, No Result From Effort).
_LONG_SHADOW = 0.5
# Background: how many bars the move into a signal is read over — a clear trend
# for a climax, a shorter move for everything else [L].
_CLIMAX_CONTEXT = 10
_CONTEXT = 5

# ── Signals (compendium section 06, K1-K15) ───────────────────────────────────
# Shakeout / Upthrust: how far back "the earlier low / high" is read [L — the
# compendium names this window as a calibration parameter].
_LEVEL_LOOKBACK = 10
_BREAK_LOOKBACK = 5
# Two Bar Reversal: candle 2 closes "around candle 1's OPEN or higher" [Z]; how
# close "around" is, is not said [L]. "V2 ≈ V1 is acceptable" [Z] — how close
# "≈" is, is not said either [L].
_TBR_TOLERANCE = 0.1
_TBR_VOL_EQUAL = 0.95
# Stopping Volume: candle 2's body stays in the lower or middle part of candle
# 1's range [L — marked as a gap on the K3 card].
_SV_REACH = 2.0 / 3.0
# Trap Upmove: "a close VERY low" and "a large red body" [L].
_TRAP_CLOSE = 0.2
_TRAP_BODY = 0.5
# Test: how far back the accumulation it tests may sit [L].
_TEST_CONTEXT_LOOKBACK = 40

# ── Formations (compendium section 04) ────────────────────────────────────────
# Hammer: "the body no bigger than 1/3 of the whole" [Z]; "a big shadow on TOP
# disqualifies — that is a spinning top, not a hammer" [Z], its size is [L].
_SMALL_BODY = 1.0 / 3.0
_NEGLIGIBLE_SHADOW = 0.1
# A formation bar must be a real session's range, not a sliver [L]; proportion
# rules are scale-free and would otherwise match a bar a fraction of a normal
# day's range (measured on GPW data when V1 shipped).
_MIN_SPREAD_MULT = 0.5
# "Large" and "has a meaningful midpoint" bodies, in average spreads [L].
_LONG_BODY_SPREADS = 0.5
_MIN_BODY_SPREADS = 0.3
# Morning Star: "a small middle candle" against candle 1's body [L].
_STAR_BODY_MAX = 0.35
# Inside Bar: how many inside bars one mother bar may hold [L — "the allowed
# number of inside candles" is a listed gap].
_INSIDE_MAX = 3

# ── Waves (compendium section 03) ─────────────────────────────────────────────
# Bullish/bearish volume is read over WAVES, not bars, and "the way the history
# is split into waves is a gap" [L]: a zigzag that turns once price retraces
# this many average spreads off its running extreme.
_WAVE_REVERSAL = 2.0
# How much of the daily history the volume character is read over [L].
_CHARACTER_LOOKBACK = 120

# ── The impulse and its correction ────────────────────────────────────────────
_MIN_CORRECTION = 3
_MAX_CORRECTION = 60
# The impulse is measured from the lowest swing low of this many sessions
# before the peak [L — the course never says which low the retracement is
# drawn from, only "od dolka do szczytu"].
_IMPULSE_LOOKBACK = 60
_MIN_IMPULSE_PCT = 0.05
# Retracement levels [Z, lessons 22 and 29].
_GEOMETRY_LEVELS = (0.382, 0.414, 0.500, 0.618)
# In lesson 22 Glinicki stresses that whether geometry is hit to the tick or
# slightly undershot/overshot does not matter — "to nie ma znaczenia, rozstrzyga
# sygnał VSA". At 4% of the impulse 38.2 and 41.4 read cleanly, and any halt
# in the 35%-65% golden pocket with a confirmed VSA signal validates geometry.
_GEOMETRY_ZONE = 0.04
# The price zone the end of the correction is read in: everything within this
# many average spreads of its lowest low [L — the sequence's "same price zone"
# has no width in the course].
_ZONE_SPREADS = 2.0

# ── WFO (compendium section 09) ───────────────────────────────────────────────
_PIVOT_K = 2
_WFO_MIN_GAP = 3
_WFO_MIN_BOUNCE = 0.02

# ── No supply at the peak ─────────────────────────────────────────────────────
_PEAK_BACK = 3
_PEAK_FWD = 3

# ── The correction's character (compendium section 10) ────────────────────────
# The approach must have enough bars to have a volume trend at all [L].
_MIN_APPROACH = 4
# Corrective volume is "clearly lower than on the impulse" [L for "clearly"].
_CORRECTIVE_RATIO = 0.85
# An accent is on volume "clearly exceeding the correction's own" [L].
_ACCENT_MULT = 1.5

# ── The superior timeframe ────────────────────────────────────────────────────
# The weekly trend compares the last two quarters of completed weekly bars
# [L — see ``_weekly_trend`` for why this and not weekly swing points].
_WEEKLY_HALF = 13

# ── The setup ─────────────────────────────────────────────────────────────────
# How many bars before the formation its confirming signal may sit [L].
_CONFIRM_WINDOW = 3
# Three signals in a sequence [Z, lessons 12, 23, 24].
_SEQUENCE_LEN = 3
# The course's one arithmetic filter [Z, lessons 28-29].
_MIN_RR = 3.0
_RECENT_FIRED = 10
_RECENCY_SCAN = 60
_TOTAL_LAYERS = 7
# A pattern at the low that missed at most this many layers is reported in the
# result's detail as "not taken", with the reasons. A presentation choice, not
# a rule of the method: it never changes what fires or what the score counts.
_NEAR_MISS_LAYERS = 2
# Half a year of weekly bars for the superior-scale trend (~30 weeks, the floor
# the app's own weekly read uses) plus the daily windows; every tracked GPW
# company clears it.
_MIN_BARS = 150

_CLIMACTIC = "climactic"
_ABSORBING = "absorbing"
_TESTING = "testing"
# Where a category may stand in a sequence: climactic, then absorbing, then
# testing — never backwards (lesson 23: "odwrocona kolejnosc" is one of the
# two sequences that make no sense).
_STAGE = {_CLIMACTIC: 0, _ABSORBING: 1, _TESTING: 2}


def _sma_before(values: Sequence[float], length: int) -> list[float | None]:
    """Mean of the ``length`` values strictly BEFORE each index (None early)."""
    out: list[float | None] = [None] * len(values)
    if length <= 0 or len(values) <= length:
        return out
    run = sum(values[:length])
    for i in range(length, len(values)):
        out[i] = run / length
        run += values[i] - values[i - length]
    return out


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


# ── Bars and the measurement layer ────────────────────────────────────────────


@dataclass(frozen=True)
class _Series:
    """One stock's bars plus the rolling context every rule reads."""

    dates: list[date]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    avg_vol: list[float | None]
    avg_spread: list[float | None]

    @classmethod
    def build(cls, bars: Sequence[StooqDailyQuote]) -> _Series:
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]
        volumes = [float(b.volume) for b in bars]
        spreads = [h - low for h, low in zip(highs, lows, strict=True)]
        return cls(
            dates=[b.date for b in bars],
            opens=[float(b.open) for b in bars],
            highs=highs,
            lows=lows,
            closes=[float(b.close) for b in bars],
            volumes=volumes,
            avg_vol=_sma_before(volumes, _VOL_MA),
            avg_spread=_sma_before(spreads, _SPREAD_MA),
        )

    def __len__(self) -> int:
        return len(self.closes)

    def body(self, i: int) -> float:
        return abs(self.closes[i] - self.opens[i])

    def rng(self, i: int) -> float:
        """The spread: the full bar, shadows included, not the body [Z]."""
        return self.highs[i] - self.lows[i]

    def upper_shadow(self, i: int) -> float:
        return self.highs[i] - max(self.opens[i], self.closes[i])

    def lower_shadow(self, i: int) -> float:
        return min(self.opens[i], self.closes[i]) - self.lows[i]

    def close_pos(self, i: int) -> float | None:
        """CP = (C - L) / (H - L), read in thirds [Z]."""
        rng = self.rng(i)
        if rng <= 0:
            return None
        return (self.closes[i] - self.lows[i]) / rng

    def is_up_bar(self, i: int) -> bool:
        """An up bar closes above the PREVIOUS CLOSE, whatever its colour [Z].

        The compendium's first implementation trap: the platform colours volume
        by close-vs-open, the VSA definition compares two closes.
        """
        return i > 0 and self.closes[i] > self.closes[i - 1]

    def is_down_bar(self, i: int) -> bool:
        return i > 0 and self.closes[i] < self.closes[i - 1]

    def is_pink(self, i: int) -> bool:
        """Pink volume [Z]: lower than each of the previous two bars."""
        if i < _PINK_N or self.volumes[i] <= 0:
            return False
        return all(self.volumes[i] < self.volumes[i - k] for k in range(1, _PINK_N + 1))

    def is_ultra(self, i: int) -> bool:
        """A volume never seen further left in the window [F; window L]."""
        if i < _ULTRA_WINDOW or self.volumes[i] <= 0:
            return False
        return self.volumes[i] > max(self.volumes[i - _ULTRA_WINDOW : i])

    def context(self, i: int) -> tuple[float, float] | None:
        """(average volume, average spread) before bar ``i``, or None.

        Fails closed on an absent or zero average: a suspension's frozen bars
        would otherwise make every relative test true on the resumption bar.
        """
        if i < 0 or i >= len(self.closes):
            return None
        avg_v = self.avg_vol[i]
        avg_sp = self.avg_spread[i]
        if avg_v is None or avg_v < 1 or avg_sp is None or avg_sp <= 0:
            return None
        return avg_v, avg_sp


def _falling(s: _Series, i: int, n: int) -> bool:
    """The move INTO bar ``i`` is a decline: net lower over ``n`` bars, and at
    least half of them down bars. Read up to the bar before, so the signal bar's
    own close (a climax often closes back up) does not decide its context."""
    j = i - 1
    if j - n < 0:
        return False
    downs = sum(1 for k in range(j - n + 1, j + 1) if s.is_down_bar(k))
    return s.closes[j] < s.closes[j - n] and downs * 2 >= n


def _rising(s: _Series, i: int, n: int) -> bool:
    j = i - 1
    if j - n < 0:
        return False
    ups = sum(1 for k in range(j - n + 1, j + 1) if s.is_up_bar(k))
    return s.closes[j] > s.closes[j - n] and ups * 2 >= n


# ── Signals ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Signal:
    """One VSA signal, dated to the bar it becomes known on.

    ``start`` is the first bar it is drawn on (a pair starts a bar earlier; a
    No Supply or Test is drawn on the bar BEFORE the one that confirms it —
    "the confirmation is a separate bar", one of the compendium's traps).
    ``volume`` is the effort the signal is read by, which is what lesson 13's
    "each test on lower volume" compares.
    """

    label: str
    category: str
    start: int
    bar: int
    low: float
    volume: float


# Signals of strength (K1-K7), each dated at bar ``i``.


def _selling_climax(s: _Series, i: int) -> _Signal | None:
    """K2: a clear downtrend, the WIDEST spread of the move, a close in the
    middle third, a demand shadow underneath, on volume unseen to the left [Z].
    """
    ctx = s.context(i)
    if ctx is None or i < _CLIMAX_CONTEXT or not _falling(s, i, _CLIMAX_CONTEXT):
        return None
    _, avg_sp = ctx
    rng = s.rng(i)
    if rng < _WIDE * avg_sp or rng < max(s.rng(k) for k in range(i - _CLIMAX_CONTEXT, i)):
        return None
    cp = s.close_pos(i)
    if cp is None or not _LOW_CLOSE < cp < _HIGH_CLOSE:
        return None
    if s.lower_shadow(i) < _SHADOW * rng or not s.is_ultra(i):
        return None
    return _Signal("Selling Climax", _CLIMACTIC, i, i, s.lows[i], s.volumes[i])


def _bag_holding(s: _Series, i: int) -> _Signal | None:
    """K1: after a clear fall, a NARROW spread on volume unseen to the left.

    "In practice the colour of the body does not matter — what counts is the
    narrow spread and the ultra volume" [Z]. Narrow is what separates it from a
    Selling Climax, the only criterion between the two.
    """
    ctx = s.context(i)
    if ctx is None or not _falling(s, i, _CLIMAX_CONTEXT):
        return None
    _, avg_sp = ctx
    rng = s.rng(i)
    if rng <= 0 or rng > _NARROW * avg_sp or not s.is_ultra(i):
        return None
    return _Signal("Bag Holding", _CLIMACTIC, i, i, s.lows[i], s.volumes[i])


def _shakeout(s: _Series, i: int) -> _Signal | None:
    """K4: the low breaks the lows of the last k bars, the bar is wider than its
    neighbours and closes in its UPPER third, colour irrelevant [Z].

    On significant volume it absorbs supply; "a Shakeout on LOW volume is not an
    absorbing signal but a testing one — a brutal test" [Z].
    """
    if i < _LEVEL_LOOKBACK:
        return None
    ctx = s.context(i)
    if ctx is None or s.volumes[i] <= 0:
        return None
    avg_v, avg_sp = ctx
    if s.lows[i] >= min(s.lows[i - _LEVEL_LOOKBACK : i]):
        return None
    cp = s.close_pos(i)
    if cp is None or cp < _HIGH_CLOSE or s.rng(i) < _WIDE * avg_sp:
        return None
    category = _ABSORBING if s.volumes[i] >= avg_v else _TESTING
    return _Signal("Shakeout", category, i, i, s.lows[i], s.volumes[i])


def _two_bar_reversal(s: _Series, i: int) -> _Signal | None:
    """K5: a red down bar closing low, then an up bar closing at its OPEN or
    higher, with the up bar's volume above the down bar's — "a necessary
    condition; V2 ≈ V1 is acceptable" [Z].

    "On large volume it absorbs supply, on very small volume it tests" [Z].
    """
    j = i - 1
    if j < 1:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    avg_v, _ = ctx
    if s.closes[j] >= s.opens[j] or not s.is_down_bar(j):
        return None
    cp1 = s.close_pos(j)
    if cp1 is None or cp1 > _LOW_CLOSE or not s.is_up_bar(i):
        return None
    if s.closes[i] < s.opens[j] - _TBR_TOLERANCE * s.body(j):
        return None
    if s.volumes[j] <= 0 or s.volumes[i] < _TBR_VOL_EQUAL * s.volumes[j]:
        return None
    category = _ABSORBING if s.volumes[i] >= avg_v else _TESTING
    return _Signal(
        "Two Bar Reversal", category, j, i, min(s.lows[j], s.lows[i]), s.volumes[i]
    )


def _stopping_volume(s: _Series, i: int) -> _Signal | None:
    """K3: a down bar closing low on increased volume after a fall, then an up
    bar closing HIGH on its own range whose body stays in the lower or middle
    part of the first bar's range [Z; the reach is L].

    Candle 2's volume may be anything — "larger, comparable or smaller, even
    pink" [Z] — so the effort read is candle 1's. That, and the shorter reach,
    is what separates it from a Two Bar Reversal.
    """
    j = i - 1
    if j < 1:
        return None
    ctx_j = s.context(j)
    if ctx_j is None or s.context(i) is None:
        return None
    if not s.is_down_bar(j) or not _falling(s, j, _CONTEXT):
        return None
    cp1 = s.close_pos(j)
    if cp1 is None or cp1 > _LOW_CLOSE or s.volumes[j] < _ELEVATED_VOL * ctx_j[0]:
        return None
    cp2 = s.close_pos(i)
    if not s.is_up_bar(i) or cp2 is None or cp2 < _HIGH_CLOSE:
        return None
    if max(s.opens[i], s.closes[i]) > s.lows[j] + _SV_REACH * s.rng(j):
        return None
    return _Signal(
        "Stopping Volume", _ABSORBING, j, i, min(s.lows[j], s.lows[i]), s.volumes[j]
    )


def _no_supply_bar(s: _Series, j: int) -> bool:
    """K6's bar: a down bar, pink volume, low volume, a narrow spread [Z]."""
    ctx = s.context(j)
    if ctx is None:
        return False
    avg_v, avg_sp = ctx
    return (
        s.is_down_bar(j)
        and s.is_pink(j)
        and s.volumes[j] < avg_v
        and 0 < s.rng(j) <= _NARROW * avg_sp
    )


def _no_supply(s: _Series, i: int) -> _Signal | None:
    """K6 No Supply, dated at the bar that CONFIRMS it.

    "An UP BAR on the next candle, best on volume LARGER than the No Supply's.
    Without the increase Glinicki calls the confirmation ambiguous and prefers
    to pass" [Z] — so the increase is required. A run of No Supply bars is
    normal and waits for the first up bar, which is exactly this rule applied
    to the last of the run.
    """
    j = i - 1
    if j < _PINK_N or not _no_supply_bar(s, j):
        return None
    if not s.is_up_bar(i) or s.volumes[i] <= s.volumes[j]:
        return None
    return _Signal("No Supply", _TESTING, j, i, s.lows[j], s.volumes[j])


def _test_bar(s: _Series, j: int) -> bool:
    """K7's bar: a medium or narrow spread, small volume, and a shadow UNDER the
    bar — "a necessary condition" [Z]; body and colour do not matter."""
    ctx = s.context(j)
    if ctx is None:
        return False
    avg_v, avg_sp = ctx
    rng = s.rng(j)
    if rng <= 0 or rng >= _WIDE * avg_sp:
        return False
    if not 0 < s.volumes[j] < avg_v:
        return False
    return s.lower_shadow(j) >= _SHADOW * rng


_PRIMARY: tuple[Callable[[_Series, int], _Signal | None], ...] = (
    _selling_climax,
    _bag_holding,
    _shakeout,
    _two_bar_reversal,
    _stopping_volume,
)

# Signals of weakness (K8-K15). Only the STRONG ones are needed — climactic or
# absorbing — because this long-only method uses them as vetoes: at the peak
# ("no supply at the peak") and inside the sequence ("no strong opposite signal
# between them"). No Demand and the low-volume variants are testing signals and
# veto nothing.


def _buying_climax(s: _Series, i: int) -> _Signal | None:
    """K9: after a clear rise, a wide spread closing in the middle third under a
    supply shadow, on volume unseen to the left [Z]."""
    ctx = s.context(i)
    if ctx is None or not _rising(s, i, _CLIMAX_CONTEXT):
        return None
    _, avg_sp = ctx
    rng = s.rng(i)
    cp = s.close_pos(i)
    if rng < _WIDE * avg_sp or cp is None or not _LOW_CLOSE < cp < _HIGH_CLOSE:
        return None
    if s.upper_shadow(i) < _SHADOW * rng or not s.is_ultra(i):
        return None
    return _Signal("Buying Climax", _CLIMACTIC, i, i, s.lows[i], s.volumes[i])


def _end_of_rising_market(s: _Series, i: int) -> _Signal | None:
    """K8: after a clear rise, an up bar with a NARROW spread closing around the
    middle, on the largest volume seen on this side of the market [Z]."""
    ctx = s.context(i)
    if ctx is None or not _rising(s, i, _CLIMAX_CONTEXT) or not s.is_up_bar(i):
        return None
    _, avg_sp = ctx
    rng = s.rng(i)
    cp = s.close_pos(i)
    if rng <= 0 or rng > _NARROW * avg_sp or cp is None:
        return None
    if not _LOW_CLOSE < cp < _HIGH_CLOSE or not s.is_ultra(i):
        return None
    return _Signal("End of a Rising Market", _CLIMACTIC, i, i, s.lows[i], s.volumes[i])


def _trap_upmove(s: _Series, i: int) -> _Signal | None:
    """K11: in a rise, a bar that pushes above the last high and closes VERY low
    with a large red body and a shadow on top, on increased volume [Z]."""
    ctx = s.context(i)
    if ctx is None or not _rising(s, i, _CONTEXT) or s.highs[i] <= s.highs[i - 1]:
        return None
    avg_v, _ = ctx
    rng = s.rng(i)
    cp = s.close_pos(i)
    if rng <= 0 or cp is None or cp > _TRAP_CLOSE or s.closes[i] >= s.opens[i]:
        return None
    if s.body(i) < _TRAP_BODY * rng or s.upper_shadow(i) <= 0:
        return None
    if s.volumes[i] < _ELEVATED_VOL * avg_v:
        return None
    return _Signal("Trap Upmove", _ABSORBING, i, i, s.lows[i], s.volumes[i])


def _no_result_from_effort(s: _Series, i: int) -> _Signal | None:
    """K13: the bar after an up bar that closed high, above-average volume, a
    large spread, a LONG upper shadow and a close low [Z] — effort, no result."""
    ctx = s.context(i)
    if ctx is None or i < 2 or not _rising(s, i, _CONTEXT):
        return None
    avg_v, avg_sp = ctx
    cp_prev = s.close_pos(i - 1)
    if not s.is_up_bar(i - 1) or cp_prev is None or cp_prev < _HIGH_CLOSE:
        return None
    rng = s.rng(i)
    cp = s.close_pos(i)
    if s.volumes[i] <= avg_v or rng < _WIDE * avg_sp or cp is None or cp > _LOW_CLOSE:
        return None
    if s.upper_shadow(i) < _LONG_SHADOW * rng:
        return None
    return _Signal("No Result From Effort", _ABSORBING, i, i, s.lows[i], s.volumes[i])


def _upthrust(s: _Series, i: int) -> _Signal | None:
    """K15: pushed above the recent highs, a small body, a long upper shadow and
    a close in the LOWER third [Z] — green (classic) or red (hidden). On
    significant volume it floods demand; on low volume it only tests, and a
    test vetoes nothing, so only the first is reported."""
    if i < _BREAK_LOOKBACK:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    avg_v, _ = ctx
    rng = s.rng(i)
    cp = s.close_pos(i)
    if rng <= 0 or cp is None or cp > _LOW_CLOSE:
        return None
    if s.highs[i] <= max(s.highs[i - _BREAK_LOOKBACK : i]):
        return None
    if s.body(i) > _SMALL_BODY * rng or s.upper_shadow(i) < _LONG_SHADOW * rng:
        return None
    if s.volumes[i] < avg_v:
        return None
    return _Signal("Upthrust", _ABSORBING, i, i, s.lows[i], s.volumes[i])


def _two_bar_reversal_weak(s: _Series, i: int) -> _Signal | None:
    """K14: a green up bar, then a down bar closing at its OPEN or lower on
    volume at least comparable ("larger or close", the weakness side's milder
    wording) [Z]. Absorbing on significant volume; the quiet form tests.

    Its places are "after distribution signals, at the top, or as the end of a
    correction in a downtrend" [Z] — the end of a RISE — so the move into the
    pair must be one. Without that context, measured on stored GPW history, it
    matched one bar in fifty: any up day followed by a down day, including the
    ordinary first days of every pullback, where it would veto the very
    signals of strength the pullback is supposed to end with.
    """
    j = i - 1
    if j < 1:
        return None
    ctx = s.context(i)
    if ctx is None or not _rising(s, j, _CONTEXT):
        return None
    avg_v, _ = ctx
    if s.closes[j] <= s.opens[j] or not s.is_up_bar(j) or not s.is_down_bar(i):
        return None
    if s.closes[i] > s.opens[j] + _TBR_TOLERANCE * s.body(j):
        return None
    if s.volumes[j] <= 0 or s.volumes[i] < _TBR_VOL_EQUAL * s.volumes[j]:
        return None
    if s.volumes[i] < avg_v:
        return None
    return _Signal("Two Bar Reversal", _ABSORBING, j, i, s.lows[i], s.volumes[i])


# K10 Supply Coming In is deliberately NOT a veto. The course files it among the
# absorbing signals of weakness, but says of it in the same breath that it
# "rarely makes the top by itself" and "is not for taking positions — it is a
# concentration launcher" [Z, lesson 15]: supply arriving without a climax,
# which a healthy advance absorbs. Measured on stored history it was the most
# frequent bar within three sessions of a pullback's peak, so treating it as
# "supply at the peak" would have refused most pullbacks for a signal the course
# itself says does not end an advance. The course's own top-making sequence,
# Supply Coming In -> No Demand -> Upthrust, is still caught at its Upthrust.
_WEAKNESS: tuple[Callable[[_Series, int], _Signal | None], ...] = (
    _buying_climax,
    _end_of_rising_market,
    _trap_upmove,
    _no_result_from_effort,
    _upthrust,
    _two_bar_reversal_weak,
)


# ── Formations (compendium section 04) ────────────────────────────────────────


@dataclass(frozen=True)
class _Formation:
    """A completed bullish formation: its name, its bars, where lesson 3 puts the
    stop, and where the entry would be filled."""

    label: str
    first: int
    stop: float
    entry: float


def _hammer(s: _Series, i: int) -> _Formation | None:
    """A long lower shadow, a close near the high, a body at most 1/3 of the
    range, colour irrelevant, after a fall [Z]; a real shadow on top makes it a
    spinning top, not a hammer [Z]. Stop under the shadow."""
    ctx = s.context(i)
    if ctx is None or i < 3:
        return None
    rng = s.rng(i)
    if rng <= 0 or rng < _MIN_SPREAD_MULT * ctx[1]:
        return None
    cp = s.close_pos(i)
    if s.body(i) > _SMALL_BODY * rng or cp is None or cp < _HIGH_CLOSE:
        return None
    if s.upper_shadow(i) > _NEGLIGIBLE_SHADOW * rng:
        return None
    # "After a fall": the hammer reaches a low below the bars just before it [F].
    if s.lows[i] >= min(s.lows[i - 3 : i]):
        return None
    return _Formation("Hammer", i, s.lows[i], s.closes[i])


def _piercing(s: _Series, i: int) -> _Formation | None:
    """Candle 2 closes above 50% of candle 1's BODY — the body's middle, not the
    range's [Z]; a body not engulfed in full is a piercing, not an engulfing."""
    if i < 1:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    j = i - 1
    if s.closes[j] >= s.opens[j] or s.closes[i] <= s.opens[i]:
        return None
    if s.body(j) < _MIN_BODY_SPREADS * ctx[1]:
        return None
    if s.closes[i] <= (s.opens[j] + s.closes[j]) / 2:
        return None
    if s.opens[i] <= s.closes[j] and s.closes[i] >= s.opens[j]:
        return None  # an engulfing — reported as that instead
    return _Formation("Piercing Line", j, min(s.lows[j], s.lows[i]), s.closes[i])


def _morning_star(s: _Series, i: int) -> _Formation | None:
    """Three candles: a large down candle, a small middle candle below it, a
    large up candle [Z]. The stop goes under the LOWEST point of all three,
    shadows included [Z]."""
    if i < 2:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    a, b = i - 2, i - 1
    if s.closes[a] >= s.opens[a] or s.closes[i] <= s.opens[i]:
        return None
    body_a = s.body(a)
    if body_a < _LONG_BODY_SPREADS * ctx[1] or s.body(i) < _LONG_BODY_SPREADS * ctx[1]:
        return None
    if s.body(b) > _STAR_BODY_MAX * body_a:
        return None
    if max(s.opens[b], s.closes[b]) > s.closes[a]:
        return None  # the star must sit below candle 1's body
    return _Formation("Morning Star", a, min(s.lows[a : i + 1]), s.closes[i])


def _bullish_engulfing(s: _Series, i: int) -> _Formation | None:
    """The green body engulfs the red body IN FULL — bodies, not ranges [Z].
    Stop under the lower low of the two."""
    if i < 1:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    j = i - 1
    if s.closes[j] >= s.opens[j] or s.closes[i] <= s.opens[i]:
        return None
    if s.body(j) < _MIN_BODY_SPREADS * ctx[1]:
        return None
    if s.opens[i] > s.closes[j] or s.closes[i] < s.opens[j]:
        return None
    return _Formation("Bullish Engulfing", j, min(s.lows[j], s.lows[i]), s.closes[i])


def _inside_bar_break(s: _Series, i: int) -> _Formation | None:
    """Lesson 5's Inside Bar, long: candle 2 sits wholly inside candle 1's range
    (shadows included) and candle 3 breaks candle 1's HIGH [Z].

    "If the third candle does not break out, there is no formation" [Z] — so it
    is dated to the breakout bar. Entry is the stop order on the break of H1
    (the open, if the bar gapped above it); the stop goes under L1 [Z]. A
    breakout bar that also undercuts L1 is an outside bar, not this [F].
    """
    ctx = s.context(i)
    if i < 2 or ctx is None:
        return None
    mother = i - 1
    inside = 0
    while inside < _INSIDE_MAX and mother >= 1:
        if s.highs[mother] <= s.highs[mother - 1] and s.lows[mother] >= s.lows[mother - 1]:
            inside += 1
            mother -= 1
            continue
        break
    if inside == 0:
        return None
    if mother >= 1 and inside == _INSIDE_MAX and (
        s.highs[mother] <= s.highs[mother - 1] and s.lows[mother] >= s.lows[mother - 1]
    ):
        return None  # the run is longer than allowed — `mother` is still inside
    if s.rng(mother) < _MIN_SPREAD_MULT * ctx[1] or s.rng(i) <= 0:
        return None
    if s.highs[i] <= s.highs[mother] or s.lows[i] < s.lows[mother]:
        return None
    entry = max(s.highs[mother], s.opens[i])
    return _Formation("Inside Bar break", mother, s.lows[mother], entry)


# Longest-spanning first, so a bar completing two formations gets the fuller one
# and its wider stop — a tighter stop would inflate the R/R the 3:1 filter reads.
_FORMATIONS: tuple[Callable[[_Series, int], _Formation | None], ...] = (
    _inside_bar_break,
    _morning_star,
    _bullish_engulfing,
    _piercing,
    _hammer,
)


def _formation_at(s: _Series, i: int) -> _Formation | None:
    for detector in _FORMATIONS:
        found = detector(s, i)
        if found is not None:
            return found
    return None


# ── Waves ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Pivot:
    """A zigzag swing point: ``bar`` is where it is, ``confirmed`` the first bar
    on which it was knowable (price had left it by the reversal threshold)."""

    bar: int
    confirmed: int
    kind: str  # "H" | "L"


def _zigzag(s: _Series) -> list[_Pivot]:
    """Split the history into alternating up- and down-waves [F; threshold L].

    Causal: every pivot carries the bar it was confirmed on, so a reader at bar
    ``i`` uses only the pivots confirmed by then.
    """
    n = len(s)
    pivots: list[_Pivot] = []
    start = _SPREAD_MA
    if n <= start + 1:
        return pivots
    up: bool | None = None
    hi = lo = ext = start
    for i in range(start + 1, n):
        avg_sp = s.avg_spread[i]
        if avg_sp is None or avg_sp <= 0:
            continue
        thr = _WAVE_REVERSAL * avg_sp
        if up is None:
            if s.highs[i] > s.highs[hi]:
                hi = i
            if s.lows[i] < s.lows[lo]:
                lo = i
            if s.highs[hi] - s.lows[lo] >= thr:
                if hi > lo:
                    pivots.append(_Pivot(lo, i, "L"))
                    up, ext = True, hi
                else:
                    pivots.append(_Pivot(hi, i, "H"))
                    up, ext = False, lo
            continue
        if up:
            if s.highs[i] >= s.highs[ext]:
                ext = i
            elif s.highs[ext] - s.lows[i] >= thr:
                pivots.append(_Pivot(ext, i, "H"))
                up, ext = False, i
        else:
            if s.lows[i] <= s.lows[ext]:
                ext = i
            elif s.highs[i] - s.lows[ext] >= thr:
                pivots.append(_Pivot(ext, i, "L"))
                up, ext = True, i
    return pivots


# ── Weekly bars: the superior timeframe ───────────────────────────────────────


@dataclass(frozen=True)
class _Week:
    high: float
    low: float
    close: float


def _weeks(s: _Series) -> tuple[list[int], list[_Week]]:
    """ISO-week candles, and the week index of every daily bar."""
    week_of: list[int] = []
    weeks: list[_Week] = []
    key_prev: tuple[int, int] | None = None
    hi = lo = close = 0.0
    for i, d in enumerate(s.dates):
        iso = d.isocalendar()
        key = (iso.year, iso.week)
        if key != key_prev:
            if key_prev is not None:
                weeks.append(_Week(hi, lo, close))
            key_prev = key
            hi, lo = s.highs[i], s.lows[i]
        hi = max(hi, s.highs[i])
        lo = min(lo, s.lows[i])
        close = s.closes[i]
        week_of.append(len(weeks))
    if key_prev is not None:
        weeks.append(_Week(hi, lo, close))
    return week_of, weeks


def _weekly_trend(weeks: Sequence[_Week]) -> str:
    """'up' | 'down' | 'undecided' from completed weekly bars [F; window L].

    The course assesses the trend on the higher interval every day by a fixed
    procedure with three admissible results — up, down, or an undecided market
    (lesson 29) — but records the procedure only by its results. Read here as
    the plainest statement of trend: the last quarter made a HIGHER high AND a
    HIGHER low than the quarter before it (down: both lower). Anything else — a
    range expanding or contracting — is undecided, and undecided trades
    nothing: "brak pozycji jest pozycja".

    Two blocks, rather than weekly swing points, because a steady advance never
    prints a weekly swing low — every week's low is above the last — so a
    pivot-based reading called the cleanest uptrends "undecided". Measured on
    stored GPW history this reads 40% of sessions as up, 33% down and 27%
    undecided, which is what the course says to expect: the undecided market
    "happens as often as the other two". Three blocks, or weekly swing points,
    left 54-68% undecided.
    """
    if len(weeks) < 2 * _WEEKLY_HALF:
        return "undecided"
    older = weeks[-2 * _WEEKLY_HALF : -_WEEKLY_HALF]
    recent = weeks[-_WEEKLY_HALF:]
    high_o, low_o = max(w.high for w in older), min(w.low for w in older)
    high_r, low_r = max(w.high for w in recent), min(w.low for w in recent)
    if high_r > high_o and low_r > low_o:
        return "up"
    if high_r < high_o and low_r < low_o:
        return "down"
    return "undecided"


# ── The engine: memoised per-stock reads ──────────────────────────────────────


@dataclass(frozen=True)
class _Leg:
    """The last impulse up and the correction hanging off it, as of one bar."""

    origin: int
    peak: int
    halt: int

    def height(self, s: _Series) -> float:
        return max(0.0, s.highs[self.peak] - s.lows[self.origin])


class _Engine:
    """Every read of one stock, computed lazily and at most once.

    ``signals()`` sweeps a stock's whole history, and each bar's setup reads the
    same neighbouring signals as the next bar's, so the per-bar signal reads are
    memoised rather than recomputed for every bar that looks at them.
    """

    def __init__(self, bars: Sequence[StooqDailyQuote]) -> None:
        self.s = _Series.build(bars)
        self.pivots = _zigzag(self.s)
        self._pivot_confirms = [p.confirmed for p in self.pivots]
        self.week_of, self.weeks = _weeks(self.s)
        self._primary: dict[int, _Signal | None] = {}
        self._strength: dict[int, _Signal | None] = {}
        self._weakness: dict[int, _Signal | None] = {}
        self._trend: dict[int, str] = {}
        self._vol_char: dict[int, str] = {}
        self._legs: dict[int, _Leg | None] = {}
        self._places: dict[tuple[int, int, int, int], str | None] = {}
        self._wfo: dict[tuple[int, int, int, int], bool] = {}
        self._abc: dict[tuple[int, int, int, int], bool] = {}
        self._no_supply_peak: dict[tuple[int, int], bool] = {}
        self._corrections: dict[tuple[int, int, int, int], tuple[bool, str | None]] = {}
        self._sequences: dict[tuple[int, int, int, int], list[_Signal] | None] = {}
        self._assessments: dict[int, _Assessment | None] = {}

    def __len__(self) -> int:
        return len(self.s)

    # Signals

    def primary(self, i: int) -> _Signal | None:
        """The strongest climactic/absorbing-family signal of strength at ``i``.

        One bar carries one signal. When several match, the strongest CATEGORY
        wins (climactic, then absorbing, then testing — a low-volume Shakeout
        is only a test, and must not hide a Stopping Volume completing on the
        same bar), and within a category the order of ``_PRIMARY``.
        """
        if i not in self._primary:
            found = None
            if 0 <= i < len(self.s):
                matches = [sig for d in _PRIMARY if (sig := d(self.s, i)) is not None]
                if matches:
                    found = min(matches, key=lambda sig: _STAGE[sig.category])
            self._primary[i] = found
        return self._primary[i]

    def _test(self, i: int) -> _Signal | None:
        """K7 Test, dated at its confirming up bar.

        "It matters ONLY when there was accumulation or strong demand in these
        price ranges before. A test with no link to the left side of the chart
        carries no information" [Z] — the concentration launcher of lesson 21.
        So the tested bar's low must sit in the zone of an earlier climactic or
        absorbing signal of strength.
        """
        s = self.s
        j = i - 1
        if j < 1 or not _test_bar(s, j) or not s.is_up_bar(i):
            return None
        ctx = s.context(j)
        if ctx is None:
            return None
        zone = _ZONE_SPREADS * ctx[1]
        for d in range(j - 1, max(0, j - _TEST_CONTEXT_LOOKBACK) - 1, -1):
            earlier = self.primary(d)
            if (
                earlier is not None
                and earlier.category != _TESTING
                and earlier.bar < j
                and abs(s.lows[j] - earlier.low) <= zone
            ):
                return _Signal("Test", _TESTING, j, i, s.lows[j], s.volumes[j])
        return None

    def strength(self, i: int) -> _Signal | None:
        """The one signal of strength dated at bar ``i``, strongest first.

        A climactic or absorbing reading wins outright. Among testing readings
        the course's dedicated testing signals — Test, then No Supply — are
        named ahead of the quiet variants of a Shakeout or Two Bar Reversal on
        the same bars; the category, which is all a sequence reads, is the same.
        """
        if i not in self._strength:
            found = self.primary(i)
            if (found is None or found.category == _TESTING) and 0 <= i < len(self.s):
                found = self._test(i) or _no_supply(self.s, i) or found
            self._strength[i] = found
        return self._strength[i]

    def weakness(self, i: int) -> _Signal | None:
        """A STRONG (climactic or absorbing) signal of weakness at ``i``."""
        if i not in self._weakness:
            found = None
            if 0 <= i < len(self.s):
                for detector in _WEAKNESS:
                    found = detector(self.s, i)
                    if found is not None:
                        break
            self._weakness[i] = found
        return self._weakness[i]

    # Timeframe and background

    def weekly_trend(self, i: int) -> str:
        """The superior-scale trend as of bar ``i``, from COMPLETED weeks only —
        the week bar ``i`` sits in is still forming and would carry days after
        ``i`` into the read."""
        w = self.week_of[i]
        if w not in self._trend:
            self._trend[w] = _weekly_trend(self.weeks[max(0, w - 2 * _WEEKLY_HALF) : w])
        return self._trend[w]

    def pivots_until(self, i: int) -> list[_Pivot]:
        """The zigzag pivots knowable on bar ``i``."""
        return self.pivots[: bisect_right(self._pivot_confirms, i)]

    def volume_character(self, i: int) -> str:
        """Lesson 6: "bullish" | "bearish" | "unclear" on the playing scale.

        "Bullish volume increases on the moves up and decreases on the moves
        down" [Z], read over whole WAVES and compared by their typical volume per
        bar [F]: bullish when the median up-wave out-trades the median
        down-wave, bearish in the mirror case, unclear with too few waves.
        """
        if i in self._vol_char:
            return self._vol_char[i]
        s = self.s
        known = [p for p in self.pivots_until(i) if p.bar >= i - _CHARACTER_LOOKBACK]
        if not known:
            self._vol_char[i] = "unclear"
            return "unclear"
        up: list[float] = []
        down: list[float] = []
        ends = [*known, _Pivot(i, i, "H" if known[-1].kind == "L" else "L")]
        for a, b in zip(ends[:-1], ends[1:], strict=True):
            if b.bar <= a.bar:
                continue
            vols = s.volumes[a.bar + 1 : b.bar + 1]
            if not vols:
                continue
            mean = sum(vols) / len(vols)
            (up if a.kind == "L" else down).append(mean)
        if len(up) < 2 or len(down) < 2:
            self._vol_char[i] = "unclear"
            return "unclear"
        mu, md = _median(up), _median(down)
        if mu > md:
            res = "bullish"
        elif md > mu:
            res = "bearish"
        else:
            res = "unclear"
        self._vol_char[i] = res
        return res

    # The impulse and the place

    def leg(self, i: int) -> _Leg | None:
        """The impulse up that the pullback ending at bar ``i`` is retracing.

        The PEAK is "the top that started this pullback": the highest high of
        the last ``_MAX_CORRECTION`` sessions, old enough that a correction
        exists and never exceeded since. If that high sits at the window's left
        edge the market has been falling for longer than a pullback lasts, and
        there is no pullback to buy.

        The ORIGIN is the most recent zigzag swing low before the peak that the
        correction has not broken [L: "od dolka do szczytu", with no rule for
        which low]. In a staircase advance that is the start of the last leg —
        the impulse the pullback is correcting. If the pullback has already
        gone below it, that leg is undone and the retracement is measured on
        the larger swing from the swing low before it, which is how a chart
        reader re-anchors a failed leg. A swing low is a real turning point
        rather than wherever a lookback window happens to start.
        """
        if i in self._legs:
            return self._legs[i]
        s = self.s
        lo = i - _MAX_CORRECTION
        hi = i - _MIN_CORRECTION
        if lo < _IMPULSE_LOOKBACK:
            self._legs[i] = None
            return None
        peak = max(range(lo, hi + 1), key=lambda k: (s.highs[k], k))
        if peak == lo:
            self._legs[i] = None
            return None
        peak_high = s.highs[peak]
        if max(s.highs[peak + 1 : i + 1]) > peak_high:
            self._legs[i] = None
            return None
        halt = min(range(peak + 1, i + 1), key=lambda k: s.lows[k])
        halt_low = s.lows[halt]
        origin = next(
            (
                p.bar
                for p in reversed(self.pivots_until(i))
                if p.kind == "L"
                and peak - _IMPULSE_LOOKBACK <= p.bar < peak
                and s.lows[p.bar] < halt_low
            ),
            None,
        )
        if origin is None:
            self._legs[i] = None
            return None
        origin_low = s.lows[origin]
        if origin_low <= 0 or (peak_high - origin_low) / origin_low < _MIN_IMPULSE_PCT:
            self._legs[i] = None
            return None
        res_leg = _Leg(origin=origin, peak=peak, halt=halt)
        self._legs[i] = res_leg
        return res_leg

    def zone_top(self, leg: _Leg, i: int) -> float | None:
        """The top of the price zone the correction ended in."""
        ctx = self.s.context(i)
        if ctx is None:
            return None
        return self.s.lows[leg.halt] + _ZONE_SPREADS * ctx[1]

    def geometry(self, leg: _Leg) -> str | None:
        """'Zatrzymanie na geometrii — 38,2 / 41,4 / 50 / 61,8' [Z]: the level
        the correction's lowest low halted on, or the golden pocket zone."""
        s = self.s
        h = leg.height(s)
        if h <= 0:
            return None
        retr = (s.highs[leg.peak] - s.lows[leg.halt]) / h
        for level in _GEOMETRY_LEVELS:
            if abs(retr - level) <= _GEOMETRY_ZONE:
                return f"{level * 100:.1f}%".replace(".0%", "%")
        if 0.35 <= retr <= 0.65:
            return f"{retr * 100:.0f}%"
        return None

    def wfo(self, leg: _Leg, i: int) -> bool:
        """The bullish WFO, lessons 25-26 — all eight necessary conditions [Z].

        On two lows of the correction, D1 then D2 (D2 its lowest low):
          1. both are visible lows (D1 a swing low, D2 the correction's low);
          2. HIGH volume at D1 itself, or right beside it — not "on the way";
          3. a bounce between them;
          4. D2 lower than D1, by at least one tick;
          5. V(D2) < V(D1);
          6. V(D2) above EVERY bar between them — "the condition easiest to
             miss": if any bar in between traded more, it is not a WFO;
          7. a recognisable VSA signal of strength at D2;
          8. a price reaction after it.
        """
        key = (leg.origin, leg.peak, leg.halt, i)
        if key in self._wfo:
            return self._wfo[key]
        s = self.s
        d2 = leg.halt
        if d2 >= i or max(s.closes[d2 + 1 : i + 1]) <= s.highs[d2]:
            self._wfo[key] = False
            return False  # 8: no reaction yet
        signal_at_d2 = False
        for j in (d2, d2 + 1):
            sig = self.strength(j)
            if sig is not None and sig.start <= d2 <= sig.bar:
                signal_at_d2 = True
        if not signal_at_d2:
            self._wfo[key] = False
            return False  # 7
        for d1 in range(d2 - _WFO_MIN_GAP, leg.peak, -1):
            if d1 - _PIVOT_K <= leg.peak or s.lows[d1] <= 0:
                continue
            if s.lows[d1] != min(s.lows[d1 - _PIVOT_K : d1 + _PIVOT_K + 1]):
                continue  # 1
            if s.lows[d2] >= s.lows[d1]:
                continue  # 4
            vol_bar = max(range(d1 - 1, d1 + 2), key=lambda k: s.volumes[k])
            ctx = s.context(vol_bar)
            if ctx is None or s.volumes[vol_bar] < _HIGH_VOL * ctx[0]:
                continue  # 2
            if s.volumes[d2] >= s.volumes[vol_bar]:
                continue  # 5
            between = s.volumes[max(d1, vol_bar) + 1 : d2]
            if not between or s.volumes[d2] <= max(between):
                continue  # 6
            bounce = max(s.highs[d1 + 1 : d2])
            if (bounce - s.lows[d1]) / s.lows[d1] < _WFO_MIN_BOUNCE:
                continue  # 3
            self._wfo[key] = True
            return True
        self._wfo[key] = False
        return False

    def abc(self, leg: _Leg, i: int) -> bool:
        """The end of an ABC correction — the compendium's proposed definition.

        The course lists it as a route to a WM and never defines it; the
        compendium suggests "a three-wave pullback whose C wave ends on
        corrective volume" [L], and that is what runs: between the peak and
        the correction's low the zigzag shows exactly one swing low (the end of
        A) and one swing high (the end of B), the low C makes lies below A's,
        and C trades on less volume per bar than the impulse did.
        """
        key = (leg.origin, leg.peak, leg.halt, i)
        if key in self._abc:
            return self._abc[key]
        s = self.s
        inner = [p for p in self.pivots_until(i) if leg.peak < p.bar < leg.halt]
        if [p.kind for p in inner] != ["L", "H"]:
            self._abc[key] = False
            return False
        a_end, b_end = inner
        if s.lows[leg.halt] >= s.lows[a_end.bar]:
            self._abc[key] = False
            return False
        c_vols = s.volumes[b_end.bar + 1 : leg.halt + 1]
        impulse_vols = s.volumes[leg.origin + 1 : leg.peak + 1]
        if not c_vols or not impulse_vols:
            self._abc[key] = False
            return False
        res = sum(c_vols) / len(c_vols) < sum(impulse_vols) / len(impulse_vols)
        self._abc[key] = res
        return res

    def place(self, leg: _Leg, i: int) -> str | None:
        """Lesson 29's WM — any ONE of its three routes is enough [Z]."""
        key = (leg.origin, leg.peak, leg.halt, i)
        if key in self._places:
            return self._places[key]
        level = self.geometry(leg)
        if level is not None:
            self._places[key] = level
            return level
        if self.wfo(leg, i):
            self._places[key] = "WFO"
            return "WFO"
        if self.abc(leg, i):
            self._places[key] = "ABC"
            return "ABC"
        self._places[key] = None
        return None

    def no_supply_at_peak(self, leg: _Leg, i: int) -> bool:
        """'BRAK PODAZY W SZCZYCIE' [Z]: no strong signal of supply at the top
        that started the pullback — "we do not play against them".

        Any climactic or absorbing signal of weakness within a few bars of the
        peak (Buying Climax, End of a Rising Market, Trap Upmove, No Result From
        Effort, Upthrust, Two Bar Reversal) means the advance ended in
        distribution. Supply Coming In alone does not — see ``_WEAKNESS``. Fails
        CLOSED when the peak is too early in the history to audit.
        """
        key = (leg.peak, i)
        if key in self._no_supply_peak:
            return self._no_supply_peak[key]
        start = leg.peak - _PEAK_BACK
        if start < _ULTRA_WINDOW:
            self._no_supply_peak[key] = False
            return False
        end = min(i, leg.peak + _PEAK_FWD)
        res = all(self.weakness(j) is None for j in range(start, end + 1))
        self._no_supply_peak[key] = res
        return res

    def correction(self, leg: _Leg, i: int) -> tuple[bool, str | None]:
        """Lesson 27: (corrective approach?, the accent that ended it or None).

        In Scenariusz 5, the pullback approach to WM must run on corrective volume
        (lower than the impulse volume and fading towards the low) [Z, F]. The correction
        can end in an ACCENT (one sharp move on raised volume: Stopping Volume,
        Shakeout, Two Bar Reversal, or a Hammer on elevated volume) [Z] or as a classic
        correction on systematically expiring volume (Test, No Supply, or quiet Hammer) [Z, L].
        """
        key = (leg.origin, leg.peak, leg.halt, i)
        if key in self._corrections:
            return self._corrections[key]
        s = self.s
        top = self.zone_top(leg, i)
        impulse = s.volumes[leg.origin + 1 : leg.peak + 1]
        if top is None or not impulse:
            self._corrections[key] = (False, None)
            return False, None
        impulse_level = _median(impulse)
        if impulse_level <= 0:
            self._corrections[key] = (False, None)
            return False, None

        accent: str | None = None
        for j in range(leg.peak + 1, i + 1):
            sig = self.strength(j)
            label: str | None = None
            first, effort = j, 0.0
            if (
                sig is not None
                and sig.category == _ABSORBING
                and sig.label in ("Stopping Volume", "Shakeout", "Two Bar Reversal")
                and sig.low <= top
            ):
                label, first = sig.label, sig.start
                effort = max(s.volumes[sig.start : sig.bar + 1])
            elif s.lows[j] <= top and _hammer(s, j) is not None:
                label, first, effort = "Hammer", j, s.volumes[j]

            if label is None:
                continue
            approach = s.volumes[leg.peak + 1 : first]
            med_app = _median(approach) if approach else 0.0
            if med_app > 0 and effort >= _ACCENT_MULT * med_app:
                accent = label
                break

        pullback_vols = s.volumes[leg.peak + 1 : i + 1]
        med_pb = _median(pullback_vols) if pullback_vols else 0.0
        if not pullback_vols or med_pb <= 0:
            res_corr = (False, accent)
            self._corrections[key] = res_corr
            return res_corr

        quiet = med_pb <= _CORRECTIVE_RATIO * impulse_level
        half = len(pullback_vols) // 2
        fading = (
            len(pullback_vols) >= _MIN_APPROACH
            and _median(pullback_vols[half:]) <= _median(pullback_vols[:half])
        )

        is_corrective = quiet or fading or (accent is not None)
        res_corr = (is_corrective, accent)
        self._corrections[key] = res_corr
        return res_corr

    def sequence(self, leg: _Leg, i: int) -> list[_Signal] | None:
        """Lessons 23-24: three signals of strength that CLOSE a sequence.

        "Three signals following one another, all from ONE side, in the same
        price zone, with no strong opposite signal between them" [Z]. The order
        is by category, not by name ("Stopping Volume -> Stopping Volume -> Test
        is a valid sequence"): climactic or absorbing first, testing last, never
        backwards — a sequence cannot open with a test, "a test with nothing
        before it does not stop the market" — and consecutive tests each on
        lower volume than the last [Z, lesson 13]. The one sequence the course
        closes differently, "accumulation or absorption -> test -> a Shakeout on
        large volume", is allowed as drawn [F: the general order rule is the
        compiler's reading of the course's four examples]. A fourth signal
        after a closed sequence is fine.
        """
        key = (leg.origin, leg.peak, leg.halt, i)
        if key in self._sequences:
            return self._sequences[key]
        top = self.zone_top(leg, i)
        if top is None:
            self._sequences[key] = None
            return None
        last_weak = max(
            (j for j in range(leg.peak + 1, i + 1) if self.weakness(j) is not None),
            default=leg.peak,
        )
        sigs: list[_Signal] = []
        for j in range(last_weak + 1, i + 1):
            sig = self.strength(j)
            if sig is not None and sig.start > last_weak and sig.low <= top:
                sigs.append(sig)
        # Newest closing signal first, so the sequence reported is the latest.
        for c in range(len(sigs) - 1, _SEQUENCE_LEN - 2, -1):
            for b in range(c - 1, 0, -1):
                for a in range(b - 1, -1, -1):
                    if _valid_sequence(sigs[a], sigs[b], sigs[c]):
                        seq_res = [sigs[a], sigs[b], sigs[c]]
                        self._sequences[key] = seq_res
                        return seq_res
        self._sequences[key] = None
        return None

    def confirming_signal(self, formation: _Formation, i: int, top: float) -> _Signal | None:
        """'FORMACJA SWIECOWA POTWIERDZONA SYGNALEM VSA' [Z]: a signal of
        strength at the low, on the formation's own bars or just before them.

        A Hammer with no such signal is still accepted on its own volume (the
        2026-09-24 relaxation). It is labelled by that volume — "high volume"
        or "low volume" — and never as a Shakeout or Test: those detectors
        have just looked at this bar and said no, so naming one here put a
        signal on the chart and in the detail that the method had rejected.
        """
        for j in range(i, max(0, formation.first - _CONFIRM_WINDOW) - 1, -1):
            sig = self.strength(j)
            if sig is not None and sig.low <= top:
                return sig
        if formation.label == "Hammer":
            ctx = self.s.context(i)
            if ctx is not None:
                avg_v, _ = ctx
                rng = self.s.rng(i)
                vol, low = self.s.volumes[i], self.s.lows[i]
                if rng > 0 and vol >= avg_v:
                    return _Signal("high volume", _ABSORBING, i, i, low, vol)
                elif rng > 0 and self.s.lower_shadow(i) >= _SHADOW * rng and vol > 0:
                    return _Signal("low volume", _TESTING, i, i, low, vol)
        return None


def _valid_sequence(x: _Signal, y: _Signal, z: _Signal) -> bool:
    sx, sy, sz = _STAGE[x.category], _STAGE[y.category], _STAGE[z.category]
    if sx == _STAGE[_TESTING]:
        return False
    if sz == _STAGE[_TESTING]:
        if not sx <= sy <= sz:
            return False
        return sy != _STAGE[_TESTING] or z.volume < y.volume
    # "akumulacyjny lub zbierajacy -> testujacy -> Shakeout na duzym wolumenie"
    return sy == _STAGE[_TESTING] and z.label == "Shakeout" and z.category == _ABSORBING


# ── The complete setup ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Assessment:
    """Every layer's verdict on a bar where a formation completed at the low.

    The pattern itself — a candle formation at the correction's low, confirmed
    by a VSA signal of strength — is what makes a bar worth assessing at all.
    ``missing`` then names each layer of the loop that did not hold, in the
    loop's order, and is empty exactly when the setup fired.
    """

    formation: str
    signal: str
    place: str | None
    rr: float
    sequence: list[_Signal] | None = None
    missing: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.formation} + {self.signal}"

    @property
    def fired(self) -> bool:
        return not self.missing


def _assess(eng: _Engine, i: int) -> _Assessment | None:
    """Scenario 5 (long) through the seven-layer loop, on bar ``i``.

    ``None`` when there is no pattern to assess: no formation completed here,
    no live pullback, the formation is not at the low, or no signal of strength
    confirms it. Otherwise every layer is judged, none cutting the others short,
    so a setup that fails can say exactly why — the course's own advice that a
    script should report candidates with their R/R and let a human decide.
    """
    if i in eng._assessments:
        return eng._assessments[i]
    s = eng.s
    formation = _formation_at(s, i)
    if formation is None:
        eng._assessments[i] = None
        return None
    leg = eng.leg(i)
    if leg is None:
        eng._assessments[i] = None
        return None
    # Layer 5 — the formation AT the low, confirmed by a VSA signal, together.
    top = eng.zone_top(leg, i)
    if top is None or min(s.lows[formation.first : i + 1]) > top:
        eng._assessments[i] = None
        return None
    signal = eng.confirming_signal(formation, i, top)
    if signal is None:
        eng._assessments[i] = None
        return None

    missing: list[str] = []
    # Layers 0-1 — the superior-scale trend and the volume character.
    if eng.weekly_trend(i) != "up":
        missing.append("weekly trend not up")
    if eng.volume_character(i) == "bearish":
        missing.append("bearish volume")
    # Layer 2 — the place, and no supply at the peak.
    place = eng.place(leg, i)
    if place is None:
        missing.append("no WM")
    if not eng.no_supply_at_peak(leg, i):
        missing.append("supply at the peak")
    # Layer 4 — corrective volume approach.
    corrective, _ = eng.correction(leg, i)
    if not corrective:
        missing.append("volume not corrective")
    # Layer 6 — the arithmetic filter, "the only condition in the whole course
    # that needs no interpretation". Target: this scale's peak.
    risk = formation.entry - formation.stop
    reward = s.highs[leg.peak] - formation.entry
    rr = reward / risk if risk > 1e-4 and reward > 0 else 0.0
    if rr < _MIN_RR:
        missing.append(f"R/R {rr:.1f}:1")

    # Sequence as quality booster
    seq = eng.sequence(leg, i)

    res = _Assessment(
        formation=formation.label,
        signal=signal.label,
        place=place,
        rr=rr,
        sequence=seq,
        missing=tuple(missing),
    )
    eng._assessments[i] = res
    return res


def _setup_at(eng: _Engine, i: int) -> _Assessment | None:
    """The complete setup on bar ``i`` — every layer holding — or None."""
    found = _assess(eng, i)
    return found if found is not None and found.fired else None


# The same reasons, shortened for a chart marker, where the label sits next to
# a candle and every character costs space. The R/R reason carries its own
# number and passes through unchanged.
_SHORT_MISSING = {
    "weekly trend not up": "weekly trend",
    "bearish volume": "bearish volume",
    "no WM": "no place",
    "supply at the peak": "supply at peak",
    "volume not corrective": "not corrective",
    "no accent": "no accent",
    "no 3-signal sequence": "no sequence",
}


def _layers(eng: _Engine, i: int, days_since: int) -> tuple[int, _Leg | None]:
    """How many of the loop's seven layers stand on bar ``i`` (0-7)."""
    leg = eng.leg(i)
    checks = [
        eng.weekly_trend(i) == "up",
        eng.volume_character(i) != "bearish",
    ]
    if leg is None:
        checks += [False, False, False, False, False]
    else:
        corrective, _ = eng.correction(leg, i)
        checks += [
            eng.place(leg, i) is not None,
            eng.no_supply_at_peak(leg, i),
            corrective,
            days_since <= _RECENT_FIRED,
            eng.sequence(leg, i) is not None or eng.wfo(leg, i),
        ]
    return sum(1 for ok in checks if ok), leg


@register_method
class Vsa3(TradingMethod):
    id = "vsa3"
    order = 60
    name = "VSA V3"
    description = (
        "Rafal Glinicki's VSA course read from the transcripts of all 34 of its "
        "recordings, run as the course's own seven-step decision loop for its "
        "one complete long setup (\"Scenario 5\"). It buys a pullback only when "
        "everything lines up: the weekly chart is in an uptrend (the last "
        "quarter made a higher high and a higher low than the one before); "
        "daily volume is not bearish (up-waves trade at least "
        "as much as down-waves); the pullback stopped at a measured place — a "
        "38.2 / 41.4 / 50 / 61.8 retracement, a volume divergence at the low "
        "(WFO) or the end of an ABC correction; the peak it fell from shows no "
        "selling; the pullback ran on fading, lighter volume; a bullish candle formation "
        "completes at the low, confirmed by a VSA signal of strength (Stopping Volume, "
        "Shakeout, Two Bar Reversal, No Supply, Test) — a Hammer may instead stand on "
        "its own volume; and the trade offers at least 3:1 "
        "to the old peak with the stop under the formation. A 3-signal sequence or WFO "
        "divergence serves as a high-confidence booster. The score says how many of the "
        "seven steps stand today. Long-only."
    )
    source = (
        "Rafal Glinicki — \"Analiza ceny i wolumenu\" (XTB Investing Masters, "
        "30 lessons) and his 2018 VSA course (4 lessons), from the transcripts "
        "of all 34 recordings: lesson 29 \"Scenariusz 5\" run through the "
        "course's decision loop, with lessons 1-28"
    )
    source_url = "https://www.xtb.com/pl/edukacja/investing-masters"

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,  # the course's own thresholds; unused
        *,
        rs_rank: float | None = None,  # cross-sectional; not used by this method
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")

        eng = _Engine(bars)
        last = len(bars) - 1
        last_date = bars[last].date

        days_since = NEVER_FIRED
        setup: _Assessment | None = None
        # The most recent pattern that came close but was not taken, if it is
        # newer than the last complete setup — so the reader sees that the
        # method saw it, and why it said no.
        near: _Assessment | None = None
        near_days = NEVER_FIRED
        for i in range(last, max(_MIN_BARS - 1, last - _RECENCY_SCAN) - 1, -1):
            found = _assess(eng, i)
            if found is None:
                continue
            age = (last_date - bars[i].date).days
            if found.fired:
                days_since, setup = age, found
                break
            if (
                near is None
                and len(found.missing) <= _NEAR_MISS_LAYERS
                and age <= _RECENT_FIRED
            ):
                near, near_days = found, age

        passed, leg = _layers(eng, last, days_since)
        fired = days_since == 0
        if setup is not None and fired:
            seq_info = " (3-sig seq)" if setup.sequence else ""
            detail = f"{setup.label} @ {setup.place}{seq_info}, R/R {setup.rr:.1f}:1"
        elif near is not None and (setup is None or near_days < days_since):
            when = "today" if near_days == 0 else f"{near_days}d ago"
            detail = f"{near.label} {when}, not taken: {', '.join(near.missing)}"
            if near_days == 0:
                passed = _TOTAL_LAYERS - len(near.missing)
        elif setup is not None:
            detail = f"{setup.label} {days_since}d ago"
        elif leg is None:
            detail = "No pullback setup"
        else:
            detail = f"{passed}/{_TOTAL_LAYERS} layers"

        score = round(passed / _TOTAL_LAYERS * 100)
        if fired and setup is not None:
            score = 100 if (setup.sequence or (leg and eng.wfo(leg, last))) else 90

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
        """Chart markers, oldest first: complete setups, and near misses.

        A complete setup is a ``"Bullish"`` marker — a trade, and the only kind
        the back-test judges. A pattern at the low that missed at most
        ``_NEAR_MISS_LAYERS`` layers is a ``"Watch"`` marker labelled with what
        was missing, so the chart shows that the method DID see the pattern and
        says why it passed — the course's "report candidates, let a human
        decide". Without it a reader sees an empty chart and concludes the
        method is blind to a textbook hammer, which is how this was found.
        """
        if len(bars) < _MIN_BARS:
            return []
        eng = _Engine(bars)
        out: list[MethodSignal] = []
        for i in range(_MIN_BARS - 1, len(bars)):
            found = _assess(eng, i)
            if found is None:
                continue
            if found.fired:
                out.append(MethodSignal(date=bars[i].date, label=found.label, type="Bullish"))
            elif len(found.missing) <= _NEAR_MISS_LAYERS:
                reasons = ", ".join(_SHORT_MISSING.get(m, m) for m in found.missing)
                out.append(
                    MethodSignal(
                        date=bars[i].date, label=f"{found.label} · {reasons}", type="Watch"
                    )
                )
        return out
