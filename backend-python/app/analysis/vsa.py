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


@dataclass(frozen=True)
class VsaConfig:
    """Complete detection configuration: per-signal thresholds and toggles."""

    params: Mapping[SignalName, SignalParams] = field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_PARAMS)
    )

    @classmethod
    def default(cls) -> VsaConfig:
        return cls()

    def for_signal(self, name: SignalName) -> SignalParams:
        return self.params.get(name, DEFAULT_SIGNAL_PARAMS[name])

    def is_default(self) -> bool:
        return all(
            self.for_signal(name) == DEFAULT_SIGNAL_PARAMS[name] for name in SignalName
        )

    def cache_suffix(self) -> str:
        """Stable short hash for cache keys; empty string for the default config.

        Keeping the default suffix empty means existing cache keys (and the
        nightly pre-warmed ranking) keep working unchanged.
        """
        if self.is_default():
            return ""
        canonical = json.dumps(
            {
                name.value: [
                    p.enabled, p.spread_mult, p.vol_mult, p.close_pos, p.lookback,
                ]
                for name in SignalName
                for p in [self.for_signal(name)]
            },
            sort_keys=True,
        )
        return ":" + hashlib.md5(canonical.encode()).hexdigest()[:10]


# Minimum warm-up buffer beyond the rolling lookback before signals may fire.
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
    df["close_pos"] = (df["close"] - df["low"]) / (df["spread"].clip(lower=1e-9))

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

    def ctx(row: pd.Series, lb: int) -> tuple[float, float, float, float] | None:
        """Rolling context for one lookback, or None when not yet available."""
        avg_v = row[f"avg_vol_{lb}"]
        if pd.isna(avg_v) or avg_v < 1:
            return None
        return (row[f"avg_spread_{lb}"], avg_v, row[f"prior_low_{lb}"], row[f"prior_high_{lb}"])

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

        matched: VsaSignal | None = None

        # ── Bullish patterns (evaluated highest-priority first) ───────────

        # Spring (VSA "Shake-out") — a break below prior support that reverses
        # to close back above it, near the bar's high. Two valid volume
        # regimes (Master the Markets "The Shake-out"; Wyckoff spring types):
        #   * high volume + wide spread — professional money absorbing the
        #     panic selling it just shook out (terminal shake-out);
        #   * low volume — the break attracted no sellers at all ("no
        #     supply"), the highest-probability spring; its spread is
        #     usually modest, so no wide-spread requirement.
        # Average, unremarkable volume shows no anomaly and does not qualify.
        if matched is None and SignalName.SPRING in active:
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
                        (spread > avg_sp * p.spread_mult and vol > avg_v * p.vol_mult)
                        or vol < avg_v * _LOW_VOL_MULT
                    )
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.SPRING,
                        type=SignalType.BULLISH, strength=0.9,
                    )

        # SOS — wide up-bar on high volume closing near the high.
        if matched is None and SignalName.SOS in active:
            p = active[SignalName.SOS]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, _ = c
                if (
                    avg_sp > 0
                    and spread > avg_sp * p.spread_mult
                    and vol > avg_v * p.vol_mult
                    and cp > p.close_pos
                    and row["close"] > prev_close
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.SOS,
                        type=SignalType.BULLISH, strength=1.0,
                    )

        # Successful Test ("no supply") — Master the Markets p.33: "Any
        # down-move dipping into an area of previous selling, which then
        # regains to close on, or near the high, on lower volume ... This is a
        # successful test." The bar dips below the previous bar's low, finds
        # no sellers, and closes near its high. Volume must be genuinely low:
        # below the rolling average (× vol_mult) AND lower than both of the
        # previous two bars (the standard TradeGuider criterion).
        if matched is None and SignalName.SUCCESSFUL_TEST in active:
            p = active[SignalName.SUCCESSFUL_TEST]
            c = ctx(row, p.lookback)
            if c is not None:
                _, avg_v, _, _ = c
                if (
                    row["low"] < prev_low
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
        # a wide spread, "on or very near the lows" (Master the Markets p.76:
        # "the day must close on or very near the lows; the volume can be
        # either low (no demand) or high (supply overcoming the demand)").
        # High volume means real supply hit the breakout; low volume means a
        # hollow fake-out with no genuine buying behind it. Either is a valid
        # trap; only "average, unremarkable" volume is excluded — the book's
        # own example (p.64) of an average-volume up-thrust sees the market
        # simply continue upwards.
        if matched is None and SignalName.UPTHRUST in active:
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

        # SOW — wide down-bar on high volume closing near the low.
        if matched is None and SignalName.SOW in active:
            p = active[SignalName.SOW]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, _ = c
                if (
                    avg_sp > 0
                    and spread > avg_sp * p.spread_mult
                    and vol > avg_v * p.vol_mult
                    and cp < p.close_pos
                    and row["close"] < prev_close
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.SOW,
                        type=SignalType.BEARISH, strength=1.0,
                    )

        # No Demand — narrow up-bar on low volume; professionals not
        # participating. Master the Markets p.30: "a low volume up-bar, on a
        # narrow spread"; the TradeGuider criterion adds that the volume must
        # be lower than both of the previous two bars and the close in the
        # middle or low — a bar closing strongly on its own high isn't a
        # No Demand bar even if narrow and quiet.
        if matched is None and SignalName.NO_DEMAND in active:
            p = active[SignalName.NO_DEMAND]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, _ = c
                if (
                    avg_sp > 0
                    and row["close"] > prev_close
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

    lam = math.log(2) / half_life_days
    net_score = 0.0

    for s in signals:
        days_ago = (as_of - s.date).days
        if days_ago < 0:
            continue  # future-dated signal; skip
        weight = math.exp(-lam * days_ago)
        if s.type == SignalType.BULLISH:
            net_score += weight * s.strength
        else:
            net_score -= weight * s.strength

    return max(0, min(100, round(50.0 + 50.0 * math.tanh(net_score / 2.0))))


# ── Signal → UI verdict mapping ───────────────────────────────────────────────

# Maps the most recent VSA signal to the 5-level verdict badge used by the UI.
_SIGNAL_VERDICT: dict[SignalName, str] = {
    SignalName.SOS: "Strong Buy",
    SignalName.SPRING: "Strong Buy",
    SignalName.SUCCESSFUL_TEST: "Buy",
    SignalName.NO_DEMAND: "Sell",
    SignalName.UPTHRUST: "Strong Sell",
    SignalName.SOW: "Strong Sell",
}


def verdict_from_signals(signals: Sequence[VsaSignal], as_of: date) -> tuple[str, int]:
    """Return (verdict_label, days_since_last_signal) from the most recent signal.

    Falls back to ("Hold", 999) when there are no signals.
    """
    if not signals:
        return "Hold", 999

    latest = max(signals, key=lambda s: s.date)
    days_since = (as_of - latest.date).days
    verdict = _SIGNAL_VERDICT.get(latest.signal_name, "Hold")
    return verdict, max(0, days_since)
