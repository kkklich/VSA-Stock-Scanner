"""Volume Spread Analysis (VSA) signal detection and rating.

VSA reads three variables per bar — spread (high − low), the close's position
within that spread, and volume — to infer whether professional money is
accumulating (strength) or distributing (weakness). See agent/DOCUMENTATION.md §7
and the Tom Williams reference text in the agent/ folder.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.models import StooqDailyQuote, VsaSettings


class SignalType(str, enum.Enum):
    """Whether a VSA signal points to strength (bullish) or weakness (bearish)."""

    BULLISH = "Bullish"
    BEARISH = "Bearish"


class SignalName(str, enum.Enum):
    """The VSA patterns the scanner detects (DOCUMENTATION.md §7)."""

    SPRING = "Spring"
    SUCCESSFUL_TEST = "Successful Test"
    SOS = "SOS"  # Sign of Strength
    UPTHRUST = "Upthrust"
    NO_DEMAND = "No Demand"
    SOW = "SOW"  # Sign of Weakness


@dataclass(frozen=True)
class VsaSignal:
    """A single detected VSA pattern on a given session."""

    date: date
    signal_name: SignalName
    type: SignalType
    # Detection confidence 0.0–1.0; feeds the Time-Decay-weighted rating.
    strength: float = field(default=1.0)


# ── Detection configuration ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SignalParams:
    """Detection thresholds for one VSA pattern.

    The multipliers are interpreted per pattern (see the rules in
    ``detect_signals``):

    - ``spread_mult`` — bar spread vs. the rolling average spread. A *minimum*
      for wide-spread patterns (Spring, SOS, Upthrust, SOW) and a *maximum*
      for No Demand (which needs a narrow bar). Unused by Successful Test.
    - ``vol_mult`` — bar volume vs. the rolling average volume. A *minimum*
      for high-volume patterns (SOS, SOW, and the high-volume legs of Spring
      and Upthrust) and a *maximum* for the quiet patterns (Successful Test,
      No Demand).
    - ``close_pos`` — where the close must sit within the bar's range,
      0.0 = low, 1.0 = high. A minimum for bullish patterns, a maximum for
      bearish ones.
    - ``lookback`` — how many prior sessions define the rolling context
      (average spread/volume and the support/resistance levels).
    """

    enabled: bool = True
    spread_mult: float = 1.5
    vol_mult: float = 1.5
    close_pos: float = 0.65
    lookback: int = 20


# Default thresholds per signal — these reproduce the original hardcoded rules.
DEFAULT_SIGNAL_PARAMS: dict[SignalName, SignalParams] = {
    SignalName.SPRING: SignalParams(spread_mult=1.2, vol_mult=1.2, close_pos=0.6),
    SignalName.SOS: SignalParams(spread_mult=1.5, vol_mult=1.5, close_pos=0.65),
    SignalName.SUCCESSFUL_TEST: SignalParams(spread_mult=1.0, vol_mult=0.7, close_pos=0.65),
    SignalName.UPTHRUST: SignalParams(spread_mult=1.2, vol_mult=1.3, close_pos=0.3),
    SignalName.SOW: SignalParams(spread_mult=1.5, vol_mult=1.5, close_pos=0.35),
    SignalName.NO_DEMAND: SignalParams(spread_mult=0.7, vol_mult=0.7, close_pos=0.65),
}

# "Low volume" for the quiet legs of Spring and Upthrust (fixed, not tunable —
# Master the Markets treats "low" simply as clearly below average).
_LOW_VOL_MULT = 0.7

# Upper volume bound for the wide-spread climax-prone patterns (SOS, the
# high-volume Spring, SOW). Master the Markets: volume on an up-bar "should not
# be excessive, as this is indicative of supply in the background" — at
# ultra-high volume a wide up-bar is a potential buying climax (a sign of
# weakness), and the mirror image holds for a wide down-bar, where climactic
# volume is potential "stopping volume" (professional buying into the panic —
# budding strength). Volume above this multiple of the average therefore
# disqualifies the pattern's straightforward reading.
_EXCESSIVE_VOL_MULT = 4.0

# ── Trend-context (background) gate ───────────────────────────────────────────
# Master the Markets insists a signal is only meaningful read against the
# background: strength shown while the background is weak, or weakness shown
# while it is strong. We approximate the background with a moving average of the
# closes over this many prior sessions (no look-ahead — the average is of bars
# strictly before the one being judged).
_TREND_LOOKBACK = 30
# Neutral band around that average, as a fraction. The background is only called
# "bullish" / "bearish" when the close is clearly (this far) above / below the
# average; within the band it is "neutral". A generous band means the gate
# "suppresses only when the background clearly contradicts" the signal, rather
# than silencing borderline cases.
_TREND_BAND = 0.03

# Maximum penetration below support, in units of the average spread, for the
# quiet bullish dips: the low-volume Spring and the Successful Test. The
# canonical low-volume spring penetrates support only SHALLOWLY; a deeper
# low-volume break below support is a breakdown, not a bullish test of supply.
# Shared by both rules so they meet without a gap between them.
_SHALLOW_PENETRATION_SPREADS = 0.5


def _excessive_cap(p: SignalParams) -> float:
    """Effective climax-volume cap for one rule, as a multiple of average volume.

    The fixed 4.0× default must never fall below the rule's own high-volume
    threshold: with a user-raised ``vol_mult`` at or above 4.0 a fixed cap
    would make ``vol > avg × vol_mult and vol <= avg × 4.0`` unsatisfiable and
    the signal would silently disappear, so the cap stays at least 1.5× above
    ``vol_mult`` (default settings keep the plain 4.0 behaviour).
    """
    return max(_EXCESSIVE_VOL_MULT, p.vol_mult * 1.5)


@dataclass(frozen=True)
class VsaConfig:
    """Complete detection configuration: per-signal thresholds and toggles."""

    params: Mapping[SignalName, SignalParams] = field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_PARAMS)
    )
    # Read each bar's signal against its background trend (Master the Markets:
    # a signal only means what the background lets it mean). When on (the
    # default), a bullish pattern is suppressed in a clearly bearish background
    # and vice versa, and ultra-high-volume up-bars in new-high ground are read
    # as buying climaxes rather than strength. There is no API/frontend control
    # for this yet, so in practice it is always True — it exists so the gate can
    # be turned off in code/tests and so the default hashes as "default".
    use_trend_context: bool = True

    @classmethod
    def default(cls) -> VsaConfig:
        return cls()

    def for_signal(self, name: SignalName) -> SignalParams:
        return self.params.get(name, DEFAULT_SIGNAL_PARAMS[name])

    def is_default(self) -> bool:
        return self.use_trend_context is True and all(
            self.for_signal(name) == DEFAULT_SIGNAL_PARAMS[name] for name in SignalName
        )

    def cache_suffix(self) -> str:
        """Stable short hash for cache keys; empty string for the default config.

        Keeping the default suffix empty means existing cache keys (and the
        nightly pre-warmed ranking) keep working unchanged. ``use_trend_context``
        defaults to True, so a default config still returns "" — only a config
        that actually deviates (custom thresholds, or the gate disabled) gets a
        non-empty suffix.
        """
        if self.is_default():
            return ""
        canonical = json.dumps(
            {
                "use_trend_context": self.use_trend_context,
                "params": {
                    name.value: [
                        p.enabled, p.spread_mult, p.vol_mult, p.close_pos, p.lookback,
                    ]
                    for name in SignalName
                    for p in [self.for_signal(name)]
                },
            },
            sort_keys=True,
        )
        return ":" + hashlib.md5(canonical.encode()).hexdigest()[:10]


# History-sufficiency gate (NOT a per-signal warm-up): a series must hold at
# least this many bars beyond the smallest rolling lookback before the scan runs
# at all, so a full rolling context window (average spread/volume, support and
# resistance) exists. It bounds the *length* of the series; the scan loop itself
# begins at the first bar that has a complete lookback window behind it, so no
# early signal is dropped by this buffer.
_WARMUP_BARS = 5

# Maps the Scanner page rule ids (API payload keys) to engine signal names.
_SETTINGS_KEY_TO_SIGNAL: dict[str, SignalName] = {
    "spring": SignalName.SPRING,
    "sos": SignalName.SOS,
    "test": SignalName.SUCCESSFUL_TEST,
    "upthrust": SignalName.UPTHRUST,
    "nodemand": SignalName.NO_DEMAND,
    "sow": SignalName.SOW,
}


def config_from_settings(settings: VsaSettings | None) -> VsaConfig:
    """Build a ``VsaConfig`` from the API settings payload.

    Missing signals or fields keep their defaults, so a partial payload only
    overrides what the user actually changed. ``close_pos`` arrives as a
    percentage (0–100) and is converted to the 0.0–1.0 fraction used here.
    """
    if settings is None:
        return VsaConfig.default()

    params = dict(DEFAULT_SIGNAL_PARAMS)
    for key, name in _SETTINGS_KEY_TO_SIGNAL.items():
        s = getattr(settings, key)
        if s is None:
            continue
        d = DEFAULT_SIGNAL_PARAMS[name]
        params[name] = SignalParams(
            enabled=s.enabled,
            spread_mult=s.spread_mult if s.spread_mult is not None else d.spread_mult,
            vol_mult=s.vol_mult if s.vol_mult is not None else d.vol_mult,
            close_pos=s.close_pos / 100.0 if s.close_pos is not None else d.close_pos,
            lookback=s.lookback if s.lookback is not None else d.lookback,
        )
    return VsaConfig(params=params)


def detect_signals(
    bars: Sequence[StooqDailyQuote],
    config: VsaConfig | None = None,
) -> list[VsaSignal]:
    """Scan a chronological OHLCV series for VSA patterns and return them in date order.

    Each rule matches at most one pattern per bar (highest priority wins), so a bar
    cannot simultaneously be a Spring and a No-Demand bar.

    ``config`` supplies per-signal thresholds and on/off toggles (the Scanner
    page settings); when omitted, the documented default rules apply.

    Requires at least ``lookback + 5`` bars for the smallest enabled lookback
    (rolling context + warm-up buffer). Returns an empty list when there is
    not enough history or every signal is disabled.
    """
    cfg = config or VsaConfig.default()
    active: dict[SignalName, SignalParams] = {
        name: cfg.for_signal(name) for name in SignalName if cfg.for_signal(name).enabled
    }
    if not active:
        return []

    min_lookback = min(p.lookback for p in active.values())
    if len(bars) < min_lookback + _WARMUP_BARS:
        return []

    df = pd.DataFrame(
        [
            {
                "date": b.date,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars
        ]
    ).sort_values("date").reset_index(drop=True)

    # Per-bar derived columns.
    df["spread"] = df["high"] - df["low"]
    # The close's position is undefined on a zero-spread (frozen) bar: leave it
    # NaN so every rule's close_pos comparison fails closed. Mirrors
    # ``statistics.close_position``, which returns None when high == low.
    df["close_pos"] = ((df["close"] - df["low"]) / df["spread"]).where(df["spread"] > 0)

    # Rolling context, one set of columns per distinct lookback in use
    # (shift(1) so each bar sees *prior* bars only, no lookahead).
    for lb in {p.lookback for p in active.values()}:
        df[f"avg_spread_{lb}"] = df["spread"].rolling(lb).mean().shift(1)
        df[f"avg_vol_{lb}"] = df["volume"].rolling(lb).mean().shift(1)
        df[f"prior_low_{lb}"] = df["low"].rolling(lb).min().shift(1)
        df[f"prior_high_{lb}"] = df["high"].rolling(lb).max().shift(1)

    # Previous-bar context. VSA defines an up-bar as a close *above the previous
    # bar's close* (not above its own open) — Master the Markets p.31 — so every
    # direction check below compares against prev_close.
    df["prev_close"] = df["close"].shift(1)
    df["prev_low"] = df["low"].shift(1)
    # "Volume lower than the previous two bars" (TradeGuider criterion for
    # No Demand / a Test) means lower than BOTH, i.e. below their minimum.
    df["prev_vol_min2"] = df["volume"].rolling(2).min().shift(1)

    # Background trend context: the average close over the prior _TREND_LOOKBACK
    # sessions (shift(1) → no look-ahead). NaN until enough history exists, in
    # which case the background is treated as "neutral" (unknown → do not
    # suppress).
    use_trend = cfg.use_trend_context
    df["trend_ma"] = df["close"].rolling(_TREND_LOOKBACK).mean().shift(1)

    def background(row: pd.Series) -> str:
        """The bar's background trend: 'bullish', 'bearish' or 'neutral'.

        Read from the trend LEADING INTO the bar — the *previous* close vs the
        trailing average — never the current bar's own close, so a strong
        breakout bar's own thrust cannot inflate its background (that would make
        every excessive-volume range breakout look 'extended'). 'neutral' when
        the gate is disabled, when there is not yet enough history for the trend
        average, or when the prior close sits within the neutral band around it —
        so a signal is suppressed only when the background *clearly* contradicts
        it.
        """
        if not use_trend:
            return "neutral"
        ma = row["trend_ma"]
        ref = row["prev_close"]
        if pd.isna(ma) or ma <= 0 or pd.isna(ref):
            return "neutral"
        if ref >= ma * (1 + _TREND_BAND):
            return "bullish"
        if ref <= ma * (1 - _TREND_BAND):
            return "bearish"
        return "neutral"

    def trend_available(row: pd.Series) -> bool:
        """Whether a usable background reading exists for this bar."""
        return use_trend and not pd.isna(row["trend_ma"]) and row["trend_ma"] > 0

    def ctx(row: pd.Series, lb: int) -> tuple[float, float, float, float] | None:
        """Rolling context for one lookback, or None when not yet available.

        Also fails closed when the rolling average spread is NaN or <= 0
        (e.g. after a run of frozen zero-spread bars during a suspension):
        every rule compares the bar's spread against ``avg_sp``, and a zero
        average would make the wide-spread conditions trivially true, so a
        resumption bar would fire false Springs/Upthrusts.
        """
        avg_v = row[f"avg_vol_{lb}"]
        avg_sp = row[f"avg_spread_{lb}"]
        if pd.isna(avg_v) or avg_v < 1 or pd.isna(avg_sp) or avg_sp <= 0:
            return None
        return (avg_sp, avg_v, row[f"prior_low_{lb}"], row[f"prior_high_{lb}"])

    signals: list[VsaSignal] = []

    for i in range(min_lookback + 1, len(df)):
        row = df.iloc[i]

        cp = row["close_pos"]
        spread = row["spread"]
        vol = row["volume"]
        prev_close = row["prev_close"]
        prev_low = row["prev_low"]
        prev_vol_min2 = row["prev_vol_min2"]
        d = row["date"]
        # Background trend for this bar (see the gate note above). ``bg`` gates
        # which patterns may fire; ``trend_ok`` says whether the climax
        # reclassification (which needs a real background reading) can run.
        bg = background(row)
        trend_ok = trend_available(row)

        matched: VsaSignal | None = None

        # ── Bullish patterns (evaluated highest-priority first) ───────────

        # Spring — a break below prior support that reverses to close back
        # above it, near the bar's high. Two valid volume regimes:
        #   * high volume + wide spread — professional money absorbing the
        #     panic selling it just shook out. This is Master the Markets'
        #     "Shake-out", which the book describes as an explicitly
        #     HIGH-volume event. Volume must still not be excessive
        #     (_excessive_cap): the book warns that excessive volume on
        #     an up-move indicates supply in the background (climactic
        #     action), which negates the bullish reading.
        #   * low volume — the break attracted no sellers at all ("no
        #     supply"). This variant is Wyckoff canon (the classic shallow
        #     spring), NOT Master the Markets' shake-out; the canonical
        #     low-volume spring penetrates support only SHALLOWLY, so the
        #     dip below support is capped at _SHALLOW_PENETRATION_SPREADS
        #     average spreads. Its spread is usually modest, so no
        #     wide-spread requirement.
        # Average, unremarkable volume shows no anomaly and does not qualify.
        # Trend gate: a Spring is a bullish structure, so it is suppressed when
        # the background is clearly bearish (a break in a downtrend is a
        # breakdown, not accumulation).
        if matched is None and SignalName.SPRING in active and bg != "bearish":
            p = active[SignalName.SPRING]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, prior_low, _ = c
                if (
                    prior_low > 0
                    and row["low"] <= prior_low
                    and row["close"] > prior_low
                    and cp > p.close_pos
                    and (
                        (
                            spread > avg_sp * p.spread_mult
                            and vol > avg_v * p.vol_mult
                            and vol <= avg_v * _excessive_cap(p)
                        )
                        or (
                            vol < avg_v * _LOW_VOL_MULT
                            and (prior_low - row["low"])
                            <= _SHALLOW_PENETRATION_SPREADS * avg_sp
                        )
                    )
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.SPRING,
                        type=SignalType.BULLISH, strength=0.9,
                    )

        # SOS — a wide up-bar on high volume closing near the high that pushes
        # up THROUGH an old area of supply. Two refinements over a plain
        # wide-up-bar:
        #   * (2b) it must break resistance — the close clears the prior rolling
        #     high — because an SOS is "pushing up through supply", not just a
        #     strong bar somewhere inside the range.
        #   * (2c) at ultra-high (excessive) volume the reading depends on the
        #     background. Master the Markets: a buying climax is a top only "in
        #     new high ground". When the background is already extended (bullish)
        #     the excessive-volume up-bar is a buying climax → reclassified
        #     bearish; when it is merely breaking out of a range (neutral
        #     background) the cap is lifted and it stays a valid SOS. With no
        #     usable background (too little history) we keep the original
        #     conservative behaviour: excessive volume yields no signal.
        if matched is None and SignalName.SOS in active:
            p = active[SignalName.SOS]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, prior_high = c
                wide_strong_up = (
                    spread > avg_sp * p.spread_mult
                    and vol > avg_v * p.vol_mult
                    and cp > p.close_pos
                    and row["close"] > prev_close
                )
                breaks_resistance = prior_high > 0 and row["close"] > prior_high
                if wide_strong_up and breaks_resistance:
                    excessive = vol > avg_v * _excessive_cap(p)
                    if not excessive:
                        matched = VsaSignal(
                            date=d, signal_name=SignalName.SOS,
                            type=SignalType.BULLISH, strength=1.0,
                        )
                    elif trend_ok and bg == "bullish":
                        # Buying climax in new high ground — reuse Upthrust, the
                        # app's bearish "distribution at the highs" structure.
                        # (Caveat of the reuse: a climax closes strong, whereas a
                        # textbook upthrust closes on its low — but both are
                        # bearish supply at new highs and map to "Strong Sell".)
                        matched = VsaSignal(
                            date=d, signal_name=SignalName.UPTHRUST,
                            type=SignalType.BEARISH, strength=0.85,
                        )
                    elif trend_ok:
                        # Breaking out of a range on a volume surge (not extended)
                        # — the climax cap is lifted, still a valid SOS.
                        matched = VsaSignal(
                            date=d, signal_name=SignalName.SOS,
                            type=SignalType.BULLISH, strength=1.0,
                        )

        # Successful Test ("no supply") — Master the Markets p.35: "Any
        # down-move dipping into an area of previous selling (previous high
        # volume level), which then regains to close on, or near the high, on
        # lower volume ... This is a successful test." The bar dips below the
        # previous bar's low, finds no sellers, and closes near its high.
        # "Area of previous selling" is approximated by requiring the dip to
        # reach the lower quartile of the recent lookback range — an
        # engineering proxy, since the exact prior high-volume price levels
        # are not tracked; without it a shallow dip anywhere on the chart
        # would qualify. The dip is also bounded from below with the same
        # _SHALLOW_PENETRATION_SPREADS limit the low-volume Spring uses: a
        # test dips INTO old selling, it does not collapse through support —
        # a deep low-volume break below the range is a breakdown and must
        # not be read as bullish. Volume must be genuinely low: below the
        # rolling average (× vol_mult) AND lower than both of the previous
        # two bars (the standard TradeGuider criterion).
        # Trend gate: a successful test is bullish, so it is suppressed in a
        # clearly bearish background (a test of supply only "passes" as strength
        # when the background is not itself falling apart).
        if matched is None and SignalName.SUCCESSFUL_TEST in active and bg != "bearish":
            p = active[SignalName.SUCCESSFUL_TEST]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, prior_low, prior_high = c
                if (
                    row["low"] < prev_low
                    and prior_high > prior_low
                    and row["low"] <= prior_low + 0.25 * (prior_high - prior_low)
                    and (prior_low - row["low"])
                    <= _SHALLOW_PENETRATION_SPREADS * avg_sp
                    and cp >= p.close_pos
                    and vol < avg_v * p.vol_mult
                    and vol < prev_vol_min2
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.SUCCESSFUL_TEST,
                        type=SignalType.BULLISH, strength=0.75,
                    )

        # ── Bearish patterns ─────────────────────────────────────────────

        # Upthrust — bar spikes above resistance then closes back below it, on
        # a wide spread, "on or very near the lows" (Master the Markets p.78:
        # "the day must close on or very near the lows; the volume can be
        # either low (no demand) or high (supply overcoming the demand)").
        # High volume means real supply hit the breakout; low volume means a
        # hollow fake-out with no genuine buying behind it. Either is a valid
        # trap; only "average, unremarkable" volume is excluded — the book's
        # own example (p.66) of an average-volume up-thrust sees the market
        # simply continue upwards.
        # Trend gate: an upthrust is bearish, so it is suppressed when the
        # background is clearly bullish (a poke above resistance inside a strong
        # uptrend usually just resolves upward — the book's average-volume case).
        if matched is None and SignalName.UPTHRUST in active and bg != "bullish":
            p = active[SignalName.UPTHRUST]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, prior_high = c
                if (
                    prior_high > 0
                    and row["high"] >= prior_high
                    and row["close"] < prior_high
                    and cp < p.close_pos
                    and spread > avg_sp * p.spread_mult
                    and (vol > avg_v * p.vol_mult or vol < avg_v * _LOW_VOL_MULT)
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.UPTHRUST,
                        type=SignalType.BEARISH, strength=0.85,
                    )

        # SOW — wide down-bar on high volume closing near the low. Mirrors the
        # SOS handling of excessive volume: at ultra-high volume a wide down-bar
        # into new-low ground with a clearly bearish background is potential
        # "stopping volume" — professional money buying into the capitulation
        # (budding strength), not clean weakness — so no SOW is emitted there.
        # Elsewhere (excessive volume but NOT in extended new-low ground) the
        # climax cap is lifted and it is a valid SOW; with no usable background
        # the original conservative behaviour holds (excessive → no signal). We
        # deliberately do NOT emit a fresh *bullish* signal off a wide down-close
        # bar — too aggressive a read for end-of-day data. (The Upthrust remains
        # uncapped: an upthrust on ultra-high volume is still legitimately
        # bearish.)
        if matched is None and SignalName.SOW in active:
            p = active[SignalName.SOW]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, prior_low, _ = c
                wide_weak_down = (
                    spread > avg_sp * p.spread_mult
                    and vol > avg_v * p.vol_mult
                    and cp < p.close_pos
                    and row["close"] < prev_close
                )
                if wide_weak_down:
                    excessive = vol > avg_v * _excessive_cap(p)
                    stopping_volume = (
                        trend_ok
                        and bg == "bearish"
                        and prior_low > 0
                        and row["low"] < prior_low
                    )
                    if not excessive:
                        matched = VsaSignal(
                            date=d, signal_name=SignalName.SOW,
                            type=SignalType.BEARISH, strength=1.0,
                        )
                    elif trend_ok and not stopping_volume:
                        # Excessive volume but not extended selling into new lows
                        # — cap lifted, still a valid SOW.
                        matched = VsaSignal(
                            date=d, signal_name=SignalName.SOW,
                            type=SignalType.BEARISH, strength=1.0,
                        )
                    # else: (excessive & stopping volume) or (excessive & no
                    # background) → no signal.

        # No Demand — narrow up-bar on low volume; professionals not
        # participating. Master the Markets p.32: "a low volume up-bar, on a
        # narrow spread"; the TradeGuider criterion adds that the volume must
        # be lower than both of the previous two bars and the close in the
        # middle or low — a bar closing strongly on its own high isn't a
        # No Demand bar even if narrow and quiet.
        # Trend gate: No Demand is bearish (lack of professional buying), so it
        # is suppressed when the background is clearly bullish — a quiet narrow
        # up-bar during a strong advance is an unremarkable pause, not a warning.
        if matched is None and SignalName.NO_DEMAND in active and bg != "bullish":
            p = active[SignalName.NO_DEMAND]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, _ = c
                if (
                    row["close"] > prev_close
                    and spread < avg_sp * p.spread_mult
                    and vol < avg_v * p.vol_mult
                    and vol < prev_vol_min2
                    and cp < p.close_pos
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.NO_DEMAND,
                        type=SignalType.BEARISH, strength=0.6,
                    )

        if matched is not None:
            signals.append(matched)

    return signals


def _net_score(
    signals: Sequence[VsaSignal],
    as_of: date,
    half_life_days: int = 30,
) -> float:
    """Time-decayed net signal score: > 0 = net bullish, < 0 = net bearish.

    Each signal contributes its strength weighted by exponential decay
    (halved every ``half_life_days``); bearish signals contribute negatively.
    Future-dated signals are ignored. Shared by ``compute_rating`` and
    ``verdict_from_signals`` so the rating and the verdict badge can never
    contradict each other.
    """
    lam = math.log(2) / half_life_days
    net = 0.0
    for s in signals:
        days_ago = (as_of - s.date).days
        if days_ago < 0:
            continue  # future-dated signal; skip
        weight = math.exp(-lam * days_ago) * s.strength
        net += weight if s.type == SignalType.BULLISH else -weight
    return net


def compute_rating(
    signals: Sequence[VsaSignal],
    as_of: date,
    half_life_days: int = 30,
) -> int:
    """Collapse detected signals into a 0–100 VSA rating, applying Time Decay.

    Each signal contributes a positive (bullish) or negative (bearish) score
    weighted by exponential decay. The net score is then mapped to 0–100 via
    tanh (halved so a single signal never saturates the badge scale — VSA
    treats isolated signals, especially No Demand, as needing confirmation):

        net ≈  0    → rating ≈ 50  (neutral)
        net ≈ -0.6  → rating ≈ 35  (one fresh No Demand — caution, not red)
        net ≈ +1    → rating ≈ 73  (one fresh strong bullish signal)
        net ≈ -1    → rating ≈ 27  (one fresh strong bearish signal)
        net ≈ +3    → rating ≈ 95  (cluster of confirming bullish signals)

    ``half_life_days`` is the number of days after which a signal's influence
    is halved (default 30 ≈ one calendar month).
    """
    if not signals:
        return 50

    net_score = _net_score(signals, as_of, half_life_days)
    return max(0, min(100, round(50.0 + 50.0 * math.tanh(net_score / 2.0))))


# ── Signal → UI verdict mapping ───────────────────────────────────────────────

# Maps one VSA signal to the 5-level verdict badge — used for per-signal
# labels (chart overlays, trust-score event selection), NOT for the stock's
# overall verdict, which comes from the decayed net score (see
# ``verdict_from_signals``).
_SIGNAL_VERDICT: dict[SignalName, str] = {
    SignalName.SOS: "Strong Buy",
    SignalName.SPRING: "Strong Buy",
    SignalName.SUCCESSFUL_TEST: "Buy",
    SignalName.NO_DEMAND: "Sell",
    SignalName.UPTHRUST: "Strong Sell",
    SignalName.SOW: "Strong Sell",
}


def verdict_for_signal(name: SignalName) -> str:
    """The UI verdict badge one signal maps to (e.g. SOS → "Strong Buy")."""
    return _SIGNAL_VERDICT.get(name, "Hold")


# Net-score boundaries for the overall verdict. A single fresh strong signal
# (strength 1.0) lands in "Buy"/"Sell"; "Strong" requires either a cluster of
# confirming signals or unusually strong recent evidence — consistent with the
# rating scale, where net 1.2 ≈ rating 77 and net 0.45 ≈ rating 61.
_VERDICT_STRONG_NET = 1.2
_VERDICT_LEAN_NET = 0.45


def verdict_from_signals(
    signals: Sequence[VsaSignal],
    as_of: date,
    half_life_days: int = 30,
) -> tuple[str, int]:
    """Return (verdict_label, days_since_last_signal) for the stock overall.

    The verdict is derived from the same time-decayed net score that drives
    ``compute_rating`` (via the shared ``_net_score`` helper), so the badge is
    always consistent with the rating — a stock rated deep green can never
    carry a "Sell" badge just because its single most recent signal happened
    to be bearish. A caller that passes a custom ``half_life_days`` to
    ``compute_rating`` must pass the same value here, or the two drift apart
    again. Mapping:

        net >=  1.2  → "Strong Buy"      net <= -1.2  → "Strong Sell"
        net >=  0.45 → "Buy"             net <= -0.45 → "Sell"
        otherwise    → "Hold"

    ``days_since`` is the age (in days) of the most recent signal of any
    type. Falls back to ("Hold", 999) when there are no signals.
    """
    if not signals:
        return "Hold", 999

    latest = max(signals, key=lambda s: s.date)
    days_since = max(0, (as_of - latest.date).days)

    net = _net_score(signals, as_of, half_life_days)
    if net >= _VERDICT_STRONG_NET:
        verdict = "Strong Buy"
    elif net >= _VERDICT_LEAN_NET:
        verdict = "Buy"
    elif net <= -_VERDICT_STRONG_NET:
        verdict = "Strong Sell"
    elif net <= -_VERDICT_LEAN_NET:
        verdict = "Sell"
    else:
        verdict = "Hold"
    return verdict, days_since
