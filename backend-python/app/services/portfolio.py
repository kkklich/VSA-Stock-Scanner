"""FIFO and moving-average accounting in quote currency, without guessed FX rates."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
XTB_RECONCILIATION = "xtb_reconciliation"


class PortfolioError(Exception):
    def __init__(self, code: str, status: int = 409, *, context: dict | None = None):
        self.code, self.status = code, status
        self.context = context


def check_broker_account(expected: str | None, received: str | None) -> None:
    if expected and received and expected != received:
        raise PortfolioError("broker_account_mismatch")


def trade_order(trade: dict):
    """Compare instants while retaining the local dates of legacy trades."""
    executed = datetime.fromisoformat(trade.get("executedAt") or trade["date"])
    if executed.tzinfo is None:
        executed = executed.replace(tzinfo=WARSAW)
    offset = executed.utcoffset()
    utc_order = executed.replace(tzinfo=None) - datetime.min
    if offset is not None:
        utc_order -= offset
    return trade["date"], bool(trade.get("executedAt")), utc_order


def xtb_checkpoint(ledger: list[dict]) -> dict | None:
    return next((entry for entry in ledger if entry.get("kind") == XTB_RECONCILIATION), None)


def require_after_checkpoint(trade: dict, checkpoint: dict | None) -> None:
    if checkpoint and trade_order(trade) <= trade_order(checkpoint):
        raise PortfolioError("xtb_snapshot_locked")


def _position(positions, key):
    return positions.setdefault(
        key,
        {
            "ticker": key[0],
            "currency": key[1],
            "quantity": Decimal(0),
            "cost": Decimal(0),
            "realizedPnl": Decimal(0),
        },
    )


@dataclass
class _Lot:
    quantity: Decimal
    cost: Decimal
    replaced: bool = False
    sold_cost: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)

    def record_sale(self, quantity: Decimal, cost: Decimal, net_price: Decimal) -> None:
        self.sold_cost += cost
        self.realized_pnl += quantity * net_price - cost


def holdings(
    transactions: list[dict],
    cost_method: str = "moving_average",
    *,
    trade_details: list[dict] | None = None,
) -> list[dict]:
    positions = {}
    lots = {}
    purchases = []
    # Preserve insertion order on a single date: the UI records trades in execution order.
    with localcontext() as context:
        context.prec = 50
        for trade in sorted(transactions, key=trade_order):
            if trade.get("kind") == XTB_RECONCILIATION:
                # Replace the open lots at the report time. Keep all historical
                # fills and their realized P&L. This is not a buy or a sale.
                for snapshot in trade["positions"]:
                    key = (snapshot["ticker"], snapshot["currency"])
                    position = _position(positions, key)
                    position["quantity"] = Decimal(snapshot["quantity"])
                    position["cost"] = Decimal(snapshot["cost"])
                    if trade_details is not None:
                        for lot in lots.get(key, ()):
                            lot.replaced = True
                    lots[key] = deque(
                        _Lot(Decimal(lot["quantity"]), Decimal(lot["cost"]))
                        for lot in snapshot["lots"]
                    )
                continue
            key = (trade["ticker"], trade["currency"])
            position = _position(positions, key)
            quantity, price, fees = (Decimal(trade[k]) for k in ("quantity", "price", "fees"))
            detail = None
            if trade_details is not None:
                detail = dict(trade)
                if detail.get("executedAt"):
                    executed = datetime.fromisoformat(detail["executedAt"])
                    if executed.tzinfo is None:
                        detail["executedAt"] = executed.replace(tzinfo=WARSAW).isoformat()
                trade_details.append(detail)
            if trade["side"] == "buy":
                cost = quantity * price + fees
                position["quantity"] += quantity
                position["cost"] += cost
                if cost_method == "fifo" or detail is not None:
                    lot = _Lot(quantity, cost)
                    lots.setdefault(key, deque()).append(lot)
                    if detail is not None:
                        purchases.append((detail, lot))
            else:
                if quantity > position["quantity"]:
                    raise PortfolioError("insufficient_shares")
                proceeds = quantity * price - fees
                net_price = proceeds / quantity if detail is not None else None
                cost = (
                    position["cost"]
                    if quantity == position["quantity"]
                    else position["cost"] * quantity / position["quantity"]
                )
                if cost_method == "fifo":
                    remaining, cost = quantity, Decimal(0)
                    while remaining:
                        lot = lots[key][0]
                        sold = min(remaining, lot.quantity)
                        allocated = (
                            lot.cost if sold == lot.quantity else lot.cost * sold / lot.quantity
                        )
                        cost += allocated
                        if net_price is not None:
                            lot.record_sale(sold, allocated, net_price)
                        lot.quantity -= sold
                        lot.cost -= allocated
                        remaining -= sold
                        if not lot.quantity:
                            lots[key].popleft()
                    # Re-sum remaining lots to avoid a rounding residue when a position closes.
                    position["cost"] = sum((lot.cost for lot in lots[key]), Decimal(0))
                else:
                    position["cost"] -= cost
                    if net_price is not None:
                        # A moving-average sale draws proportionally from the whole pool.
                        share_left = (position["quantity"] - quantity) / position["quantity"]
                        for lot in lots.get(key, ()):
                            next_quantity = lot.quantity * share_left
                            next_cost = lot.cost * share_left
                            lot.record_sale(
                                lot.quantity - next_quantity, lot.cost - next_cost, net_price
                            )
                            lot.quantity = next_quantity
                            lot.cost = next_cost
                        if not share_left:
                            lots.pop(key, None)
                position["quantity"] -= quantity
                realized_pnl = proceeds - cost
                position["realizedPnl"] += realized_pnl
                if detail is not None:
                    detail.update(realizedCostBasis=cost, realizedPnl=realized_pnl)
        for detail, lot in purchases:
            detail.update(
                remainingQuantity=None if lot.replaced else lot.quantity,
                costBasis=None if lot.replaced else lot.cost,
                realizedCostBasis=lot.sold_cost or None,
                realizedPnl=lot.realized_pnl if lot.sold_cost else None,
            )
        return list(positions.values())


def valuation(
    transactions: list[dict], quotes: dict[str, dict], cost_method: str = "moving_average"
) -> dict:
    positions, totals = [], {}
    with localcontext() as context:
        context.prec = 50
        for position in holdings(transactions, cost_method):
            currency = position["currency"]
            quote = quotes.get(position["ticker"])
            # No comparison of pence with pounds or transaction currencies with other quotes.
            price = quote["price"] if quote and quote["currency"] == currency else None
            quantity, cost = position["quantity"], position["cost"]
            value = (
                quantity * price if price is not None else (Decimal(0) if not quantity else None)
            )
            pnl = value - cost if value is not None else None
            position.update(
                {
                    "averagePrice": cost / quantity if quantity else None,
                    "currentPrice": price,
                    "quoteDate": quote["date"] if price is not None else None,
                    "quoteAsOf": quote.get("asOf") if price is not None else None,
                    "quoteSource": quote.get("source", "close") if price is not None else None,
                    "quoteAgeDays": quote.get("ageDays") if price is not None else None,
                    "marketValue": value,
                    "unrealizedPnl": pnl,
                    "unrealizedPnlPct": pnl / cost * 100 if pnl is not None and cost else None,
                }
            )
            total = totals.setdefault(
                currency,
                {
                    "currency": currency,
                    "cost": Decimal(0),
                    "marketValue": None,
                    "realizedPnl": Decimal(0),
                    "missingQuotes": 0,
                },
            )
            total["realizedPnl"] += position["realizedPnl"]
            if value is None:
                total["missingQuotes"] += 1
            elif quantity:
                total["cost"] += cost
                total["marketValue"] = (total["marketValue"] or Decimal(0)) + value
            positions.append(position)
        for total in totals.values():
            if total["marketValue"] is None and not total["missingQuotes"]:
                total["marketValue"] = Decimal(0)
            total["unrealizedPnl"] = (
                total["marketValue"] - total["cost"] if total["marketValue"] is not None else None
            )
            total["unrealizedPnlPct"] = (
                total["unrealizedPnl"] / total["cost"] * 100
                if total["unrealizedPnl"] is not None and total["cost"]
                else None
            )
    return {"positions": positions, "totals": list(totals.values())}
