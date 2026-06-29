"""Volume Spread Analysis (VSA) signal detection and rating.

VSA reads three variables per bar — spread (high − low), the close's position
within that spread, and volume — to infer whether professional money is
accumulating (strength) or distributing (weakness). See agent/DOCUMENTATION.md §7
and the Tom Williams reference text in the agent/ folder.

Stub module — the detector and rating land with the ingestion workflow. The
types and signatures below define the intended contract so the router and tests
can be written against them.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

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
    strength: float = 1.0


def detect_signals(bars: Sequence[StooqDailyQuote]) -> list[VsaSignal]:
    """Scan a chronological series of OHLCV bars for VSA patterns.

    Returns the detected signals in date order. Not yet implemented.
    """
    raise NotImplementedError


def compute_rating(
    signals: Sequence[VsaSignal],
    as_of: date,
    half_life_days: int = 30,
) -> int:
    """Collapse detected signals into a 0–100 VSA rating, applying Time Decay.

    Recent signals weigh more heavily than older ones (the relevance of a flag
    decays over time). Not yet implemented.
    """
    raise NotImplementedError
