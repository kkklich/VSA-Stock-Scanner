"""What the AI layer learns to predict — plan §18, design choices §1.

* **L1 — beat the market** (the training label): the return from the **next
  open** to the close *N* sessions later. ``dataset`` compares it with the
  same-day median of that return across the stock's market; this module
  computes the stock's own half.
* **L2 — the app's own frame** (reporting only): exactly what the back-test
  gate measures in ``method_backtest_service.judge_stock`` — entry at the
  firing bar's close, compared with the stock's own median *N*-session move.
* **L3 — the trade**: a triple barrier (stop, target, time limit) on the next
  open, stop first when both are hit on one bar, gaps filled at the open, and
  VSA V4's stock-like costs on both sides.

A label that cannot be judged honestly — too few forward bars, a missing next
open, or a suspension inside the window — is missing, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import numpy as np
import pandas as pd

from app.analysis.vsa4.adapter import DEFAULT_COMMISSION_BPS, DEFAULT_SLIPPAGE_BPS

#: A window holding a gap longer than this (in calendar days) is a suspension.
MAX_WINDOW_GAP_DAYS = 10
#: L3's stop distance, in ATR14 multiples, and its target in multiples of risk.
STOP_ATR = 2.0
TARGET_R = 3.0


def _day_gaps(dates: pd.Series) -> np.ndarray:
    """Calendar days between each session and the one before it (0 for the first)."""
    days = np.array([d.toordinal() for d in dates], dtype=float)
    gaps = np.zeros(len(days))
    if len(days) > 1:
        gaps[1:] = np.diff(days)
    return gaps


def forward_open_to_close(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """L1's stock half for every row of a bars frame (``features.bars_frame``).

    Returns ``fwd_r`` (return from the open of *t*+1 to the close of *t*+*n*,
    a fraction), ``fwd_end`` (the date of *t*+*n*, the label's last day — the
    purge in ``validation`` needs it) and ``fwd_valid``.
    """
    size = len(df)
    opens = df["open"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    entry = np.full(size, np.nan)
    exit_ = np.full(size, np.nan)
    if size > 1:
        entry[:-1] = opens[1:]
    if size > n:
        exit_[: size - n] = closes[n:]

    gaps = pd.Series(_day_gaps(df["date"]))
    # Largest gap among sessions t+1 … t+n (the window the trade is held over).
    max_gap = gaps.rolling(n, min_periods=n).max().shift(-n).to_numpy()

    with np.errstate(invalid="ignore"):
        valid = (
            np.isfinite(entry)
            & np.isfinite(exit_)
            & (entry > 0)
            & (exit_ > 0)
            & np.isfinite(max_gap)
            & (max_gap <= MAX_WINDOW_GAP_DAYS)
        )
    fwd_r = np.where(valid, exit_ / np.where(entry > 0, entry, 1.0) - 1.0, np.nan)
    dates = list(df["date"])
    fwd_end = [dates[i + n] if valid[i] else None for i in range(size)]
    return pd.DataFrame({"fwd_r": fwd_r, "fwd_end": fwd_end, "fwd_valid": valid})


def gate_forward_pct(closes: np.ndarray, n: int) -> np.ndarray:
    """L2's move: close-to-close percent over *n* sessions, as the gate computes it."""
    closes = np.asarray(closes, dtype=float)
    out = np.full(len(closes), np.nan)
    if len(closes) > n:
        base = closes[:-n]
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = (closes[n:] - base) / base * 100.0
        out[: len(closes) - n] = np.where(base > 0, pct, np.nan)
    return out


def gate_baseline_pct(closes: np.ndarray, n: int) -> float | None:
    """L2's baseline: the stock's median *n*-session move (``judge_stock``)."""
    moves = gate_forward_pct(closes, n)
    finite = [float(x) for x in moves if np.isfinite(x)]
    return median(finite) if finite else None


@dataclass(frozen=True)
class TradeCosts:
    """Per-side costs, in basis points. Defaults: VSA V4's stock-like 20 + 5."""

    commission_bps: float = DEFAULT_COMMISSION_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS

    @property
    def per_side(self) -> float:
        return (self.commission_bps + self.slippage_bps) / 10_000.0


@dataclass(frozen=True)
class BarrierOutcome:
    """One L3 trade: its net R after costs and how it ended."""

    r_net: float
    exit_reason: str  # "stop" | "target" | "time"
    entry: float
    exit: float
    bars_held: int


def triple_barrier(
    df: pd.DataFrame,
    t: int,
    n: int,
    atr_t: float,
    *,
    stop_atr: float = STOP_ATR,
    target_r: float = TARGET_R,
    costs: TradeCosts | None = None,
) -> BarrierOutcome | None:
    """L3 for a signal on row ``t``: enter at the next open, hold at most ``n`` bars.

    The stop sits ``stop_atr`` × ATR14 (as of the signal's close) below the
    entry, the target ``target_r`` times that risk above it. On every bar the
    stop is checked first — the same conservative rule as VSA V4's simulator
    when stop and target share a bar — and a bar that *opens* beyond a barrier
    fills at that open. Returns ``None`` when the trade cannot be judged.
    """
    costs = costs or TradeCosts()
    size = len(df)
    if t < 0 or t + n >= size or not np.isfinite(atr_t) or atr_t <= 0:
        return None
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    gaps = _day_gaps(df["date"])
    if gaps[t + 1 : t + n + 1].max(initial=0.0) > MAX_WINDOW_GAP_DAYS:
        return None

    entry = opens[t + 1]
    if not np.isfinite(entry) or entry <= 0:
        return None
    risk = stop_atr * atr_t
    stop = entry - risk
    target = entry + target_r * risk

    exit_price = closes[t + n]
    reason = "time"
    held = n
    for j in range(t + 1, t + n + 1):
        gapped = j > t + 1  # the entry bar opens at the entry by definition
        if gapped and opens[j] <= stop:
            exit_price, reason = opens[j], "stop"
        elif lows[j] <= stop:
            exit_price, reason = stop, "stop"
        elif gapped and opens[j] >= target:
            exit_price, reason = opens[j], "target"
        elif highs[j] >= target:
            exit_price, reason = target, "target"
        else:
            continue
        held = j - t
        break

    gross_r = (exit_price - entry) / risk
    cost_r = costs.per_side * (entry + exit_price) / risk
    return BarrierOutcome(
        r_net=gross_r - cost_r,
        exit_reason=reason,
        entry=float(entry),
        exit=float(exit_price),
        bars_held=held,
    )
