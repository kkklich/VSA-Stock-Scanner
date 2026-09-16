"""VSA 2 — Glinicki's 30-lesson VSA course, mechanised as its own "Scenario 5".

Source: *Investing Masters — VSA* by Rafal Glinicki (XTB Polska, **30 lessons**,
13 h 32 min), plus the same author's four 2018 XTB/VSA-Trader webinars (8 h
41 min). This is a different, much longer course than the five-lesson one behind
the app's existing ``glinicki`` method ("VSA V1"), and it teaches a different
thing: V1 is a catalogue of candle formations gated by market phase, while the
long course spends its last nine lessons building **one complete trade
setup** — "SCENARIUSZ 5 - (long)", the only place in either course where the
author writes the entry conditions down as text and puts a number on
reward-to-risk. That setup is this method.

The slide (lesson 29, the one the whole course converges on) reads, verbatim:

    WAZNE MIEJSCE (WM)                      | IMPORTANT PLACE (WM)
      * Koniec korekty ABC                  |   * end of an ABC correction
      * WFO                                 |   * volumetric reversal formation
      * Zatrzymanie na geometrii -          |   * a halt on the geometry -
        38,2; 41,4; 50 ; 61,8               |     38.2 / 41.4 / 50 / 61.8
                                            |
    WARUNKI DOJSCIA DO SCENARIUSZA:         | CONDITIONS TO REACH THE SETUP:
      * BRAK PODAZY W SZCZYCIE              |   * no supply at the peak
      * WOLUMEN KOREKCYJNY                  |   * corrective volume
      * FORMACJA SWIECOWA POTWIERDZONA      |   * a candle formation CONFIRMED
        SYGNALEM VSA                        |     by a VSA signal
      * POTENCJALNY R/R MIN 3:1             |   * potential R/R at least 3:1

so a firing here means all of the following held on the same bar, which is why
it fires rarely and only on a complete setup:

    1. PLACE (WM). Price came back into a *measured* place, not a place judged
       by eye: either a halt inside one of the course's four retracement bands
       of the last impulse up (38.2 / 41.4 / 50 / 61.8 — lesson 22, "VSA
       signals as confirmation of market geometry"), or a bullish WFO
       (lesson 26: a lower price low on a LOWER volume low than the previous
       one — a divergence measured on volume instead of an oscillator).
    2. NO SUPPLY AT THE PEAK. The top the pullback started from shows no
       selling footprint — no wide down-bar on high volume, no upthrust. If
       supply came in up there, the advance is over and the dip is not a
       correction (lessons 15 and 20, read as an absence — the course's own
       law of cause and effect: "the ABSENCE of expected activity is also a
       cause").
    3. CORRECTIVE VOLUME. The pullback is quieter than the impulse and its
       volume systematically dries up (lesson 27's "classic correction on
       expiring volume"), or else it ended in one violent shakeout on raised
       volume — the course's second, explicitly allowed type of correction.
    4. FORMATION *AND* SIGNAL. A bullish candle formation from lessons 3-5
       (Hammer, Piercing Line, Morning Star, Bullish Engulfing, or a break out
       of an Inside Bar) completed here, AND one of the lesson 8-13 signals of
       strength (Bag Holding, Selling Climax, Stopping Volume, Shakeout, Two
       Bar Reversal, No Supply, Test) sits on or just before it. The slide's
       word is POTWIERDZONA — *confirmed* — so these are not alternatives:
       the place justifies the formation and the VSA signal justifies the
       formation, all three or nothing.
    5. R/R >= 3:1, measured to the peak the correction fell from, with the stop
       under the formation's low. This is the course's only purely
       mathematical filter and it rejects a perfect read of the market on
       arithmetic alone: lesson 28 derives the 3:1 from its own profitability
       simulation (20 trades at 30% hit rate = +6% of capital; break-even at
       25%), which is why the number is 3 and not 2.

WHAT THIS ADDS OVER "VSA V1" (``glinicki``). The two share an author and
therefore a candle vocabulary, and both are long-only, but they select on
different things and will rarely fire together:

    V1 (5 lessons)   phase (accumulation / markup) -> support zone drawn from
                     prior lows -> one of six candle formations -> volume vs
                     the 20-day average.
    V2 (30 lessons)  a *measured* place (Fibonacci retracement of the last
                     impulse, or a volume divergence at the low) -> the peak
                     must be free of supply -> the pullback's volume must
                     expire -> a candle formation *plus* a named VSA signal
                     -> and the trade must still offer 3:1.

V2 is therefore a pullback-continuation method with a hard arithmetic filter,
where V1 is a reversal-formation method. The R/R gate in particular has no
counterpart anywhere else in this app: a stock can pass every reading of the
market here and still be rejected for sitting too close to its target.

PROVENANCE, and it is worth being exact about it. The rules below come from a
written compendium of the two courses assembled from their image layer
(slide-by-slide, with second-level timestamps) — only lesson 1 of the 30 has a
transcript, and none of the four webinars do. The compendium marks every rule
with its status, and that mapping is honoured here:

    [Z] written verbatim on a slide. All five thresholds this method takes
        from the course are of this kind: the close-position 30/70 split, the
        "pink volume" rule (V_t < V_t-1 AND V_t < V_t-2, the indicator setting
        the course puts on screen), the 50%-of-the-body rule for a Piercing
        Line, the four retracement levels, and R/R 3:1.
    [R] read off a hand-drawn slide carrying no text. The fourteen signals of
        lessons 8-20 are all of this kind — the course never writes a single
        entry rule or stop for any of them.
    [L] a gap the course leaves open on purpose: it says outright that VSA is
        a filter for your own decision process, not a mechanical generator, and
        it never puts a number on "wide spread", "narrow range", "much lower
        volume" or "close to". Every such constant below is marked and is a
        calibration choice, not a claim about the source.

Two parts of the setup are deliberately NOT implemented, rather than guessed:

    * "End of an ABC correction", the third alternative route to a WM. The
      course names it as a condition and then never defines an ABC correction
      anywhere in 13 hours — the compendium flags it as its most conspicuous
      gap. Encoding a guess would put an invented rule behind the author's
      name, so the two defined routes (geometry, WFO) are the ones that run.
    * The sequence requirement (lessons 23-24's SA -> SZP -> ST, and the 2018
      series' more concrete A -> Stop -> T). The course never says which of
      its fourteen signals belong to which of its three categories, so a
      mechanical "the sequence completed" gate would be mine, not the
      author's. Instead the one form the material *does* pin down — lesson
      21's testing process, "A SUCCESSFUL TEST IS ONE OF THE STRONGEST TOOLS
      IN VSA": a high-volume low, a bounce, then a return to it on much lower
      volume — is detected and scored, not gated.

The ``score`` (0-100) rates how much of the setup currently stands, so a stock
sitting in a good place with a quiet pullback scores well a few days before the
formation completes, and a stock in free fall scores near zero and never leans
bullish in the analytics summary.

MEASURED, on 292 stored GPW tickers / 588 ticker-years of stored bars
(2026-09-14, after the source-fidelity pass described under CORRECTIONS below).
The setup fires **0.20 times per ticker-year** — once every five years per
stock, or once every few sessions somewhere in the universe — and 59 tickers
produced at least one. That is more than ten times rarer than the five-lesson
V1 method, which is the intended consequence of demanding six conditions at
once rather than a defect. The funnel, counted per completed candle formation,
says which condition does the work:

    27764  a bullish candle formation completed
    20056  ...with a live pullback off a measured impulse behind it
     5761  ...in a WM (geometry band or WFO)
     3083  ...with no supply at the peak
      887  ...on corrective volume
      551  ...confirmed by a VSA signal of strength
      116  ...still offering 3:1  <- the course's arithmetic filter cuts 79%

The last line is worth reading twice: four out of five setups that pass every
reading of the market are rejected on arithmetic alone. That is exactly what
lesson 29 asks for ("a mathematical filter at the end ... it rejects trades
regardless of the quality of the market read") and it is the single most
binding rule in the method.

BACK-TESTED, on the same stored history, through the app's own generic gate
(``GET /api/stocks/methods/vsa2/backtest``), which judges every firing's forward
return against that stock's own median move over the same span:

    horizon   judged   beat baseline   avg edge   reward/risk   gate
     5         68          41.2%       +0.47 pp      1.82       fail
    10         66          47.0%       +0.87 pp      1.74       fail
    20         63          52.4%       +2.92 pp      2.35       PASS
    30         63          55.6%       +5.27 pp      2.53       STRONG

The edge grows monotonically with the horizon, which is what the setup itself
predicts: its target is the peak the correction fell from, typically 5-15% away,
and price needs weeks rather than days to travel there. Judged at the
endpoint's default ten sessions the trade is still open, so it fails; judged
over twenty or thirty it passes, and at thirty it earns the gate's top grade.
For comparison, on the identical gate and universe every other method in the app
fails at every horizon (V1 +1.25 pp / 48.1% at thirty sessions, VSA rating
+1.21 pp / 44.4%, Volume Breakout +0.50 pp / 44.7%, Minervini a NEGATIVE
-0.34 pp), which makes this the only shipped method that clears the gate at all.

Two caveats belong with those numbers. The gate's pass condition is a HIT RATE
over 50%, which sits awkwardly with a method built on 3:1 payoffs — a setup
winning 40% of the time at 3:1 is profitable and would still be marked "fail".
And 63 judged firings is a thin sample on one exchange over the stored window
(the gate itself calls anything under 30 "insufficient", so this clears that
bar but not by much), so "passes" here means "did not fail its first honest
test", not "proven". The sample HALVED in the fidelity pass below: the numbers
are better because the setups are fewer and cleaner, which is the trade this
method is supposed to make, but it is a trade.

CORRECTIONS, 2026-09-14. A source-fidelity and correctness audit against the
compendium found four rules that did not say what the course says, and fixing
them roughly doubled the measured edge while halving the firings:

  * no BUYING CLIMAX test at the peak (lesson 14's K9). 19% of the firings
    this method used to produce were pullbacks bought out of a climactic top —
    the single situation "BRAK PODAZY W SZCZYCIE" exists to refuse, and one a
    climax slips through because it arrives on a big UP bar, invisible to the
    wide-down-bar and upthrust tests. See ``_no_supply_at_peak``.
  * the WFO compared its second low against local lows from inside the
    IMPULSE, not the correction, so the whole rally could stand in for the
    small bounce lesson 26 draws between the two lows. See ``_bullish_wfo``.
  * the Two Bar Reversal carried no volume condition at all, though lesson 11
    draws one — which made it a pure price shape that duplicated a Bullish
    Engulfing, letting one candle be both the formation AND the VSA signal that
    is supposed to confirm it. See ``_two_bar_reversal``.
  * zero-volume bars satisfied "corrective volume" perfectly, so a trading
    HALT inside the pullback read as the course's textbook quiet correction.
    See ``_corrective_volume``.

Also corrected: lesson 3's per-formation stop (the Morning Star's goes under
the MIDDLE candle, not the lowest of the three — ``_formation_stop``); the
formation search now tries the longest-spanning shapes first, so a bar that
completes two does not get the tighter stop and the inflated R/R that follows;
and ``_stopping_volume`` judged its down bar against an average containing that
same bar.

KNOWN SCOPE: like every other method here, this reproduces the source's own
thresholds (Glinicki teaches on intraday FX and index charts; VSA is
interval-agnostic and the course says so) rather than GPW-tuned ones, and the
gaps above are filled with calibration constants measured against stored GPW
history. It must be proven on that history via
``GET /api/stocks/methods/vsa2/backtest`` before its score guides real money.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    register_method,
)
from app.analysis.vsa import VsaConfig
from app.models import StooqDailyQuote

# ── Measurement layer (compendium part A) ─────────────────────────────────────
# Rolling reference windows. The course never gives one ("always by comparison
# with the bars to the left" [L]); 20 sessions is the average the course itself
# puts on screen as its one required indicator.
_VOL_MA = 20
_SPREAD_MA = 20
# Close position [Z, lesson 2 of the 2018 series, and lesson 1 slide 12 of the
# long course]: the course splits a bar's height 30/70 — an "up close" sits in
# the top 30%, a "down close" in the bottom 30%. Only the down half is used
# here (the bearish footprints at the peak); the up half of the same threshold
# is named by ``_TEST_CLOSE_POS``, which sits just under it.
_DOWN_CLOSE = 0.30
# "Pink volume" [Z]: the xStation indicator option the course shows on screen,
# "volume lower than the previous [2] bars". N = 2 in every recording it
# appears in. This is the ONE volume rule in either course that needs no
# calibration, and it is what makes No Supply computable.
_PINK_N = 2

# Volume classes against the 20-session average. The course's scale (low /
# medium / high / ultra high) carries no numbers at all [L]; these match the
# multipliers V1 already uses, so the two engines speak one language.
_ULTRA_VOL_MULT = 2.0
_HIGH_VOL_MULT = 1.5
_ELEVATED_VOL_MULT = 1.2
# Spread classes, in units of the 20-session average spread [L].
_WIDE_SPREAD_MULT = 1.2
_NARROW_SPREAD_MULT = 0.7
# A formation bar must be a real session's range, not a sliver. Proportion-based
# definitions (a Hammer is "small body, long lower shadow") are scale-free, so
# without a floor a bar covering a fraction of a normal day matches — V1 learned
# this from measured GPW data. It is the course's own first principle (S2,
# "everything is relative") applied to the one place its wording omits it.
_MIN_SPREAD_MULT = 0.5

# ── The impulse leg and its correction ────────────────────────────────────────
# How far back to look for the impulse whose retracement defines the place.
_LEG_LOOKBACK = 120
# The pullback must have at least this many bars (a correction has to exist)...
_MIN_CORRECTION_BARS = 3
# ...and at most this many (beyond that the leg is history, not a live pullback).
_MAX_CORRECTION_BARS = 60
# The impulse must be a real advance, not noise, measured from its own low [L].
_MIN_IMPULSE_PCT = 0.05
# How many candidate peaks to walk back through before giving up on finding a
# live pullback. The course draws one impulse by hand; this is how far the
# search looks for the one it would have drawn [L].
_MAX_LEG_CANDIDATES = 6
# Retracement bands the course names [Z, lesson 22, repeated as text in 29].
_GEOMETRY_LEVELS = (0.382, 0.414, 0.500, 0.618)
# Half-width of the zone around each level, in fractions of the impulse height.
# The course does not give one [L]. At 0.03 the 38.2 and 41.4 lines (3.2 pp
# apart) read as the single region the slide draws them as.
_GEOMETRY_ZONE = 0.03

# ── WFO — volumetric reversal formation (lesson 26) ───────────────────────────
# Two lows are compared, so they must be separated by a genuine bounce...
_WFO_MIN_GAP = 3
# ...of at least this much, measured off the earlier low [L].
_WFO_MIN_BOUNCE = 0.02
# Half-window that makes a bar a local low for the WFO comparison [L].
_PIVOT_K = 2

# ── No supply at the peak ─────────────────────────────────────────────────────
# The window around the peak that must be free of a selling footprint [L].
_PEAK_BACK = 3
_PEAK_FWD = 3
# Prior highs an upthrust at the peak has to exceed [L].
_LEVEL_LOOKBACK = 10

# ── Corrective volume (lesson 27) ─────────────────────────────────────────────
# A correction needs this many bars before its volume can be said to expire.
_MIN_FADE_BARS = 4
# A shakeout this recent counts as the second, "ended by a violent move", type
# of correction the course allows [L].
_SHAKEOUT_WINDOW = 5

# ── Formations (lessons 3-5) ──────────────────────────────────────────────────
# Hammer: "the body should be no bigger than 1/3 of the whole" [Z, lesson 3].
_SMALL_BODY = 1.0 / 3.0
# Hammer: "the close is near the maximum" — the top third of the range. The
# course gives no number for "near" [L].
_CLOSE_TO_EXTREME = 1.0 / 3.0
# Hammer: "a long lower shadow", as a fraction of the range [L].
_LONG_SHADOW = 0.5
# Hammer: the upper shadow must be negligible. This is not a free parameter —
# the course's own list of rejected shapes includes "a hammer or shooting star
# with a shadow on the OPPOSITE side", so a bar with a real upper wick is
# disqualified however well the rest of it fits. Matches V1's constant, so both
# methods read the same hammer.
_NEGLIGIBLE_SHADOW = 0.10
# A "large" candle body, in units of the average spread [L].
_LONG_BODY_SPREADS = 0.5
# A body big enough to have a meaningful midpoint (Piercing Line) [L].
_MIN_BODY_SPREADS = 0.3
# Morning Star: the middle candle is "a small body or a doji", against candle 1.
_STAR_BODY_MAX = 0.35
# Inside Bar: how many consecutive inside bars may form one compression block.
_INSIDE_MAX_RUN = 5

# ── Signals of strength (lessons 8-13) ────────────────────────────────────────
# Bag Holding / Selling Climax: the drawings show three candles [R]; the course
# does not say whether three is a requirement.
_SERIES_N = 3
# Window a climactic bar must be the volume maximum of [L].
_CLIMAX_WINDOW = 20
# Two Bar Reversal: candle 2 is "the same size" as candle 1 [R].
_TBR_MIN_RATIO = 0.8
_TBR_MAX_RATIO = 1.4
# Test: how far back the earlier high-volume low may sit [L].
_TEST_LOOKBACK = 40
# Test: the return must be "much lower" volume — the compendium flags this as
# one of the two critical missing thresholds [L].
_TEST_VOL_FRACTION = 0.5
# Test: how close "back to the area of the low" is, in average spreads [L].
_TEST_ZONE_SPREADS = 1.0
# Test: how far below the old low the test may dip ("no new low, or only
# marginally lower" — lesson 21) [L].
_TEST_UNDERCUT_SPREADS = 0.5
# Test: the bar must come back up off its low — a close in the upper part of its
# own range. The course draws it as a two-tone body closing well above the low
# but puts no number on it [L]; this sits just under the course's 70% up-close.
_TEST_CLOSE_POS = 0.60

# ── The setup ─────────────────────────────────────────────────────────────────
# How many bars before the formation a confirming VSA signal may sit. The
# course says the signal confirms the formation but never says how far apart
# they may be [L]; a scanner cannot look forward, so the signal is allowed on
# the formation's own bars or just before them.
_CONFIRM_WINDOW = 3
# The course's one arithmetic filter [Z, lesson 29; derived in lesson 28].
_MIN_RR = 3.0
# Lesson 21's testing process, scored over this window [L].
_SEQUENCE_WINDOW = 40
# A setup this many calendar days old still counts as fresh for the score.
_RECENT_FIRED = 10
# How far back to scan for the most recent firing when reporting days_since.
_RECENCY_SCAN = 60
# The posture checklist the score is scaled against (see ``_posture_rules``).
_TOTAL_RULES = 6
# Minimum bars to evaluate at all. Every individual rule is satisfiable from
# about 45 bars, but one full leg-search window means the very first bar judged
# sees the same amount of history as every later one, so a stock's oldest
# markers are not read off a shorter memory than its newest. All 288 tracked
# GPW companies clear it.
_MIN_BARS = _LEG_LOOKBACK  # 120


def _sma_series(values: Sequence[float], length: int) -> list[float | None]:
    """Simple moving average ending AT each index (None until enough bars)."""
    out: list[float | None] = [None] * len(values)
    if length <= 0 or len(values) < length:
        return out
    run = sum(values[:length])
    out[length - 1] = run / length
    for i in range(length, len(values)):
        run += values[i] - values[i - length]
        out[i] = run / length
    return out


def _shift1(series: Sequence[float | None]) -> list[float | None]:
    """The same series read one bar late, so bar i sees only bars before it."""
    return [None, *list(series[:-1])]


def _median(values: Sequence[float]) -> float:
    """Plain median; 0.0 for an empty sequence."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


@dataclass(frozen=True)
class _Series:
    """One stock's bars plus the rolling context every rule reads."""

    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    #: Mean volume of the _VOL_MA bars strictly before each index.
    avg_vol: list[float | None]
    #: Mean spread of the _SPREAD_MA bars strictly before each index.
    avg_spread: list[float | None]

    @classmethod
    def build(cls, bars: Sequence[StooqDailyQuote]) -> _Series:
        opens = [float(b.open) for b in bars]
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]
        closes = [float(b.close) for b in bars]
        volumes = [float(b.volume) for b in bars]
        spreads = [h - low for h, low in zip(highs, lows, strict=True)]
        return cls(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            avg_vol=_shift1(_sma_series(volumes, _VOL_MA)),
            avg_spread=_shift1(_sma_series(spreads, _SPREAD_MA)),
        )

    def __len__(self) -> int:
        return len(self.closes)

    def body(self, i: int) -> float:
        return abs(self.closes[i] - self.opens[i])

    def rng(self, i: int) -> float:
        return self.highs[i] - self.lows[i]

    def lower_shadow(self, i: int) -> float:
        return min(self.opens[i], self.closes[i]) - self.lows[i]

    def close_pos(self, i: int) -> float | None:
        """(C - L) / (H - L) — the course's one close-position measure [Z]."""
        rng = self.rng(i)
        if rng <= 0:
            return None
        return (self.closes[i] - self.lows[i]) / rng

    def is_up_bar(self, i: int) -> bool:
        """VSA's up bar: close ABOVE the previous close, not a green body [Z]."""
        return i > 0 and self.closes[i] > self.closes[i - 1]

    def is_down_bar(self, i: int) -> bool:
        return i > 0 and self.closes[i] < self.closes[i - 1]

    def is_pink(self, i: int) -> bool:
        """The course's pink volume bar [Z]: lower than the previous N bars."""
        if i < _PINK_N:
            return False
        return all(self.volumes[i] < self.volumes[i - k] for k in range(1, _PINK_N + 1))

    def context(self, i: int) -> tuple[float, float] | None:
        """(average volume, average spread) before bar ``i``, or None.

        Fails closed on an absent or zero average: a run of frozen zero-spread
        bars during a suspension would otherwise satisfy every relative test
        on the resumption bar.
        """
        avg_v = self.avg_vol[i]
        avg_sp = self.avg_spread[i]
        if avg_v is None or avg_v < 1 or avg_sp is None or avg_sp <= 0:
            return None
        return avg_v, avg_sp


# ── The place: impulse leg, geometry, WFO ─────────────────────────────────────


@dataclass(frozen=True)
class _Leg:
    """The last impulse up and the correction hanging off it, as of one bar.

    ``trough`` and ``peak`` index the impulse's low and high; ``height`` is the
    move being retraced, which every geometry level is measured against, and
    ``peak_high`` is the target the course's R/R is computed to.
    """

    trough: int
    peak: int
    height: float
    peak_high: float


def _is_local_high(s: _Series, i: int, k: int = _PIVOT_K) -> bool:
    """Is bar ``i`` the highest high of the ``k`` bars either side of it?"""
    if i - k < 0 or i + k >= len(s):
        return False
    return all(s.highs[i] >= s.highs[j] for j in range(i - k, i + k + 1))


def _leg_from_peak(s: _Series, i: int, start: int, peak: int) -> _Leg | None:
    """Validate one candidate peak as the impulse the bar ``i`` pullback retraces."""
    if peak - start < 2 or i - peak > _MAX_CORRECTION_BARS:
        return None
    trough = min(range(start, peak), key=lambda k: s.lows[k])
    peak_high = s.highs[peak]
    trough_low = s.lows[trough]
    height = peak_high - trough_low
    if trough_low <= 0 or height <= 0:
        return None
    if height / trough_low < _MIN_IMPULSE_PCT:
        return None
    # The pullback must still BE a pullback: price has not taken the peak back
    # out (the correction would be over, and there is nothing to retrace), and
    # has not broken the impulse's own origin (the advance is undone).
    if max(s.highs[peak + 1 : i + 1]) > peak_high:
        return None
    if min(s.lows[peak + 1 : i + 1]) < trough_low:
        return None
    return _Leg(trough=trough, peak=peak, height=height, peak_high=peak_high)


def _find_leg(s: _Series, i: int) -> _Leg | None:
    """The impulse up that the pullback ending at bar ``i`` is retracing.

    The course measures its retracement off "the impulse", drawn by hand from a
    low to a high (lesson 22: the diagonal line the levels hang off). Its
    lesson-29 schema says which one: a sharp fall, the low marked WM, a bounce,
    a SECOND HIGHER LOW, and the entry there — so the impulse being retraced is
    the most recent completed advance, not necessarily the largest one on
    screen.

    Mechanically: walk back from the newest candidate peak (a local high old
    enough that a correction exists) and take the first one that still stands —
    unexceeded since, its origin intact, and a real advance rather than noise.
    Taking only the highest high of the whole lookback instead would blind the
    method to every stock whose window high is older than
    ``_MAX_CORRECTION_BARS``, which on stored GPW history is over 40% of bars.

    KNOWN [L], and it is a real limitation rather than a nicety: the PEAK is
    the most recent one that still stands, but the TROUGH is simply the lowest
    low in the whole lookback (``_leg_from_peak``), so the "impulse" is often
    the largest swing in the window and not the last leg up. Measured on stored
    GPW history the median leg runs 63 bars and 25%, and in about one leg in
    eight the trough sits against the window's left edge — an artefact of
    ``_LEG_LOOKBACK`` rather than a turning point. Everything downstream is
    measured off that height: the geometry bands, and the distance to the
    target the R/R is computed to. The course gives no rule to replace it with
    ("Kurs nie podaje ... jak wybierac impuls do mierzenia zniesienia", lesson
    22 [L]), so a different choice here would be an invention, not a
    correction — but it should not be read as the course's hand-drawn impulse.
    """
    start = max(0, i - _LEG_LOOKBACK)
    peak_end = i - _MIN_CORRECTION_BARS
    if peak_end - start < _VOL_MA:
        return None

    tried = 0
    for peak in range(peak_end, start + 1, -1):
        if not _is_local_high(s, peak):
            continue
        tried += 1
        if tried > _MAX_LEG_CANDIDATES:
            return None
        leg = _leg_from_peak(s, i, start, peak)
        if leg is not None:
            return leg
    return None


def _on_geometry(leg: _Leg, low: float) -> float | None:
    """The retracement level ``low`` halted on, or None if it is between bands.

    "Zatrzymanie na geometrii - 38,2; 41,4; 50; 61,8" [Z]. Returns the matched
    level so the reason can be reported to the reader.
    """
    retr = (leg.peak_high - low) / leg.height
    for level in _GEOMETRY_LEVELS:
        if abs(retr - level) <= _GEOMETRY_ZONE:
            return level
    return None


def _is_local_low(s: _Series, i: int, k: int = _PIVOT_K) -> bool:
    """Is bar ``i`` the lowest low of the ``k`` bars either side of it?"""
    if i - k < 0 or i + k >= len(s):
        return False
    return all(s.lows[i] <= s.lows[j] for j in range(i - k, i + k + 1))


def _bullish_wfo(s: _Series, leg: _Leg, i: int) -> bool:
    """Lesson 26's bullish WFO: a lower price low on a lower VOLUME low.

    Two lows are compared, D1 then D2, with a bounce between them:
    ``L(D2) < L(D1)`` and ``V(D2) < V(D1)`` — price makes a new low but the
    selling behind it has shrunk. The signal is the SECOND low; the first is
    only the volume reference. The course gives no minimum difference for
    either comparison [L], so both are read strictly as drawn.

    BOTH lows belong to the same decline. The slide is explicit about the
    sequence — "ruch spadkowy, pierwszy dolek, odbicie, drugi dolek NIZSZY od
    pierwszego, po nim wyjscie w gore" [R] — so D1 is searched only inside the
    correction, after the peak. Letting it reach back into the impulse (as far
    as ``leg.trough``) turns the rule into "is there any local low in the last
    120 bars that is higher than this one and traded more volume", with the
    whole rally standing in for the slide's small bounce; measured on stored
    GPW history that loose form was true on 45% of legs and supplied most of
    this method's places, crowding out the geometry route the course actually
    writes down.
    """
    d2 = min(range(leg.peak + 1, i + 1), key=lambda k: s.lows[k])
    if i - d2 > _WFO_MIN_GAP + _PIVOT_K:
        # The second low is no longer the live edge of the correction.
        return False
    for d1 in range(d2 - _WFO_MIN_GAP, leg.peak, -1):
        if not _is_local_low(s, d1):
            continue
        if s.lows[d2] >= s.lows[d1] or s.volumes[d2] >= s.volumes[d1]:
            continue
        # The bounce is what price did BETWEEN the lows ("odbicie" sits between
        # the two numbered arrows), so neither low's own bar counts. Reading
        # D1's high as part of it made the rule vacuous: any first low whose own
        # session spanned 2% "bounced", even if price never left it afterwards.
        bounce_high = max(s.highs[d1 + 1 : d2])
        if s.lows[d1] > 0 and (bounce_high - s.lows[d1]) / s.lows[d1] >= _WFO_MIN_BOUNCE:
            return True
    return False


def _in_wm(s: _Series, leg: _Leg, i: int, low: float) -> str | None:
    """The WM route this place qualifies under, or None — lesson 29's gate.

    ``low`` is where the formation sits (its own lowest low). Two of the
    slide's three alternatives are implemented; the third, "the end of an ABC
    correction", is never defined anywhere in the course and is left out
    rather than invented (see the module docstring).

    The geometry route is a HALT ("zatrzymanie na geometrii"), so it is judged
    where the correction actually stopped — its lowest low, the point the
    lesson-29 schema circles and labels WM — not wherever the formation
    happens to sit. The schema then draws a bounce and a second, HIGHER
    approach as the entry, so the formation may complete above the halt, but
    it must still be on the geometry itself. Judging the formation's low alone
    let a pullback that ran straight through every band count as a halt on one
    of them, as soon as a later bounce candle's low landed inside it.
    """
    halt = min(s.lows[leg.peak + 1 : i + 1])
    level = _on_geometry(leg, halt)
    if level is not None and _on_geometry(leg, low) is not None:
        return f"{level * 100:.1f}%".replace(".0%", "%")
    if _bullish_wfo(s, leg, i):
        return "WFO"
    return None


# ── Condition: no supply at the peak ─────────────────────────────────────────


def _no_supply_at_peak(s: _Series, leg: _Leg, i: int) -> bool:
    """"BRAK PODAZY W SZCZYCIE" — the top shows no selling footprint.

    Read as an absence, which is how the course's law of cause and effect
    frames it. Around the peak, none of the three ways the course draws supply
    arriving at a top may appear:

    * a wide-spread down bar on high volume — real effort spent driving price
      down off the top. This is the generic VSA supply footprint, NOT one of
      the course's named signals: lesson 15's Supply Coming In is a different
      picture entirely ("co najmniej dwie swiece WZROSTOWE o WYSOKIM
      wolumenie, oddzielone korekta, przy niewspolmiernie malym przyroscie
      ceny" — K10 [R]), so this rule is marked [L] and claims no lesson;
    * an UPTHRUST — a push above the prior highs closing in the bottom 30% of
      its own range on high volume (lesson 20's K15, which also catches K11
      Trap Upmove, the same break with a large red body);
    * a BUYING CLIMAX — lesson 14's K9, and the one signal the course draws
      not as a shape but as a PLACE: "ekstremum wolumenu na szczycie trendu,
      po ktorym cena nie idzie juz wyzej" [R] — a volume extreme at the top of
      the advance after which price goes no higher. The second half is already
      guaranteed here (``_leg_from_peak`` rejects a peak price has since taken
      back out), so what is left to test is the volume extreme itself.

    Any of them means the advance ended in distribution, so the dip is not a
    correction and there is nothing to buy.

    The climax test is the one that does the work: measured on stored GPW
    history, 19% of the setups this method fired without it were pullbacks
    bought out of a climactic top — the single situation this condition exists
    to refuse. (Lesson 17's K13 No Result From Effort was measured too and
    never fired at a peak on this universe, so it is deliberately not added:
    a detector that cannot fire is dead code wearing the course's name.)

    Fails CLOSED when the peak sits too early in the series to audit, rather
    than passing vacuously on an empty window.
    """
    start = max(_LEVEL_LOOKBACK, _CLIMAX_WINDOW, leg.peak - _PEAK_BACK)
    end = min(i, leg.peak + _PEAK_FWD)
    if start > end:
        return False
    for j in range(start, end + 1):
        ctx = s.context(j)
        if ctx is None:
            continue
        avg_v, avg_sp = ctx
        high_vol = s.volumes[j] >= _HIGH_VOL_MULT * avg_v
        if not high_vol:
            continue
        if s.is_down_bar(j) and s.rng(j) >= _WIDE_SPREAD_MULT * avg_sp:
            return False
        cp = s.close_pos(j)
        prior_high = max(s.highs[j - _LEVEL_LOOKBACK : j])
        if cp is not None and cp <= _DOWN_CLOSE and s.highs[j] > prior_high:
            return False
        if s.volumes[j] >= _ULTRA_VOL_MULT * avg_v and s.volumes[j] >= max(
            s.volumes[j - _CLIMAX_WINDOW : j]
        ):
            return False
    return True


# ── Condition: corrective volume ─────────────────────────────────────────────


def _corrective_volume(s: _Series, leg: _Leg, i: int) -> bool:
    """"WOLUMEN KOREKCYJNY" — lesson 27's two allowed kinds of correction.

    The classic one runs "on expiring volume": the pullback is quieter than the
    impulse it corrects (the course's bullish volume, lesson 6 — volume grows
    on up-waves and shrinks on down-waves) and its own volume systematically
    falls as it goes. The second kind ends in one violent move on raised
    volume, whose extreme is the turning point — mechanically a Shakeout, so a
    recent shakeout satisfies this condition by the other route.
    """
    corr = list(range(leg.peak + 1, i + 1))
    if len(corr) < _MIN_FADE_BARS:
        return False

    impulse_vols = s.volumes[leg.trough : leg.peak + 1]
    corr_vols = [s.volumes[j] for j in corr]
    half = len(corr) // 2
    # A halted stock prints zero-volume bars, and those satisfy "the volume
    # expired" and "quieter than the impulse" perfectly — a suspension would
    # otherwise read as the course's textbook correction and push the method
    # into leaning bullish on a stock that is not trading at all. Volume drying
    # up means fewer trades, not none.
    if min(corr_vols) <= 0:
        return False

    faded = _median(corr_vols[half:]) < _median(corr_vols[:half])
    quieter = _median(corr_vols) <= _median(impulse_vols) if impulse_vols else False
    if faded and quieter:
        return True

    return any(
        _shakeout(s, j) for j in range(max(corr[0], i - _SHAKEOUT_WINDOW + 1), i + 1)
    )


# ── Candle formations (lessons 3-5) ───────────────────────────────────────────
# Each returns the number of bars the formation spans (so the stop can be placed
# under its low, as the course requires) or None.


def _hammer(s: _Series, i: int) -> int | None:
    """"A long lower shadow, the close near the high, the body at most 1/3 of
    the whole, the colour irrelevant, appearing after a fall" [Z, lesson 3],
    and no meaningful shadow on the opposite side (the course's own rejected
    shape T11)."""
    ctx = s.context(i)
    if ctx is None:
        return None
    _, avg_sp = ctx
    rng = s.rng(i)
    if rng <= 0 or rng < _MIN_SPREAD_MULT * avg_sp:
        return None
    if s.body(i) > _SMALL_BODY * rng:
        return None
    if (s.highs[i] - s.closes[i]) / rng > _CLOSE_TO_EXTREME:
        return None
    if s.lower_shadow(i) < _LONG_SHADOW * rng:
        return None
    if (s.highs[i] - max(s.opens[i], s.closes[i])) > _NEGLIGIBLE_SHADOW * rng:
        return None
    return 1


def _piercing(s: _Series, i: int) -> int | None:
    """"A close above 50% of the preceding candle's body" [Z, lesson 3]."""
    if i < 1:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    _, avg_sp = ctx
    if s.closes[i - 1] >= s.opens[i - 1] or s.closes[i] <= s.opens[i]:
        return None
    if s.body(i - 1) < _MIN_BODY_SPREADS * avg_sp:
        return None
    midpoint = (s.opens[i - 1] + s.closes[i - 1]) / 2
    if s.closes[i] <= midpoint:
        return None
    return 2


def _morning_star(s: _Series, i: int) -> int | None:
    """Lesson 3's Morning Star [R]: a large down candle, a small body clear of
    its body, then a large up candle."""
    if i < 2:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    _, avg_sp = ctx
    b1, b2, b3 = s.body(i - 2), s.body(i - 1), s.body(i)
    if s.closes[i - 2] >= s.opens[i - 2] or s.closes[i] <= s.opens[i]:
        return None
    if b1 < _LONG_BODY_SPREADS * avg_sp or b3 < _LONG_BODY_SPREADS * avg_sp:
        return None
    if b1 <= 0 or b2 > _STAR_BODY_MAX * b1:
        return None
    if max(s.opens[i - 1], s.closes[i - 1]) >= min(s.opens[i - 2], s.closes[i - 2]):
        return None
    return 3


def _bullish_engulfing(s: _Series, i: int) -> int | None:
    """Lesson 3's Bullish Engulfing [R]: the up candle engulfs the down
    candle's BODY (the drawing engulfs bodies, not full ranges)."""
    if i < 1:
        return None
    ctx = s.context(i)
    if ctx is None:
        return None
    _, avg_sp = ctx
    if s.closes[i - 1] >= s.opens[i - 1] or s.closes[i] <= s.opens[i]:
        return None
    if s.body(i - 1) < _MIN_BODY_SPREADS * avg_sp:
        return None
    if s.opens[i] > s.closes[i - 1] or s.closes[i] < s.opens[i - 1]:
        return None
    return 2


def _inside_breakout(s: _Series, i: int) -> int | None:
    """Lesson 5's Inside Bar, taken long: price leaves the mother bar's range.

    "The signal is the exit beyond the range of candle 1" — the course teaches
    the short variant (enter below the inside bar), so the long side is its
    mirror: a close above the bar that set the range. The compression may be
    one bar or a run of them ("the longer the compression, the stronger the
    break"), capped at ``_INSIDE_MAX_RUN``.
    """
    ctx = s.context(i)
    if ctx is None:
        return None
    inside = 0
    mother = i - 1
    capped = True
    while inside < _INSIDE_MAX_RUN and mother - 1 >= 0:
        if s.highs[mother] <= s.highs[mother - 1] and s.lows[mother] >= s.lows[mother - 1]:
            inside += 1
            mother -= 1
            continue
        capped = False
        break
    if inside == 0:
        return None
    if capped and inside >= _INSIDE_MAX_RUN:
        # The run hit the cap before the real mother bar was found, so `mother`
        # is still an INSIDE bar and its high is narrower than the range that
        # actually has to be broken. Reporting a break of it would be an easier
        # signal than the rule asks for, so decline to read the compression.
        return None
    if s.closes[i] <= s.highs[mother] or s.closes[i] <= s.opens[i]:
        return None
    return i - mother + 1


# Longest-spanning first, so that when one bar completes two formations the
# fuller reading wins and the stop goes under all of its bars rather than under
# the last one. The order is load-bearing, not cosmetic: a shorter span is a
# tighter stop, which inflates the R/R that lesson 29's 3:1 filter then judges.
_FORMATIONS: tuple[tuple[str, object], ...] = (
    ("Inside Bar break", _inside_breakout),
    ("Morning Star", _morning_star),
    ("Bullish Engulfing", _bullish_engulfing),
    ("Piercing Line", _piercing),
    ("Hammer", _hammer),
)


def _formation_at(s: _Series, i: int) -> tuple[str, int] | None:
    """The bullish candle/bar formation completing on bar ``i``, if any.

    Returns ``(label, span)`` — the span being how many bars the formation
    covers, which is what the stop goes under. Multi-bar formations are checked
    before their single-bar lookalikes so the fuller reading wins.
    """
    for label, detector in _FORMATIONS:
        span = detector(s, i)  # type: ignore[operator]
        if span is not None:
            return label, span
    return None


# ── Signals of strength (lessons 8-13) ────────────────────────────────────────


def _down_move(s: _Series, i: int, n: int = _SERIES_N) -> bool:
    """"Kontekst: ruch spadkowy" — bar ``i`` sits at the end of a decline.

    Every signal of strength in lessons 8-13 is drawn after a fall, and that
    context is the part the slides state. The number of candles in the run is
    NOT: the compendium records for lessons 8 and 14 that "the drawing shows
    three, but nothing says three is a requirement" [L]. So the run is read as
    a net decline over ``n`` bars in which the closes mostly fell, rather than
    as exactly three strictly-ordered candles — which, measured on stored GPW
    history, fired about once per twenty ticker-years and made both detectors
    dead code.
    """
    if i < n:
        return False
    downs = sum(1 for j in range(i - n + 1, i + 1) if s.is_down_bar(j))
    return downs >= n - 1 and s.closes[i] < s.closes[i - n]


def _bag_holding(s: _Series, i: int) -> bool:
    """Lesson 8's Bag Holding [R]: bodies shrink while volume grows.

    Effort up, result down — the highest volume of the run sits under the
    smallest body, so maximum selling is buying maximum nothing. The run may be
    two or three candles (see ``_down_move`` on why the length is not fixed at
    the three the slide draws).
    """
    ctx = s.context(i)
    if ctx is None or not _down_move(s, i):
        return False
    avg_v, _ = ctx
    if s.volumes[i] < _ELEVATED_VOL_MULT * avg_v:
        return False
    for n in (_SERIES_N, _SERIES_N - 1):
        idx = list(range(i - n + 1, i + 1))
        if idx[0] < 1 or not all(s.is_down_bar(j) for j in idx):
            continue
        if all(
            s.body(b) < s.body(a) and s.volumes[b] > s.volumes[a]
            for a, b in zip(idx[:-1], idx[1:], strict=True)
        ):
            return True
    return False


def _selling_climax(s: _Series, i: int) -> bool:
    """Lesson 8's Selling Climax [R]: selling culminates in one bar.

    Bodies grow into the low, then price spikes down on extreme volume and
    closes back up, leaving a long lower shadow — the compendium's reading is
    "lower shadow > body, volume the maximum in the window". The expansion is
    tested against the previous bar rather than as a fixed three-candle run
    (see ``_down_move``), which is what separates a climax from Bag Holding:
    there the bodies shrink, here they grow.
    """
    if i < _CLIMAX_WINDOW:
        return False
    ctx = s.context(i)
    if ctx is None or not _down_move(s, i):
        return False
    avg_v, _ = ctx
    if s.body(i) <= s.body(i - 1):
        return False
    if s.lower_shadow(i) <= s.body(i):
        return False
    if s.volumes[i] < _ULTRA_VOL_MULT * avg_v:
        return False
    return s.volumes[i] >= max(s.volumes[i - _CLIMAX_WINDOW : i])


def _stopping_volume(s: _Series, i: int) -> bool:
    """Lesson 9's Stopping Volume [R]: a down candle, then a SMALLER up candle
    that takes back part of its range on high volume — the fall is halted
    without being reversed (which is what separates it from a Two Bar
    Reversal)."""
    if i < 1:
        return False
    if s.context(i) is None:
        return False
    if s.closes[i - 1] >= s.opens[i - 1] or s.closes[i] <= s.opens[i]:
        return False
    if s.body(i) >= s.body(i - 1):
        return False
    if s.rng(i - 1) <= 0:
        return False
    midpoint = s.lows[i - 1] + s.rng(i - 1) / 2
    if s.closes[i] <= midpoint:
        return False
    # The effort sits on the down bar; the slide draws its volume bar as the
    # taller of the pair. Judge it against the average of the bars before IT,
    # the way every other detector here judges its own bar — reading bar i-1
    # against bar i's average would score it partly against itself.
    ctx_prev = s.context(i - 1)
    if ctx_prev is None:
        return False
    return s.volumes[i - 1] >= _HIGH_VOL_MULT * ctx_prev[0]


def _shakeout(s: _Series, i: int) -> bool:
    """Lesson 10's Shakeout [R]: price dips under the level the protective
    orders sit on, shakes them out, and closes straight back above it on the
    highest volume around."""
    if i < max(_LEVEL_LOOKBACK, _CLIMAX_WINDOW):
        return False
    ctx = s.context(i)
    if ctx is None:
        return False
    avg_v, _ = ctx
    level = min(s.lows[i - _LEVEL_LOOKBACK : i])
    if s.lows[i] >= level:
        return False
    if s.closes[i] <= s.opens[i] or s.closes[i] <= level:
        return False
    if s.lower_shadow(i) <= s.body(i):
        return False
    if s.volumes[i] < _HIGH_VOL_MULT * avg_v:
        return False
    return s.volumes[i] >= max(s.volumes[i - _LEVEL_LOOKBACK : i])


def _two_bar_reversal(s: _Series, i: int) -> bool:
    """Lesson 11's Two Bar Reversal [R]: a down candle and an up candle of the
    SAME size, the second reaching the top of the first's body — a full
    reversal rather than a halt — and BOTH of them on low volume.

    The volume condition is read straight off the slide's own panels: under
    the pair, "niski slupek czerwony i obok niego niski zielony", against a
    second, comparative panel of "trzy czerwone slupki o rosnacej wysokosci"
    showing the volume during the decline itself. So the pair is quiet against
    a noisy fall. The compendium's K5 formalisation drops this, and without it
    the detector is a pure PRICE-shape rule that all but duplicates
    ``_bullish_engulfing`` — which let a single candle satisfy both halves of
    lesson 29's "FORMACJA SWIECOWA POTWIERDZONA SYGNALEM VSA" by itself, the
    one reading the slide explicitly rules out ("nie sa alternatywami, tylko
    musza wystapic razem"). Measured on stored GPW history, every one of the
    "Bullish Engulfing confirmed by Two Bar Reversal" firings was one bar
    wearing both names. "Low" is the course's own volume class, i.e. under the
    20-session average [L] — the slide gives no number.
    """
    if i < 1:
        return False
    ctx = s.context(i)
    if ctx is None:
        return False
    avg_v, _ = ctx
    if s.closes[i - 1] >= s.opens[i - 1] or s.closes[i] <= s.opens[i]:
        return False
    b1, b2 = s.body(i - 1), s.body(i)
    if b1 <= 0 or not (_TBR_MIN_RATIO <= b2 / b1 <= _TBR_MAX_RATIO):
        return False
    if s.volumes[i] > avg_v or s.volumes[i - 1] > avg_v:
        return False
    return s.closes[i] >= s.opens[i - 1] - 0.1 * b1


def _no_supply(s: _Series, i: int) -> bool:
    """Lesson 12's No Supply — the one signal with a computable volume rule.

    A small narrow down candle whose volume bar is PINK: lower than the
    previous two [Z]. "A lack of supply shows itself as selling failing to
    increase on down candles."
    """
    ctx = s.context(i)
    if ctx is None:
        return False
    _, avg_sp = ctx
    if not s.is_down_bar(i) or s.closes[i] >= s.opens[i]:
        return False
    if s.rng(i) > _NARROW_SPREAD_MULT * avg_sp:
        return False
    return s.is_pink(i)


def _test(s: _Series, i: int) -> bool:
    """Lesson 13's Test [R]: price returns to an earlier high-volume low on
    MUCH smaller volume and closes back up.

    The only signal in the course defined by comparing two places in time
    rather than the shape of one bar or pair: the supply that once needed heavy
    volume is no longer there. Lesson 21 calls a successful test one of the
    strongest tools in VSA, and allows the low to be marginally undercut.
    """
    ctx = s.context(i)
    if ctx is None:
        return False
    avg_v, avg_sp = ctx
    cp = s.close_pos(i)
    if cp is None or cp < _TEST_CLOSE_POS:
        return False
    # A test happens on LOW volume in the course's own volume classes, not
    # merely on less volume than the low it is testing: "the supply that once
    # needed heavy volume is no longer there" [L for the level].
    if s.volumes[i] > avg_v:
        return False
    zone = _TEST_ZONE_SPREADS * avg_sp
    undercut = _TEST_UNDERCUT_SPREADS * avg_sp
    start = max(_VOL_MA, i - _TEST_LOOKBACK)
    for d in range(i - 2, start - 1, -1):
        ctx_d = s.context(d)
        if ctx_d is None:
            continue
        avg_v_d, _ = ctx_d
        if s.volumes[d] < _HIGH_VOL_MULT * avg_v_d:
            continue
        if not _is_local_low(s, d):
            continue
        if s.lows[i] < s.lows[d] - undercut or s.lows[i] > s.lows[d] + zone:
            continue
        if s.volumes[i] <= _TEST_VOL_FRACTION * s.volumes[d]:
            return True
    return False


_SIGNALS: tuple[tuple[str, object], ...] = (
    ("Selling Climax", _selling_climax),
    ("Shakeout", _shakeout),
    ("Test", _test),
    ("Stopping Volume", _stopping_volume),
    ("Two Bar Reversal", _two_bar_reversal),
    ("Bag Holding", _bag_holding),
    ("No Supply", _no_supply),
)


def _signal_at(s: _Series, i: int) -> str | None:
    """The strongest signal of strength on bar ``i``, if any."""
    for label, detector in _SIGNALS:
        if detector(s, i):  # type: ignore[operator]
            return label
    return None


def _confirming_signal(s: _Series, i: int, span: int) -> str | None:
    """A signal of strength on the formation's bars or just before them.

    The slide's word is *confirmed*: the formation and the signal must occur
    together. A scanner cannot look forward, so the window runs backwards from
    the formation's last bar — its own bars plus ``_CONFIRM_WINDOW``.
    """
    oldest = max(0, i - span - _CONFIRM_WINDOW + 1)
    for j in range(i, oldest - 1, -1):
        label = _signal_at(s, j)
        if label is not None:
            return label
    return None


# ── Condition: R/R at least 3:1 ──────────────────────────────────────────────


def _formation_stop(s: _Series, formation: str, i: int, span: int) -> float:
    """Where lesson 3 puts the stop for this formation [Z].

    The lesson writes one per formation, and three of the four reduce to the
    same thing — the formation's own minimum: the Hammer's "stop loss pod
    minimum dolnego cienia", the Piercing Line's "pod minimum formacji", the
    Bullish Engulfing's "pod dolna granica formacji". The Morning Star is the
    exception the course states separately: "stop loss pod minimum swiecy
    SRODKOWEJ" — under the middle candle, the star itself, not under whichever
    of the three bars happens to be lowest.
    """
    if formation == "Morning Star" and span == 3:
        return s.lows[i - 1]
    return min(s.lows[i - span + 1 : i + 1])


def _risk_reward(s: _Series, leg: _Leg, i: int, formation: str, span: int) -> float | None:
    """Potential reward-to-risk for a long taken on this formation.

    Entry is the formation's close (a scanner reads end-of-day; the course
    would buy the break of the formation). The stop is where lesson 3 puts it
    for this particular formation (``_formation_stop``), which is also the
    course's general rule — "the level at which the position stops making
    sense in terms of the reason it was taken". The target is the peak
    the correction fell from: the course requires a target planned at entry
    and never gives a rule for choosing one [L], and that peak is the level
    the resumed move is measured to.

    ``None`` when the geometry is degenerate (no risk, or the target is
    already below the entry).
    """
    entry = s.closes[i]
    stop = _formation_stop(s, formation, i, span)
    risk = entry - stop
    reward = leg.peak_high - entry
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


# ── The complete setup ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Setup:
    """One complete Scenario 5 firing, with the reasons it passed."""

    formation: str
    signal: str
    place: str
    rr: float

    @property
    def label(self) -> str:
        return f"{self.formation} + {self.signal}"


def _setup_at(s: _Series, i: int) -> _Setup | None:
    """Lesson 29's Scenario 5 (long), evaluated on bar ``i``.

    Every condition is a hard gate, so the order changes nothing but the cost:
    the shape is tested first because it is the cheapest and rejects ~95% of
    bars outright, and the arithmetic filter last because it is the one that
    rejects a good read of the market on its own. (The course's own order is
    the other way round — "first the place, then the candle", lesson 2 — which
    is how a human reads a chart, not how a scanner should sweep one.)
    """
    found = _formation_at(s, i)
    if found is None:
        return None
    formation, span = found

    leg = _find_leg(s, i)
    if leg is None:
        return None

    form_low = min(s.lows[i - span + 1 : i + 1])
    place = _in_wm(s, leg, i, form_low)
    if place is None:
        return None

    if not _no_supply_at_peak(s, leg, i):
        return None
    if not _corrective_volume(s, leg, i):
        return None

    signal = _confirming_signal(s, i, span)
    if signal is None:
        return None

    rr = _risk_reward(s, leg, i, formation, span)
    if rr is None or rr < _MIN_RR:
        return None

    return _Setup(formation=formation, signal=signal, place=place, rr=rr)


# ── Score: how much of the setup currently stands ─────────────────────────────


def _test_process(s: _Series, i: int) -> bool:
    """Lesson 21's testing process: a high-volume low, a bounce, then a return
    to it on much lower volume.

    This is the one sequence the material pins down concretely (the 2018
    series draws it as A -> Stop -> T), and ``_test`` already encodes exactly
    it — a test only fires when an earlier high-volume low exists and is
    revisited on a fraction of that volume. Scored rather than gated, because
    the course never assigns its fourteen signals to its three sequence
    categories.
    """
    return any(_test(s, j) for j in range(max(0, i - _SEQUENCE_WINDOW + 1), i + 1))


def _posture_rules(s: _Series, i: int, days_since: int, leg: _Leg | None) -> int:
    """How many of the setup's six conditions currently stand (0-6)."""
    if leg is None:
        # No live pullback off a measured impulse: nothing this method plays.
        return 1 if days_since <= _RECENT_FIRED else 0
    # Rule 2 must be read off the same low ``_setup_at`` gates on, or a stock
    # that fired today on a multi-bar formation would publish a posture saying
    # it is not in a WM — the score contradicting its own ``fired`` flag.
    found = _formation_at(s, i)
    wm_low = min(s.lows[i - found[1] + 1 : i + 1]) if found is not None else s.lows[i]
    checks = (
        True,  # 1 a live correction off a real impulse exists
        _in_wm(s, leg, i, wm_low) is not None,  # 2 price is in a WM
        _no_supply_at_peak(s, leg, i),  # 3 no supply at the peak
        _corrective_volume(s, leg, i),  # 4 the pullback's volume is corrective
        _test_process(s, i),  # 5 lesson 21's testing process happened
        days_since <= _RECENT_FIRED,  # 6 a complete setup fired recently
    )
    return sum(1 for ok in checks if ok)


@register_method
class Vsa2(TradingMethod):
    id = "vsa2"
    order = 50
    name = "VSA V2"
    description = (
        "Rafal Glinicki's 30-lesson VSA course, run as the one complete trade "
        "setup it builds towards (\"Scenario 5 - long\"). It buys a pullback "
        "inside an advance, and only when six things hold at once: price has "
        "come back to a measured place — one of the course's retracement bands "
        "(38.2 / 41.4 / 50 / 61.8) of the last impulse up, or a volume "
        "divergence at the low (WFO); the peak the pullback started from shows "
        "no selling (no wide down-bar on heavy volume, no upthrust); the "
        "pullback's own volume has dried up, or it ended in a shakeout; a "
        "bullish candle formation has completed here (Hammer, Piercing Line, "
        "Morning Star, Bullish Engulfing or an Inside Bar break); a VSA signal "
        "of strength confirms it (Test, No Supply, Selling Climax, Stopping "
        "Volume, Shakeout, Bag Holding, Two Bar Reversal); and the trade still "
        "offers at least 3:1 to the old peak with the stop under the "
        "formation. That last filter is arithmetic and rejects a good setup "
        "priced too close to its target. The score says how many of the six "
        "conditions stand today. Long-only. (Back-tested on stored GPW "
        "history: over 63 historical firings it beat each stock's own baseline "
        "move by 5.3 percentage points on a 30-session horizon — the only "
        "method here that passes that gate at all — but on a 10-session one "
        "the trade has not yet reached its target and it does not. Judge it "
        "over weeks, not days, and note the sample is small.)"
    )
    source = (
        "Rafal Glinicki — Investing Masters: VSA (XTB Polska, 30 lessons), "
        "lesson 29 \"Scenariusz 5 (long)\", with lessons 3-5, 8-13, 21-22, "
        "26-28; and his 2018 XTB / VSA Trader webinar series"
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

        s = _Series.build(bars)
        last_idx = len(bars) - 1
        last_date = bars[last_idx].date

        days_since = NEVER_FIRED
        setup: _Setup | None = None
        floor = max(_MIN_BARS - 1, last_idx - _RECENCY_SCAN)
        for i in range(last_idx, floor - 1, -1):
            hit = _setup_at(s, i)
            if hit is not None:
                days_since = (last_date - bars[i].date).days
                setup = hit
                break

        leg = _find_leg(s, last_idx)
        passed = _posture_rules(s, last_idx, days_since, leg)
        score = round(passed / _TOTAL_RULES * 100)
        fired = days_since == 0

        if setup is not None and fired:
            detail = f"{setup.label} @ {setup.place}, R/R {setup.rr:.1f}:1"
        elif setup is not None:
            detail = f"{setup.label} {days_since}d ago"
        elif leg is None:
            # Nothing this method plays: no live pullback off a measured impulse
            # (price is at a new high, or the correction is older than
            # _MAX_CORRECTION_BARS, or the advance has been undone).
            detail = "No pullback setup"
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
        """A marker on every bar a complete Scenario 5 fired on, oldest first.

        Each firing is its own event — the course treats a second setup at the
        same place as accumulating evidence — and every marker is labelled with
        the formation and the VSA signal that confirmed it.
        """
        if len(bars) < _MIN_BARS:
            return []
        s = _Series.build(bars)
        out: list[MethodSignal] = []
        for i in range(_MIN_BARS - 1, len(bars)):
            setup = _setup_at(s, i)
            if setup is not None:
                out.append(
                    MethodSignal(date=bars[i].date, label=setup.label, type="Bullish")
                )
        return out
