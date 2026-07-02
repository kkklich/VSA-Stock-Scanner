"""Volume Spread Analysis (VSA) signal detection and rating.

VSA reads three variables per bar — spread (high − low), the close's position
within that spread, and volume — to infer whether professional money is
accumulating (strength) or distributing (weakness). See agent/DOCUMENTATION.md §7
and the Tom Williams reference text in the agent/ folder.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.models import StooqDailyQuote


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


# Minimum bars required for meaningful signal detection (lookback + buffer).
_MIN_BARS = 25
_LOOKBACK = 20


def detect_signals(bars: Sequence[StooqDailyQuote]) -> list[VsaSignal]:
    """Scan a chronological OHLCV series for VSA patterns and return them in date order.

    Each rule matches at most one pattern per bar (highest priority wins), so a bar
    cannot simultaneously be a Spring and a No-Demand bar.

    Requires at least 25 bars (20 for the rolling context + 5 as a warm-up buffer).
    Returns an empty list when there is not enough history.
    """
    if len(bars) < _MIN_BARS:
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

    # Rolling context (shift(1) so each bar sees *prior* bars only, no lookahead).
    df["avg_spread"] = df["spread"].rolling(_LOOKBACK).mean().shift(1)
    df["avg_vol"] = df["volume"].rolling(_LOOKBACK).mean().shift(1)
    df["prior_low"] = df["low"].rolling(_LOOKBACK).min().shift(1)
    df["prior_high"] = df["high"].rolling(_LOOKBACK).max().shift(1)

    # Previous-bar context. VSA defines an up-bar as a close *above the previous
    # bar's close* (not above its own open) — Master the Markets p.31 — so every
    # direction check below compares against prev_close.
    df["prev_close"] = df["close"].shift(1)
    df["prev_low"] = df["low"].shift(1)
    # "Volume lower than the previous two bars" (TradeGuider criterion for
    # No Demand / a Test) means lower than BOTH, i.e. below their minimum.
    df["prev_vol_min2"] = df["volume"].rolling(2).min().shift(1)

    signals: list[VsaSignal] = []

    for i in range(_LOOKBACK + 1, len(df)):
        row = df.iloc[i]

        # Skip bars where rolling context is not yet available.
        if pd.isna(row["avg_vol"]) or row["avg_vol"] < 1:
            continue

        avg_sp = row["avg_spread"]
        avg_v = row["avg_vol"]
        cp = row["close_pos"]
        spread = row["spread"]
        vol = row["volume"]
        prior_low = row["prior_low"]
        prior_high = row["prior_high"]
        prev_close = row["prev_close"]
        prev_low = row["prev_low"]
        prev_vol_min2 = row["prev_vol_min2"]
        d = row["date"]

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
        if (
            prior_low > 0
            and row["low"] <= prior_low
            and row["close"] > prior_low
            and cp > 0.6
            and (
                (spread > avg_sp * 1.2 and vol > avg_v * 1.2)
                or vol < avg_v * 0.7
            )
        ):
            signals.append(
                VsaSignal(date=d, signal_name=SignalName.SPRING, type=SignalType.BULLISH, strength=0.9)
            )

        # SOS — wide up-bar on high volume closing near the high.
        elif (
            avg_sp > 0
            and spread > avg_sp * 1.5
            and vol > avg_v * 1.5
            and cp > 0.65
            and row["close"] > prev_close
        ):
            signals.append(
                VsaSignal(date=d, signal_name=SignalName.SOS, type=SignalType.BULLISH, strength=1.0)
            )

        # Successful Test ("no supply") — Master the Markets p.33: "Any
        # down-move dipping into an area of previous selling, which then
        # regains to close on, or near the high, on lower volume ... This is a
        # successful test." The bar dips below the previous bar's low, finds
        # no sellers, and closes near its high. Volume must be genuinely low:
        # below the 20-bar average AND lower than both of the previous two
        # bars (the standard TradeGuider criterion).
        elif (
            row["low"] < prev_low
            and cp >= 0.65
            and vol < avg_v * 0.7
            and vol < prev_vol_min2
        ):
            signals.append(
                VsaSignal(
                    date=d,
                    signal_name=SignalName.SUCCESSFUL_TEST,
                    type=SignalType.BULLISH,
                    strength=0.75,
                )
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
        elif (
            prior_high > 0
            and row["high"] >= prior_high
            and row["close"] < prior_high
            and cp < 0.3
            and spread > avg_sp * 1.2
            and (vol > avg_v * 1.3 or vol < avg_v * 0.7)
        ):
            signals.append(
                VsaSignal(date=d, signal_name=SignalName.UPTHRUST, type=SignalType.BEARISH, strength=0.85)
            )

        # SOW — wide down-bar on high volume closing near the low.
        elif (
            avg_sp > 0
            and spread > avg_sp * 1.5
            and vol > avg_v * 1.5
            and cp < 0.35
            and row["close"] < prev_close
        ):
            signals.append(
                VsaSignal(date=d, signal_name=SignalName.SOW, type=SignalType.BEARISH, strength=1.0)
            )

        # No Demand — narrow up-bar on low volume; professionals not
        # participating. Master the Markets p.30: "a low volume up-bar, on a
        # narrow spread"; the TradeGuider criterion adds that the volume must
        # be lower than both of the previous two bars and the close in the
        # middle or low — a bar closing strongly on its own high isn't a
        # No Demand bar even if narrow and quiet.
        elif (
            avg_sp > 0
            and row["close"] > prev_close
            and spread < avg_sp * 0.7
            and vol < avg_v * 0.7
            and vol < prev_vol_min2
            and cp < 0.65
        ):
            signals.append(
                VsaSignal(date=d, signal_name=SignalName.NO_DEMAND, type=SignalType.BEARISH, strength=0.6)
            )

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
