"""VSA Glinicki V1 — the bullish half of Rafal Glinicki's VSA course, mechanised.

Source: *Kurs inwestowania metoda VSA* by Rafal Glinicki (XTB Polska, five
lessons, 2 h 29 min), which teaches Tom Williams' Volume Spread Analysis (after
Richard Wyckoff) as one repeatable decision procedure rather than a bag of
patterns. The course's own "master algorithm" is this method's skeleton:

    1. Establish the market PHASE — accumulation, markup, distribution or
       markdown. It decides which signals you may even look for: bullish ones
       only in accumulation and on pullbacks inside an uptrend.
    2. Build the BACKGROUND — trend and its maturity, support/resistance
       levels, where the ultra-high-volume bars sit (that is where big money
       holds a position), earlier signs of strength.
    3. Mark the ZONE *before* a signal appears. A formation found by accident
       in the middle of the chart means nothing.
    4. Wait for a FORMATION in that zone.
    5. Apply the law of EFFORT VS RESULT — the formation's volume against the
       ~20-bar volume average. This is the moment of decision.

and its three disqualifiers, each of which alone kills a setup: a formation out
of phase, a formation outside the marked zone, and a formation without volume
confirmation. All three are enforced here as hard gates, so this method fires
rarely and only on a complete Glinicki setup — that is the point of it. Steps
6-9 of the course (entry type, stop placement, target, trade management) are
execution advice, not selection, and are out of scope for a scanner: firing
means "the formation completed"; the course's own entry is then a buy-stop just
above the formation's high.

PROVENANCE. The rules below are taken from a written compendium of the course
(its per-lesson chapter listings with second-level timestamps, the official
lesson descriptions, and the canonical Williams/Wyckoff VSA methodology the
course teaches) rather than from a verbatim transcript — YouTube exposes no
transcript for these videos. The distinction matters, and it lines up in this
method's favour: the formation definitions, the three laws, the market phases
and the master algorithm encoded here are canonical VSA and are not in doubt,
while the one part of the course that a compendium cannot pin down exactly —
the precise entry/stop/target placement of each "strategia gry" — is execution
advice a scanner has no use for and is deliberately not encoded. See
``agent/ROADMAP.md`` item 25 for the standing task of obtaining the real
transcripts.

**Long-only.** The course is symmetric — lesson 3 teaches four bullish candle
formations and lesson 4 their exact mirror images — but the app's trading-method
framework is long-only (a method leans bullish or stays neutral, never bearish),
so only the bullish half is implemented. The bearish formations (Shooting Star,
Evening Star, Dark Cloud Cover, Bearish Engulfing) are deliberately absent; the
app's VSA engine already surfaces the weakness side through Upthrust / No Demand
/ SOW.

The six bullish setups, exactly as the course's summary table ("Sciaga")
specifies them:

    Hammer             1 candle   — high/ultra volume (absorption) or very low
                                    volume (a test after an earlier climax)
    Piercing Line      2 candles  — elevated volume on candle 2
    Morning Star       3 candles  — lower volume on candle 2, rising on candle 3
    Bullish Engulfing  2 candles  — volume higher on the engulfing candle (critical)
    Outside Bar        2 candles  — always elevated volume, close in the upper part
    Inside Bar break   2+ candles — quiet compression, rising volume on the break

The first five are reversal setups and must pass phase + down-wave + support
zone + volume. The sixth is the course's lesson-5 breakout-from-compression
setup, which has no reversal to locate, so instead of a support zone it requires
a rising background — the course's "the background tells you which side of the
range to take".

The ``score`` (0-100) rates the current *setup posture* against the master
algorithm's five decision steps, so a stock sitting in a good place scores well
a few days before a formation completes, while a stock in free fall scores near
zero and so never leans bullish in the analytics summary.

KNOWN SCOPE: like the other example methods, this reproduces the source's own
thresholds (Glinicki teaches on intraday index/FX charts; VSA itself is
interval-agnostic and the course says so explicitly) rather than GPW-tuned
ones. The roadmap requires proving a method on stored GPW history via
``GET /api/stocks/methods/glinicki/backtest`` before it should guide real money.
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

# ── Volume classes ────────────────────────────────────────────────────────────
# The course's one required indicator: a ~20-period moving average of volume,
# which turns a subjective "a lot / a little" into a repeatable classification.
_VOL_MA = 20
# "Ultra-wysoki" — the course's own test for a big-money footprint: volume two
# to three times the average.
_ULTRA_VOL_MULT = 2.0
# "Wysoki".
_HIGH_VOL_MULT = 1.5
# "Podwyzszony" — merely elevated, the bar the two- and three-candle formations
# must clear on their confirming candle.
_ELEVATED_VOL_MULT = 1.2
# "Niski" — matches the VSA engine's own low-volume constant, so the two engines
# speak one language.
_LOW_VOL_MULT = 0.7

# ── Spread / body geometry ────────────────────────────────────────────────────
# Spread is judged RELATIVELY, against the average of the preceding bars.
_SPREAD_MA = 20
# A "long" candle body, in units of that average spread.
_LONG_BODY_SPREADS = 0.5
# Hammer: a small body, at most this fraction of the bar's range.
_SMALL_BODY = 0.33
# Hammer: the body sits in the upper third of the range.
_HAMMER_BODY_FLOOR = 2.0 / 3.0
# Hammer: the upper shadow is "negligible or none".
_NEGLIGIBLE_SHADOW = 0.1
# Hammer: the lower shadow is at least this multiple of the body.
_HAMMER_SHADOW_MULT = 2.0
# Hammer: minimum bar range, in units of the average spread. The Hammer's
# written definition is pure PROPORTIONS (small body, shadow ≥ 2× body,
# negligible upper shadow) and proportions are scale-free, so without this a bar
# whose whole range is a fraction of a normal session matches — and cannot
# possibly have recorded the deep push down and full absorption the formation
# means. Measured on stored GPW history, 16% of matches were bars under half an
# average day's range (median 0.87× vs 1.56-2.00× for every other formation,
# each of which carries an implicit floor through its "long candle" or
# range-engulfing requirement). This applies the course's own foundational rule
# — spread is judged RELATIVELY, "compared to a dozen-odd bars back, not in
# absolute points" — to the one formation whose definition does not restate it.
_HAMMER_MIN_SPREAD = 0.5
# Morning Star: the middle candle's body vs. candle 1's — "a small body or doji".
_STAR_BODY_MAX = 0.35
# Outside Bar: the close must sit at least this far up the range for demand to
# have won the session (the app's VSA engine uses the same 0.65 for its bullish
# close-position default).
_OUTSIDE_CLOSE_POS = 0.65
# Inside Bar: how many consecutive inside bars may form one compression block.
# "A series of inside bars — the longer the compression, the stronger the break."
_INSIDE_MAX_RUN = 5

# ── Background / phase / zone ─────────────────────────────────────────────────
# Prior lows that define the support zone the reversal must happen at.
_ZONE_LOOKBACK = 40
# How close to that prior low the formation must reach, in average spreads.
_ZONE_SPREADS = 1.0
# The down-wave leading into the formation ("only after a clear down-wave")...
_WAVE_LOOKBACK = 10
# ...must have carried price down at least this far.
_WAVE_MIN_DROP = 0.03
# Accumulation test: "the lows stop being deepened". The lows of the last
# _BASE_WINDOW sessions are compared against the lows of the _BASE_PRIOR
# sessions before them.
_BASE_WINDOW = 10
_BASE_PRIOR = 30
_BASE_TOLERANCE = 0.03
# Markup test: price above a rising medium-term average.
_TREND_MA = 50
_TREND_SLOPE_LOOKBACK = 20
# Score rule 4: how many recent sessions the "no supply" read looks at.
_SUPPLY_WINDOW = 5
# Score rule 5: a formation this many calendar days old still counts as fresh.
_RECENT_FIRED = 10
# How far back to scan for the most recent firing when reporting days_since.
_RECENCY_SCAN = 60
# Posture-checklist size the score is scaled against (the master algorithm's
# five decision steps).
_TOTAL_RULES = 5
# Minimum bars to evaluate at all: the binding constraint is the markup test,
# which needs the _TREND_MA average plus _TREND_SLOPE_LOOKBACK sessions of
# slope behind the last bar.
_MIN_BARS = _TREND_MA + _TREND_SLOPE_LOOKBACK  # 70

# Formation families: a reversal must be located at support after a down-wave;
# a breakout out of compression takes its direction from the background instead.
_REVERSAL = "reversal"
_BREAKOUT = "breakout"


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
    """The same series read one bar late, so bar i sees only bars before it.

    Mirrors the VSA engine's ``shift(1)`` on its rolling context columns: no
    rule may look at the bar it is judging when forming that bar's baseline.
    """
    return [None, *list(series[:-1])]


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
    #: Mean spread (high-low) of the _SPREAD_MA bars strictly before each index.
    avg_spread: list[float | None]
    #: Simple moving average of closes ending at each index (the background).
    sma_trend: list[float | None]

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
            sma_trend=_sma_series(closes, _TREND_MA),
        )

    def body(self, i: int) -> float:
        return abs(self.closes[i] - self.opens[i])

    def rng(self, i: int) -> float:
        return self.highs[i] - self.lows[i]

    def context(self, i: int) -> tuple[float, float] | None:
        """(average volume, average spread) before bar ``i``, or None.

        Fails closed on a zero/absent average — a run of frozen zero-spread bars
        during a suspension would otherwise make every "long body" test
        trivially true on the resumption bar.
        """
        avg_v = self.avg_vol[i]
        avg_sp = self.avg_spread[i]
        if avg_v is None or avg_v < 1 or avg_sp is None or avg_sp <= 0:
            return None
        return avg_v, avg_sp


# ── The background gates (master algorithm, steps 1-3) ────────────────────────


def _phase_state(s: _Series, i: int) -> str | None:
    """The market phase as of bar ``i``, or None when it forbids buying.

    The course allows bullish setups in exactly two places — "look for bullish
    signals only in accumulation and on corrections inside an uptrend":

    * **markup** — price above a rising medium-term average, so a dip is a
      correction inside a live uptrend;
    * **accumulation** — sideways after a down-wave, where "the lows stop being
      deepened": the last ``_BASE_WINDOW`` sessions' low is not materially below
      the low of the ``_BASE_PRIOR`` sessions before them.

    Everything else is a markdown still making lower lows, where a bullish
    formation is, in the course's word, noise.
    """
    ma = s.sma_trend[i]
    if ma is not None and ma > 0 and i >= _TREND_SLOPE_LOOKBACK:
        ma_prev = s.sma_trend[i - _TREND_SLOPE_LOOKBACK]
        if ma_prev is not None and s.closes[i] > ma and ma > ma_prev:
            return "markup"

    if i >= _BASE_WINDOW + _BASE_PRIOR - 1:
        recent_low = min(s.lows[i - _BASE_WINDOW + 1 : i + 1])
        prior_low = min(
            s.lows[i - _BASE_WINDOW - _BASE_PRIOR + 1 : i - _BASE_WINDOW + 1]
        )
        if prior_low > 0 and recent_low >= prior_low * (1 - _BASE_TOLERANCE):
            return "accumulation"
    return None


def _down_wave(s: _Series, start: int, form_low: float) -> bool:
    """Whether a clear down-wave led into the formation starting at ``start``.

    Measured from the highest high of the ``_WAVE_LOOKBACK`` sessions BEFORE the
    formation down to the formation's own low, so a violent reversal bar's own
    rally cannot be counted as part of the fall it is supposed to end.
    """
    lo = start - _WAVE_LOOKBACK
    if lo < 0:
        return False
    wave_high = max(s.highs[lo:start])
    return wave_high > 0 and (wave_high - form_low) / wave_high >= _WAVE_MIN_DROP


def _at_support(s: _Series, start: int, form_low: float, i: int) -> bool:
    """Whether the formation reached down into a pre-existing support zone.

    The zone is the lowest low of the ``_ZONE_LOOKBACK`` sessions before the
    formation — a previous low or the lower boundary of the range — and the
    formation must trade within one average spread of it. This is the course's
    step 3: the level is identifiable *before* the signal, which is exactly what
    makes the signal a confirmation rather than a reason.
    """
    lo = start - _ZONE_LOOKBACK
    if lo < 0:
        return False
    ctx = s.context(i)
    if ctx is None:
        return False
    _avg_v, avg_sp = ctx
    prior_low = min(s.lows[lo:start])
    return form_low <= prior_low + _ZONE_SPREADS * avg_sp


def _has_climax(s: _Series, i: int, window: int = _ZONE_LOOKBACK) -> bool:
    """Whether an ultra-high-volume bar sits in the recent background.

    Step 2 of the master algorithm: "where were the ultra-high-volume bars —
    that is where big money holds a position and will defend it".
    """
    for j in range(max(0, i - window + 1), i + 1):
        avg = s.avg_vol[j]
        if avg is not None and avg >= 1 and s.volumes[j] >= _ULTRA_VOL_MULT * avg:
            return True
    return False


# ── The six bullish formations (lessons 3 and 5) ──────────────────────────────


def _hammer(s: _Series, i: int, avg_v: float, avg_sp: float) -> bool:
    """Mlot / Hammer — a single bar whose lower shadow records rejected lows.

    Small body in the upper third of the range, lower shadow at least twice the
    body, negligible upper shadow, body colour irrelevant. Supply pushed price
    deep down during the session and was absorbed in full — and the bar has to
    be big enough for that to have happened at all, hence the relative-spread
    floor (``_HAMMER_MIN_SPREAD``) on top of the shape proportions.

    Volume must be an anomaly in one of the two directions the course allows:
    high or ultra-high (big money absorbing the panic — a selling climax), or
    very low *after an earlier climax* (a test confirming supply has gone).
    Average volume shows nothing and explicitly weakens the formation, so it
    disqualifies it here.
    """
    rng = s.rng(i)
    if rng < _HAMMER_MIN_SPREAD * avg_sp or rng <= 0:
        return False
    body = s.body(i)
    body_low = min(s.opens[i], s.closes[i])
    lower_shadow = body_low - s.lows[i]
    upper_shadow = s.highs[i] - max(s.opens[i], s.closes[i])
    shape = (
        body <= _SMALL_BODY * rng
        and lower_shadow >= _HAMMER_SHADOW_MULT * body
        and upper_shadow <= _NEGLIGIBLE_SHADOW * rng
        and body_low >= s.lows[i] + _HAMMER_BODY_FLOOR * rng
    )
    if not shape:
        return False
    vol = s.volumes[i]
    if vol >= _HIGH_VOL_MULT * avg_v:
        return True
    # The quiet variant is a test, and a test only means something once a
    # climax has already happened somewhere in the background.
    return vol <= _LOW_VOL_MULT * avg_v and _has_climax(s, i - 1)


def _piercing(s: _Series, i: int, avg_v: float, avg_sp: float) -> bool:
    """Przenikanie / Piercing Line — candle 2 takes back over half of candle 1.

    Candle 1 is a long bearish bar; candle 2 opens below its close (ideally with
    a gap) and closes back above the midpoint of its body — but below its open,
    because full recovery is a Bullish Engulfing, a different (stronger)
    formation. Volume on candle 2 must be elevated: low volume there means the
    bounce is only sellers running out, not buyers arriving.
    """
    if i < 1:
        return False
    o1, c1 = s.opens[i - 1], s.closes[i - 1]
    if c1 >= o1:
        return False
    body1 = o1 - c1
    if body1 < _LONG_BODY_SPREADS * avg_sp:
        return False
    return (
        s.closes[i] > s.opens[i]
        and s.opens[i] < c1
        and s.closes[i] > c1 + 0.5 * body1
        and s.closes[i] < o1
        and s.volumes[i] >= _ELEVATED_VOL_MULT * avg_v
    )


def _morning_star(s: _Series, i: int, avg_v: float, avg_sp: float) -> bool:
    """Gwiazda Poranna / Morning Star — three beats: supply, exhaustion, demand.

    Candle 1 long bearish; candle 2 a small body or doji detached below it (its
    whole body under candle 1's close), colour irrelevant; candle 3 bullish,
    closing back above the midpoint of candle 1's body.

    Volume profile: lower on candle 2 than candle 1 — nobody wants to sell down
    there — then rising on candle 3 as demand steps in. The course also accepts
    the opposite reading on candle 2: ultra-high volume with no price progress
    is absorption, which is equally bullish (effort without result).
    """
    if i < 2:
        return False
    o1, c1 = s.opens[i - 2], s.closes[i - 2]
    if c1 >= o1:
        return False
    body1 = o1 - c1
    if body1 < _LONG_BODY_SPREADS * avg_sp:
        return False
    star_top = max(s.opens[i - 1], s.closes[i - 1])
    if s.body(i - 1) > _STAR_BODY_MAX * body1 or star_top >= c1:
        return False
    if not (s.closes[i] > s.opens[i] and s.closes[i] > c1 + 0.5 * body1):
        return False
    v1, v2, v3 = s.volumes[i - 2], s.volumes[i - 1], s.volumes[i]
    star_ok = v2 < v1 or v2 >= _ULTRA_VOL_MULT * avg_v
    return star_ok and v3 > v2 and v3 >= avg_v


def _bullish_engulfing(s: _Series, i: int, avg_v: float) -> bool:
    """Objecie hossy / Bullish Engulfing — one bar undoes the whole prior bar.

    Candle 2's body covers candle 1's body completely. The course calls this the
    least ambiguous of the two-candle formations: there is no percentage of
    penetration left to argue about.

    The volume condition is critical, not decorative: the engulfing candle's
    volume must be clearly higher than the engulfed one's *and* genuinely
    elevated. An engulfing on falling volume is an empty move — a wide spread
    with no capital behind it, the classic trap.
    """
    if i < 1:
        return False
    o1, c1 = s.opens[i - 1], s.closes[i - 1]
    return (
        c1 < o1
        and s.closes[i] > s.opens[i]
        and s.opens[i] <= c1
        and s.closes[i] >= o1
        and s.body(i) > s.body(i - 1)
        and s.volumes[i] > s.volumes[i - 1]
        and s.volumes[i] >= _ELEVATED_VOL_MULT * avg_v
    )


def _outside_bar(s: _Series, i: int, avg_v: float) -> bool:
    """Outside Bar resolved upwards — an explosion of volatility demand won.

    The bar takes out both extremes of the previous one: supply and demand
    fought openly and the CLOSE settles it. A close in the upper part of the
    range means demand won; after a down-wave that is a climax and a change of
    control, the same event the VSA engine reads as a selling climax.

    Volume must always be elevated — a wide spread with no volume is internally
    contradictory and disqualifies the bar.
    """
    if i < 1:
        return False
    rng = s.rng(i)
    if rng <= 0:
        return False
    close_pos = (s.closes[i] - s.lows[i]) / rng
    return (
        s.highs[i] > s.highs[i - 1]
        and s.lows[i] < s.lows[i - 1]
        and close_pos >= _OUTSIDE_CLOSE_POS
        and s.volumes[i] >= _ELEVATED_VOL_MULT * avg_v
    )


def _inside_mother(s: _Series, i: int) -> int | None:
    """Index of the mother bar of the compression block ending at ``i - 1``.

    An inside bar is contained entirely within the previous bar's range. A run
    of them is one compression block against the same mother bar, and the course
    notes the longer the compression the stronger the break, so the deepest
    valid mother (up to ``_INSIDE_MAX_RUN`` inside bars) is returned. None when
    bar ``i - 1`` is not an inside bar at all.
    """
    mother: int | None = None
    m = i - 2
    while m >= 0 and (i - 1 - m) <= _INSIDE_MAX_RUN:
        inside = all(
            s.highs[k] < s.highs[m] and s.lows[k] > s.lows[m] for k in range(m + 1, i)
        )
        if not inside:
            break
        mother = m
        m -= 1
    return mother


def _inside_breakout(s: _Series, i: int, avg_v: float, mother: int) -> bool:
    """The upside break of an Inside Bar compression range.

    Direction is given by the market itself, breaking one side of the mother
    bar's range; only the upside is taken here (long-only). The course's volume
    filter is the whole point of the setup: "the break must come on rising
    volume — a break on low volume is a candidate for a false one, there is no
    capital behind it".
    """
    return (
        s.closes[i] > s.highs[mother]
        and s.volumes[i] > s.volumes[i - 1]
        and s.volumes[i] >= _ELEVATED_VOL_MULT * avg_v
    )


def _formation_at(s: _Series, i: int) -> tuple[str, str, int] | None:
    """The bullish formation completing on bar ``i``: (label, family, start bar).

    At most one formation per bar, strongest first, mirroring the VSA engine's
    "each bar matches at most one pattern" rule: a Morning Star's three candles
    of confirmation outrank a two-candle formation, a full Engulfing outranks a
    partial Piercing, and the body formations of lesson 3 outrank the bar
    formations of lesson 5 they overlap with.
    """
    ctx = s.context(i)
    if ctx is None:
        return None
    avg_v, avg_sp = ctx

    if _morning_star(s, i, avg_v, avg_sp):
        return "Morning Star", _REVERSAL, i - 2
    if _bullish_engulfing(s, i, avg_v):
        return "Bullish Engulfing", _REVERSAL, i - 1
    if _piercing(s, i, avg_v, avg_sp):
        return "Piercing Line", _REVERSAL, i - 1
    if _outside_bar(s, i, avg_v):
        return "Outside Bar", _REVERSAL, i - 1
    if _hammer(s, i, avg_v, avg_sp):
        return "Hammer", _REVERSAL, i
    mother = _inside_mother(s, i)
    if mother is not None and _inside_breakout(s, i, avg_v, mother):
        return "Inside Bar breakout", _BREAKOUT, mother
    return None


def _setup_at(s: _Series, i: int) -> str | None:
    """The complete, gated Glinicki setup firing on bar ``i``, or None.

    A formation alone is never enough. The course's three disqualifiers are
    applied here, each fatal on its own:

    * out of phase — no bullish setup outside accumulation or a markup pullback;
    * outside the zone — a reversal must reach a support level identified from
      the bars before it, after a genuine down-wave;
    * unconfirmed by volume — already enforced inside each formation.

    The breakout family has no reversal to locate, so in place of a support zone
    it requires the rising background that gives the break its direction.
    """
    form = _formation_at(s, i)
    if form is None:
        return None
    label, family, start = form
    phase = _phase_state(s, i)

    if family == _BREAKOUT:
        return label if phase == "markup" else None

    if phase is None:
        return None
    form_low = min(s.lows[start : i + 1])
    if not _down_wave(s, start, form_low):
        return None
    if not _at_support(s, start, form_low, i):
        return None
    return label


# ── Setup posture (the score) ─────────────────────────────────────────────────


def _in_zone_now(s: _Series, i: int) -> bool:
    """Whether bar ``i`` itself is trading in the support zone."""
    lo = i - _ZONE_LOOKBACK
    if lo < 0:
        return False
    ctx = s.context(i)
    if ctx is None:
        return False
    _avg_v, avg_sp = ctx
    return s.lows[i] <= min(s.lows[lo:i]) + _ZONE_SPREADS * avg_sp


def _supply_dried_up(s: _Series, i: int) -> bool:
    """Whether supply has stopped showing over the last few sessions.

    "No Supply" from the course's signal catalogue: every recent down-bar came
    on below-average volume, i.e. nobody is willing to sell lower. A window with
    no down-bars at all also passes — there is no supply on show either way.
    """
    start = max(1, i - _SUPPLY_WINDOW + 1)
    for j in range(start, i + 1):
        avg = s.avg_vol[j]
        if avg is None or avg < 1:
            return False
        if s.closes[j] < s.closes[j - 1] and s.volumes[j] > avg:
            return False
    return True


def _posture_rules(s: _Series, i: int, days_since: int) -> int:
    """How many of the master algorithm's five steps currently line up (0-5)."""
    checks = (
        _phase_state(s, i) is not None,  # 1 phase allows buying at all
        _in_zone_now(s, i),  # 2 price is at an identified level
        _has_climax(s, i),  # 3 big money left a footprint nearby
        _supply_dried_up(s, i),  # 4 effort vs result: no supply showing
        days_since <= _RECENT_FIRED,  # 5 a formation fired recently
    )
    return sum(1 for ok in checks if ok)


@register_method
class VsaGlinicki(TradingMethod):
    id = "glinicki"
    order = 40
    name = "VSA Glinicki V1"
    description = (
        "The buying half of Rafal Glinicki's VSA course, applied end-to-end as "
        "he teaches it. It only looks for a buy where the course allows one — "
        "in accumulation after a sell-off, or on a dip inside an uptrend — and "
        "only at a support level marked out by earlier bars. There it waits for "
        "one of his six bullish formations (Hammer, Piercing Line, Morning "
        "Star, Bullish Engulfing, a bullish Outside Bar, or a break out of an "
        "Inside Bar squeeze), and each one must be confirmed by volume against "
        "the 20-day average: the whole method rests on effort versus result. "
        "The score rates how well the current setup lines up with those five "
        "steps; a recent example means a full formation completed lately. "
        "Long-only, so the course's mirror-image selling formations are left "
        "out. (Faithful to the source's own thresholds; still needs a GPW "
        "back-test before it should guide real money.)"
    )
    source = (
        "Rafal Glinicki — Kurs inwestowania metoda VSA (XTB Polska, 5 lessons), "
        "after Tom Williams (Master the Markets) and Richard Wyckoff"
    )
    source_url = (
        "https://www.youtube.com/playlist?list=PLKbpCaHB0CJYDfHo_c0rd9jbHfO8uF2jn"
    )

    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,  # Glinicki's own thresholds; unused
        *,
        rs_rank: float | None = None,  # cross-sectional; not used by this method
    ) -> MethodResult:
        if len(bars) < _MIN_BARS:
            return MethodResult.unavailable("Not enough history")

        s = _Series.build(bars)
        last_idx = len(bars) - 1
        last_date = bars[last_idx].date

        # Recency: the most recent bar a complete setup fired on. days_since == 0
        # (a setup on the last bar) is exactly ``fired``.
        days_since = NEVER_FIRED
        label: str | None = None
        floor = max(_MIN_BARS - 1, last_idx - _RECENCY_SCAN)
        for i in range(last_idx, floor - 1, -1):
            hit = _setup_at(s, i)
            if hit is not None:
                days_since = (last_date - bars[i].date).days
                label = hit
                break

        passed = _posture_rules(s, last_idx, days_since)
        score = round(passed / _TOTAL_RULES * 100)
        fired = days_since == 0

        if fired and label is not None:
            detail = label
        elif label is not None:
            detail = f"{label} {days_since}d ago"
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
        """A marker on every bar a complete Glinicki setup fired on, oldest first.

        Each firing is its own event — the course treats a second formation at
        the same level as accumulating evidence, not as a duplicate — so unlike
        the breakout overlay there is no "only mark where it turns on" filter.
        Every marker is labelled with the formation that fired.
        """
        if len(bars) < _MIN_BARS:
            return []
        s = _Series.build(bars)
        out: list[MethodSignal] = []
        for i in range(_MIN_BARS - 1, len(bars)):
            label = _setup_at(s, i)
            if label is not None:
                out.append(MethodSignal(date=bars[i].date, label=label, type="Bullish"))
        return out
