"""Small single-position OHLCV backtester with explicit adverse execution rules.

[StockPilot] Vendored from the owner's "VSA - kompendium i program Python"
package (python/backtest.py, SHA-256 145640aa...ef0ee, supplied 2026-09-24).
Unchanged except this note and the import below, which points at the vendored
engine instead of a sibling ``engine.py`` on ``sys.path``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.analysis.vsa4.engine import Bar, Config  # [StockPilot] was: from engine import


@dataclass
class Position:
    direction: int
    signal_index: int
    entry_index: int
    entry_time: str
    entry_price: float
    quantity: float
    stop: float
    target: float
    initial_risk_per_unit: float
    entry_commission: float
    signal_name: str


TRADE_FIELDS = [
    "status", "direction", "signal_timestamp", "entry_timestamp", "exit_timestamp",
    "entry_bar_index", "exit_bar_index", "signal_name", "entry_price", "stop_loss",
    "take_profit", "quantity", "entry_notional", "initial_risk_per_unit",
    "exit_price", "exit_reason", "gross_pnl", "entry_commission", "exit_commission",
    "net_pnl", "net_r_multiple", "unrealized_net_pnl",
]


def _close_execution_price(raw_price: float, direction: int, config: Config) -> float:
    slip = config.slippage_bps / 10000.0
    return raw_price * (1.0 - direction * slip)


def _mark_to_market(position: Position, close: float, cash: float, config: Config) -> tuple[float, float]:
    hypothetical_exit = _close_execution_price(close, position.direction, config)
    unrealized_gross = position.quantity * position.direction * (hypothetical_exit - position.entry_price)
    estimated_exit_commission = hypothetical_exit * position.quantity * config.commission_bps / 10000.0
    unrealized_net = unrealized_gross - estimated_exit_commission
    return cash + unrealized_net, unrealized_net


def _closed_trade(
    position: Position, bars: list[Bar], exit_index: int, raw_exit: float,
    reason: str, config: Config, limit_fill: bool = False,
) -> tuple[dict[str, Any], float]:
    exit_price = raw_exit if limit_fill else _close_execution_price(raw_exit, position.direction, config)
    gross = position.quantity * position.direction * (exit_price - position.entry_price)
    exit_commission = exit_price * position.quantity * config.commission_bps / 10000.0
    net = gross - position.entry_commission - exit_commission
    initial_cash_risk = position.quantity * position.initial_risk_per_unit
    trade = {
        "status": "closed", "direction": "long" if position.direction > 0 else "short",
        "signal_timestamp": bars[position.signal_index].timestamp,
        "entry_timestamp": position.entry_time, "exit_timestamp": bars[exit_index].timestamp,
        "entry_bar_index": position.entry_index, "exit_bar_index": exit_index,
        "signal_name": position.signal_name, "entry_price": position.entry_price,
        "stop_loss": position.stop, "take_profit": position.target,
        "quantity": position.quantity, "entry_notional": position.entry_price * position.quantity,
        "initial_risk_per_unit": position.initial_risk_per_unit,
        "exit_price": exit_price, "exit_reason": reason, "gross_pnl": gross,
        "entry_commission": position.entry_commission, "exit_commission": exit_commission,
        "net_pnl": net, "net_r_multiple": net / initial_cash_risk if initial_cash_risk else None,
        "unrealized_net_pnl": 0.0,
    }
    return trade, gross - exit_commission


def _try_enter(
    i: int, bars: list[Bar], rows: list[dict[str, Any]], pending: dict[str, Any],
    equity_before_open: float, cash: float, config: Config,
) -> tuple[Position | None, float, str]:
    row = rows[i]
    direction = 1 if pending["direction"] == "long" else -1
    raw_open = bars[i].open
    stop = pending["stop"]
    if bars[i].volume <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_zero_volume_entry_bar"
        return None, cash, "skipped_zero_volume_entry_bar"
    if not math.isfinite(stop) or stop <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_invalid_stop"
        return None, cash, "skipped_invalid_stop"
    # A gap through the planned structural stop invalidates this setup before entry.
    if (direction > 0 and raw_open <= stop) or (direction < 0 and raw_open >= stop):
        rows[pending["signal_index"]]["entry_status"] = "skipped_gap_through_stop"
        return None, cash, "skipped_gap_through_stop"
    entry_price = _close_execution_price(raw_open, -direction, config)
    price_distance = direction * (entry_price - stop)
    if not math.isfinite(price_distance) or price_distance <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_invalid_stop_distance"
        return None, cash, "skipped_invalid_stop_distance"
    risk_budget = max(0.0, equity_before_open) * config.risk_fraction
    stop_exit = _close_execution_price(stop, direction, config)
    if stop_exit <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_invalid_stop_exit"
        return None, cash, "skipped_invalid_stop_exit"
    # Size against the modeled loss at the adverse stop fill, including both fees.
    effective_loss_per_unit = (
        direction * (entry_price - stop_exit)
        + (entry_price + stop_exit) * config.commission_bps / 10000.0
    )
    if risk_budget <= 0 or effective_loss_per_unit <= 0 or entry_price <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_nonpositive_size"
        return None, cash, "skipped_nonpositive_size"
    risk_limited_qty = risk_budget / effective_loss_per_unit
    notional_limited_qty = max(0.0, equity_before_open) * config.max_notional_fraction / entry_price
    quantity = min(risk_limited_qty, notional_limited_qty)
    if not math.isfinite(quantity) or quantity <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_nonpositive_size"
        return None, cash, "skipped_nonpositive_size"
    target = entry_price + direction * price_distance * config.reward_risk
    if not math.isfinite(target) or target <= 0:
        rows[pending["signal_index"]]["entry_status"] = "skipped_invalid_target"
        return None, cash, "skipped_invalid_target"
    entry_commission = entry_price * quantity * config.commission_bps / 10000.0
    cash -= entry_commission
    pos = Position(
        direction=direction, signal_index=pending["signal_index"], entry_index=i,
        entry_time=bars[i].timestamp, entry_price=entry_price, quantity=quantity,
        stop=stop, target=target, initial_risk_per_unit=price_distance,
        entry_commission=entry_commission, signal_name=pending["signal_name"],
    )
    rows[pending["signal_index"]]["entry_status"] = "filled_next_open"
    return pos, cash, "filled_next_open"


def run_backtest(
    bars: list[Bar], rows: list[dict[str, Any]], config: Config
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Simulate close-confirmed setups filled on the next bar open."""
    cash = config.initial_capital
    equity = config.initial_capital
    peak = config.initial_capital
    position: Position | None = None
    pending_entry: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    skipped_entries = 0

    for i, bar in enumerate(bars):
        if pending_entry is not None:
            if position is None:
                position, cash, _entry_status = _try_enter(
                    i, bars, rows, pending_entry, equity, cash, config
                )
                if position is None:
                    skipped_entries += 1
            else:
                rows[pending_entry["signal_index"]]["entry_status"] = "skipped_position_already_open"
                skipped_entries += 1
            pending_entry = None

        # The entry bar is processed here too. If both intrabar barriers are touched,
        # the conservative stop-first convention is used because OHLC has no path.
        if position is not None and bar.volume > 0:
            direction = position.direction
            exit_raw: float | None = None
            exit_reason = ""
            limit_fill = False
            if direction > 0:
                if bar.open <= position.stop:
                    exit_raw, exit_reason = bar.open, "stop_gap_open"
                elif bar.open >= position.target:
                    exit_raw, exit_reason, limit_fill = position.target, "take_profit_gap_open", True
                else:
                    stop_hit, target_hit = bar.low <= position.stop, bar.high >= position.target
                    if stop_hit:
                        exit_raw, exit_reason = position.stop, "stop_same_bar_both_hit" if target_hit else "stop"
                    elif target_hit:
                        exit_raw, exit_reason, limit_fill = position.target, "take_profit", True
            else:
                if bar.open >= position.stop:
                    exit_raw, exit_reason = bar.open, "stop_gap_open"
                elif bar.open <= position.target:
                    exit_raw, exit_reason, limit_fill = position.target, "take_profit_gap_open", True
                else:
                    stop_hit, target_hit = bar.high >= position.stop, bar.low <= position.target
                    if stop_hit:
                        exit_raw, exit_reason = position.stop, "stop_same_bar_both_hit" if target_hit else "stop"
                    elif target_hit:
                        exit_raw, exit_reason, limit_fill = position.target, "take_profit", True
            if exit_raw is not None:
                trade, cash_delta = _closed_trade(
                    position, bars, i, exit_raw, exit_reason, config, limit_fill
                )
                trades.append(trade)
                cash += cash_delta
                position = None

        # Optional mark-to-close liquidation applies after ordinary stop/target checks.
        if position is not None and i == len(bars) - 1 and config.close_positions_at_end and bar.volume > 0:
            trade, cash_delta = _closed_trade(
                position, bars, i, bar.close, "end_of_data_close", config
            )
            trades.append(trade)
            cash += cash_delta
            position = None

        unrealized = 0.0
        if position is not None:
            equity, unrealized = _mark_to_market(position, bar.close, cash, config)
        else:
            equity = cash
        peak = max(peak, equity)
        drawdown = peak - equity
        equity_rows.append({
            "timestamp": bar.timestamp, "cash": cash, "equity": equity,
            "open_unrealized_net_pnl": unrealized, "peak_equity": peak,
            "drawdown": drawdown,
            "drawdown_pct": drawdown / peak if peak > 0 else 0.0,
            "open_position": "long" if position and position.direction > 0 else "short" if position else "",
        })

        # The close of this bar creates a signal; it may only be filled at i+1 open.
        row = rows[i]
        long_signal = bool(row["long_setup_confirmation"])
        short_signal = bool(row["short_setup_confirmation"])
        if long_signal and short_signal:
            row["entry_status"] = "skipped_conflicting_setups"
        elif long_signal or short_signal:
            if i + 1 >= len(bars):
                row["entry_status"] = "no_next_open"
            elif position is not None or pending_entry is not None:
                row["entry_status"] = "skipped_position_already_open"
                skipped_entries += 1
            else:
                stop = row["setup_stop_level"]
                if stop is None or not math.isfinite(float(stop)):
                    row["entry_status"] = "skipped_missing_stop"
                    skipped_entries += 1
                else:
                    direction = "long" if long_signal else "short"
                    row["entry_status"] = "queued_next_open"
                    pending_entry = {
                        "direction": direction, "stop": float(stop), "signal_index": i,
                        "signal_name": f"{direction}:{row['setup_reference_signal']}",
                    }

    if position is not None:
        marked_equity, unrealized = _mark_to_market(position, bars[-1].close, cash, config)
        hypothetical_exit = _close_execution_price(bars[-1].close, position.direction, config)
        exit_fee_estimate = hypothetical_exit * position.quantity * config.commission_bps / 10000.0
        gross_mark = position.quantity * position.direction * (hypothetical_exit - position.entry_price)
        net_mark = gross_mark - position.entry_commission - exit_fee_estimate
        trades.append({
            "status": "open", "direction": "long" if position.direction > 0 else "short",
            "signal_timestamp": bars[position.signal_index].timestamp,
            "entry_timestamp": position.entry_time, "exit_timestamp": "",
            "entry_bar_index": position.entry_index, "exit_bar_index": "",
            "signal_name": position.signal_name, "entry_price": position.entry_price,
            "stop_loss": position.stop, "take_profit": position.target,
            "quantity": position.quantity, "entry_notional": position.entry_price * position.quantity,
            "initial_risk_per_unit": position.initial_risk_per_unit,
            "exit_price": "", "exit_reason": "open_at_end",
            "gross_pnl": "", "entry_commission": position.entry_commission,
            "exit_commission": exit_fee_estimate, "net_pnl": net_mark,
            "net_r_multiple": net_mark / (position.quantity * position.initial_risk_per_unit),
            "unrealized_net_pnl": unrealized,
        })
        equity = marked_equity

    final_equity = equity_rows[-1]["equity"] if equity_rows else config.initial_capital
    if position is not None:
        final_equity = equity
        equity_rows[-1]["equity"] = equity
        equity_rows[-1]["open_unrealized_net_pnl"] = unrealized
        # Recalculate final drawdown after including closing cost estimate.
        peak = max(row["peak_equity"] for row in equity_rows)
        equity_rows[-1]["peak_equity"] = peak
        equity_rows[-1]["drawdown"] = peak - equity
        equity_rows[-1]["drawdown_pct"] = (peak - equity) / peak if peak > 0 else 0.0

    closed = [trade for trade in trades if trade["status"] == "closed"]
    wins = sum(float(trade["net_pnl"]) > 0 for trade in closed)
    losses = sum(float(trade["net_pnl"]) < 0 for trade in closed)
    gross_wins = sum(max(0.0, float(trade["net_pnl"])) for trade in closed)
    gross_losses = -sum(min(0.0, float(trade["net_pnl"])) for trade in closed)
    summary = {
        "initial_capital": config.initial_capital,
        "final_equity": final_equity,
        "net_pnl_including_open_mtm": final_equity - config.initial_capital,
        "total_return_pct": (final_equity / config.initial_capital - 1.0) * 100.0,
        "max_drawdown": max((float(row["drawdown"]) for row in equity_rows), default=0.0),
        "max_drawdown_pct": max((float(row["drawdown_pct"]) for row in equity_rows), default=0.0) * 100.0,
        "closed_trades": len(closed), "open_trades": sum(trade["status"] == "open" for trade in trades),
        "wins": wins, "losses": losses,
        "win_rate_pct": wins / len(closed) * 100.0 if closed else None,
        "profit_factor_net": gross_wins / gross_losses if gross_losses > 0 else None,
        "skipped_entries": skipped_entries,
        "close_positions_at_end": config.close_positions_at_end,
        "execution_model": "next-open fills; adverse slippage; fees on both sides; stop-first if SL and TP share an OHLC bar",
        "caveat": "Educational heuristic simulation; OHLC does not reveal intrabar path; no broker, financing, dividends, spread model or market impact.",
    }
    return trades, equity_rows, summary
