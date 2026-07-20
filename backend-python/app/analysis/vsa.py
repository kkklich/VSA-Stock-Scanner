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

        # SOS — wide up-bar on high volume closing near the high. High but NOT
        # excessive: Master the Markets says volume on an up-bar "should not
        # be excessive, as this is indicative of supply in the background" —
        # at ultra-high volume a wide up-bar is a potential buying climax
        # (weakness), so volume is capped at _excessive_cap × average.
        if matched is None and SignalName.SOS in active:
            p = active[SignalName.SOS]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, _ = c
                if (
                    spread > avg_sp * p.spread_mult
                    and vol > avg_v * p.vol_mult
                    and vol <= avg_v * _excessive_cap(p)
                    and cp > p.close_pos
                    and row["close"] > prev_close
                ):
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
        if matched is None and SignalName.SUCCESSFUL_TEST in active:
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

        # SOW — wide down-bar on high volume closing near the low. High but
        # NOT excessive, mirroring SOS: at ultra-high volume a wide down-bar
        # is potential "stopping volume" — professional money buying into the
        # capitulation (budding strength) — so the same climax cap applies.
        # (The Upthrust is deliberately NOT capped: an upthrust on ultra-high
        # volume — a buying climax — is still legitimately bearish.)
        if matched is None and SignalName.SOW in active:
            p = active[SignalName.SOW]
            c = ctx(row, p.lookback)
            if c is not None:
                avg_sp, avg_v, _, _ = c
                if (
                    spread > avg_sp * p.spread_mult
                    and vol > avg_v * p.vol_mult
                    and vol <= avg_v * _excessive_cap(p)
                    and cp < p.close_pos
                    and row["close"] < prev_close
                ):
                    matched = VsaSignal(
                        date=d, signal_name=SignalName.SOW,
                        type=SignalType.BEARISH, strength=1.0,
                    )

        # No Demand — narrow up-bar on low volume; professionals not
        # participating. Master the Markets p.32: "a low volume up-bar, on a
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
