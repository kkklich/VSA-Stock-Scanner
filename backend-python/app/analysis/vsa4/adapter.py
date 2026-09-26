"""StockPilot glue for the vendored VSA program (``engine`` + ``backtest``).

The program works on its own ``Bar`` (ISO timestamp + floats) and validates
strictly: one inconsistent bar anywhere raises ``VSAError`` for the whole
series. That is right for a hand-prepared CSV and wrong for a scan over a
thousand stocks, where one bad Yahoo bar must never sink a ranking. So this
module owns everything between the app's ``StooqDailyQuote`` rows and the
program, and nothing else:

* ``to_engine_bars`` — conversion plus the two repairs a real feed needs
  (duplicate dates, and a high/low that does not contain the open/close).
* ``config_for`` — the program's own defaults, with ``min_tick`` sized to the
  stock's price (see ``tick_size``).
* ``analyze_quotes`` / ``sequence_state`` — run the engine and read back where
  its long/short sequence stands at the last bar.
* ``simulate`` — the program's own trade simulator (``run_backtest``), long-only
  by default because this app is.

The engine and the simulator themselves are untouched; see ``__init__.py``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal

from app.analysis.vsa4.backtest import run_backtest
from app.analysis.vsa4.engine import Bar, Config, analyze
from app.models import StooqDailyQuote

Sides = Literal["long", "both"]

# Display names for the engine's signal ids (the program writes snake_case).
# The two Two Bar Reversals and the two WFOs share a name: the side is always
# clear from where they are shown (a long setup's primary is a strength).
SIGNAL_LABELS: dict[str, str] = {
    "bag_holding": "Bag Holding",
    "selling_climax": "Selling Climax",
    "stopping_volume": "Stopping Volume",
    "shakeout": "Shakeout",
    "strength_two_bar_reversal": "Two Bar Reversal",
    "no_supply": "No Supply",
    "test": "Test",
    "end_of_rising_market": "End of Rising Market",
    "buying_climax": "Buying Climax",
    "supply_coming_in": "Supply Coming In",
    "trap_upmove": "Trap Upmove",
    "no_demand": "No Demand",
    "no_result_from_effort": "No Result From Effort",
    "weakness_two_bar_reversal": "Two Bar Reversal",
    "upthrust": "Upthrust",
    "wfo_bullish": "WFO",
    "wfo_bearish": "WFO",
}

# The program's defaults are placeholders for a futures contract (1 bp each
# way). A stock trade on the GPW costs roughly 0.2-0.4% commission, so the
# app's trade simulation uses stock-like costs unless the caller says
# otherwise — the kompendium itself: "W backteście należy stosować koszty
# zgodne z instrumentem". Detection is unaffected by costs.
DEFAULT_COMMISSION_BPS = 20.0
DEFAULT_SLIPPAGE_BPS = 5.0


def label(signal_id: str) -> str:
    """Display name for an engine signal id (falls back to the id itself)."""
    return SIGNAL_LABELS.get(signal_id, signal_id.replace("_", " ").title())


def tick_size(price: float) -> float:
    """The ``min_tick`` for a stock trading at ``price``.

    The program compares prices "by more than one tick" (a new low for a
    Shakeout, the WFO's second extreme, every invalidation) and defaults the
    tick to 0.01, which is right for a futures contract or a 50-złoty stock and
    badly wrong for a penny stock: at 0.30 zł a 0.01 tick is 3%, so a Shakeout
    would need a 3% undercut. The course gives no number here ([L] in the
    kompendium), so this is a calibration choice: exchange ticks shrink with
    price roughly in decades, and so does this. Bucketed on purpose — sizing it
    continuously from the price would move every tolerance a little each day.
    """
    if price >= 10:
        return 0.01
    if price >= 1:
        return 0.001
    return 0.0001


def to_engine_bars(quotes: Sequence[StooqDailyQuote]) -> tuple[list[Bar], list[date]]:
    """Convert stored bars to the program's ``Bar``, repairing what a feed breaks.

    Returns the bars and a parallel list of their dates. Repairs, each of which
    the program would otherwise answer with a ``VSAError`` for the whole stock:

    * bars are sorted and a duplicated date keeps its last bar;
    * a bar with a non-positive or non-finite price is dropped (a halted
      session the provider filled with zeros), and a negative volume reads as 0;
    * high/low are widened to contain open/close — Yahoo's adjusted series
      occasionally prints a close a fraction above the high.
    """
    by_date: dict[date, StooqDailyQuote] = {}
    for q in quotes:
        by_date[q.date] = q
    bars: list[Bar] = []
    dates: list[date] = []
    for d in sorted(by_date):
        q = by_date[d]
        try:
            o, h, lo, c = float(q.open), float(q.high), float(q.low), float(q.close)
            v = float(q.volume)
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(x) and x > 0 for x in (o, h, lo, c)):
            continue
        if not math.isfinite(v) or v < 0:
            v = 0.0
        bars.append(Bar(d.isoformat(), o, max(h, o, c), min(lo, o, c), c, v))
        dates.append(d)
    return bars, dates


def config_for(bars: Sequence[Bar], **overrides: Any) -> Config:
    """The program's default ``Config`` with ``min_tick`` sized to the stock.

    The tick comes from the LAST close, so every caller that ends on the same
    session (the ranking, the chart, the summary) reads the same tolerances.
    """
    base = Config()
    if bars:
        base = replace(base, min_tick=tick_size(bars[-1].close))
    return replace(base, **overrides) if overrides else base


def analyze_quotes(
    quotes: Sequence[StooqDailyQuote], config: Config | None = None
) -> tuple[list[Bar], list[date], list[dict[str, Any]]]:
    """Run the program's analysis on stored bars.

    Returns ``(bars, dates, rows)`` — ``rows[i]`` is the program's full
    per-bar record (features, ``candidate_*`` flags, confirmations and the
    sequence-state fields), ``dates[i]`` its session.
    """
    bars, dates = to_engine_bars(quotes)
    if not bars:
        return [], [], []
    return bars, dates, analyze(bars, config or config_for(bars))


def split_ref(value: str) -> tuple[str, str]:
    """``"name@timestamp"`` → ``(name, timestamp)``; ``("", "")`` when empty."""
    if not value or "@" not in value:
        return "", ""
    name, _, stamp = value.partition("@")
    return name, stamp


@dataclass(frozen=True)
class SequenceLeg:
    """One piece of the program's sequence as it stands at a bar."""

    #: The primary signal (a strength for the long side, a weakness for short).
    primary: str
    #: The secondary test (No Supply / Test / No Demand), or "" for a background.
    secondary: str
    #: Session of the newest element (the test for a pending setup).
    on: date


@dataclass(frozen=True)
class SequenceState:
    """Where the program's two sequences stand after a bar's close."""

    long_background: SequenceLeg | None
    long_pending: SequenceLeg | None
    short_background: SequenceLeg | None
    short_pending: SequenceLeg | None


def _leg(value: str, pending: bool) -> SequenceLeg | None:
    ref, stamp = split_ref(value)
    if not ref:
        return None
    try:
        on = date.fromisoformat(stamp[:10])
    except ValueError:
        return None
    if pending:
        primary, _, secondary = ref.partition(">")
        return SequenceLeg(primary=primary, secondary=secondary, on=on)
    return SequenceLeg(primary=ref, secondary="", on=on)


def sequence_state(row: dict[str, Any]) -> SequenceState:
    """Read the sequence-state fields the vendored engine reports on each row."""
    return SequenceState(
        long_background=_leg(row.get("long_background", ""), pending=False),
        long_pending=_leg(row.get("long_setup_pending", ""), pending=True),
        short_background=_leg(row.get("short_background", ""), pending=False),
        short_pending=_leg(row.get("short_setup_pending", ""), pending=True),
    )


def setup_label(row: dict[str, Any]) -> str:
    """"Shakeout → No Supply" for a confirmed setup row (primary → test)."""
    secondary = label(row.get("setup_reference_signal") or "")
    primary = row.get("setup_primary_signal") or ""
    return f"{label(primary)} → {secondary}" if primary else secondary


@dataclass(frozen=True)
class SimulationRun:
    """The program's trade simulation on one stock, plus what it ran on."""

    bars: list[Bar]
    dates: list[date]
    #: The analysis exactly as the engine produced it (both sides), not the
    #: copies the simulator was given.
    rows: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    equity: list[dict[str, Any]]
    summary: dict[str, Any]
    config: Config
    sides: Sides


def simulate(
    quotes: Sequence[StooqDailyQuote],
    *,
    sides: Sides = "long",
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> SimulationRun | None:
    """Run the program's analysis and its own trade simulator on stored bars.

    ``sides="long"`` drops the short setups before the simulator sees them, so
    the account only ever buys — the app is long-only and most GPW retail
    accounts cannot short a stock. ``"both"`` is the program exactly as
    shipped. Everything else (next-open fills, stop-first when stop and target
    share a bar, 1% risk per trade, 3R target, the gap rules) is the program's.

    Returns ``None`` when there are no usable bars.
    """
    bars, dates = to_engine_bars(quotes)
    if not bars:
        return None
    config = config_for(bars, commission_bps=commission_bps, slippage_bps=slippage_bps)
    rows = analyze(bars, config)
    # The simulator writes ``entry_status`` into the rows it is given; hand it
    # copies so the analysis stays as the engine produced it.
    sim_rows = [dict(r) for r in rows]
    if sides == "long":
        for r in sim_rows:
            r["short_setup_confirmation"] = False
    trades, equity, summary = run_backtest(bars, sim_rows, config)
    return SimulationRun(
        bars=bars,
        dates=dates,
        rows=rows,
        trades=trades,
        equity=equity,
        summary=summary,
        config=config,
        sides=sides,
    )
