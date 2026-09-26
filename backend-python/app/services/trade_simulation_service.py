"""Per-stock trade simulation: the owner's VSA program, run on stored bars.

``GET /api/stocks/{ticker}/trade-simulation`` answers "what would the VSA V4
program have done on this stock?" with the program's own simulator
(``app/analysis/vsa4/backtest.py``): every confirmed setup entered at the next
open, a structural stop, a 3R target, one position at a time, 1% of the
account risked per trade, costs on both sides. This module only runs
``adapter.simulate`` and reshapes its ``trades.csv`` / ``equity.csv`` /
``summary.json`` equivalents into the API model — no rule lives here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import Any

from app.analysis.vsa4.adapter import (
    DEFAULT_COMMISSION_BPS,
    DEFAULT_SLIPPAGE_BPS,
    Sides,
    SimulationRun,
    setup_label,
    simulate,
)
from app.models import (
    EquityPoint,
    SimulatedTrade,
    StooqDailyQuote,
    TradeSimulationResponse,
)

ENGINE_VERSION = "vsa-kompendium-program-2026-09-24"
# The equity curve is for a sparkline; a few hundred points draw the same line
# as 1,250 and keep the payload small. Every trade's effect is still in it —
# thinning drops sessions, and drawdown is measured on the full curve.
_MAX_EQUITY_POINTS = 300


def _finite(value: Any) -> float | None:
    """``value`` as a finite float, or ``None`` ("" and None come from the CSV rows)."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _day(stamp: str) -> date | None:
    return date.fromisoformat(stamp[:10]) if stamp else None


def _trades(run: SimulationRun) -> list[SimulatedTrade]:
    index_of = {b.timestamp: i for i, b in enumerate(run.bars)}
    last_close = run.bars[-1].close
    out: list[SimulatedTrade] = []
    for t in run.trades:
        direction = 1 if t["direction"] == "long" else -1
        entry = float(t["entry_price"])
        exit_price = _finite(t["exit_price"])
        reference = exit_price if exit_price is not None else last_close
        signal_i = index_of.get(t["signal_timestamp"])
        setup = (
            setup_label(run.rows[signal_i])
            if signal_i is not None
            else str(t["signal_name"]).split(":", 1)[-1]
        )
        out.append(
            SimulatedTrade(
                status=t["status"],
                direction=t["direction"],
                signal_date=_day(t["signal_timestamp"]),
                entry_date=_day(t["entry_timestamp"]),
                exit_date=_day(t["exit_timestamp"]),
                setup=setup,
                entry_price=entry,
                stop_loss=float(t["stop_loss"]),
                take_profit=float(t["take_profit"]),
                exit_price=exit_price,
                exit_reason=t["exit_reason"],
                quantity=float(t["quantity"]),
                net_pnl=float(t["net_pnl"]),
                net_r=_finite(t["net_r_multiple"]),
                return_pct=(
                    direction * (reference / entry - 1.0) * 100.0 if entry > 0 else None
                ),
            )
        )
    return out


def _equity(run: SimulationRun) -> list[EquityPoint]:
    rows = run.equity
    step = max(1, math.ceil(len(rows) / _MAX_EQUITY_POINTS))
    picked = list(range(0, len(rows), step))
    if rows and picked[-1] != len(rows) - 1:
        picked.append(len(rows) - 1)
    return [
        EquityPoint(
            date=run.dates[i],
            equity=float(rows[i]["equity"]),
            drawdown_pct=float(rows[i]["drawdown_pct"]) * 100.0,
        )
        for i in picked
    ]


def build_trade_simulation(
    ticker: str,
    quotes: Sequence[StooqDailyQuote],
    *,
    currency: str | None,
    sides: Sides = "long",
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> TradeSimulationResponse | None:
    """Simulate the VSA V4 program on ``quotes``; ``None`` with no usable bars."""
    run = simulate(
        quotes, sides=sides, commission_bps=commission_bps, slippage_bps=slippage_bps
    )
    if run is None:
        return None
    summary = run.summary
    closed_r = [
        r
        for r in (_finite(t["net_r_multiple"]) for t in run.trades if t["status"] == "closed")
        if r is not None
    ]
    first_close, last_close = run.bars[0].close, run.bars[-1].close
    cfg = run.config
    return TradeSimulationResponse(
        ticker=ticker.upper(),
        currency=currency,
        from_date=run.dates[0],
        as_of=run.dates[-1],
        bar_count=len(run.bars),
        sides=sides,
        initial_capital=cfg.initial_capital,
        risk_pct=cfg.risk_fraction * 100.0,
        reward_risk=cfg.reward_risk,
        commission_pct=cfg.commission_bps / 100.0,
        slippage_pct=cfg.slippage_bps / 100.0,
        final_equity=float(summary["final_equity"]),
        total_return_pct=float(summary["total_return_pct"]),
        max_drawdown_pct=float(summary["max_drawdown_pct"]),
        closed_trades=int(summary["closed_trades"]),
        open_trades=int(summary["open_trades"]),
        wins=int(summary["wins"]),
        losses=int(summary["losses"]),
        win_rate_pct=_finite(summary["win_rate_pct"]),
        profit_factor=_finite(summary["profit_factor_net"]),
        avg_r=sum(closed_r) / len(closed_r) if closed_r else None,
        skipped_entries=int(summary["skipped_entries"]),
        long_setups=sum(bool(r["long_setup_confirmation"]) for r in run.rows),
        short_setups=sum(bool(r["short_setup_confirmation"]) for r in run.rows),
        buy_hold_return_pct=(last_close / first_close - 1.0) * 100.0 if first_close > 0 else None,
        trades=_trades(run),
        equity=_equity(run),
        engine=ENGINE_VERSION,
    )
