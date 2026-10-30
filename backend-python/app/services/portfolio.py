"""FIFO and moving-average accounting in quote currency, without guessed FX rates."""

from collections import deque
from decimal import Decimal, localcontext


class PortfolioError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status


def holdings(transactions: list[dict], cost_method: str = "moving_average") -> list[dict]:
    positions = {}
    lots = {}
    # Preserve insertion order on a single date: the UI records trades in execution order.
    with localcontext() as context:
        context.prec = 50
        for trade in sorted(transactions, key=lambda t: t["date"]):
            key = (trade["ticker"], trade["currency"])
            position = positions.setdefault(
                key,
                {
                    "ticker": key[0],
                    "currency": key[1],
                    "quantity": Decimal(0),
                    "cost": Decimal(0),
                    "realizedPnl": Decimal(0),
                },
            )
            quantity, price, fees = (Decimal(trade[k]) for k in ("quantity", "price", "fees"))
            if trade["side"] == "buy":
                position["quantity"] += quantity
                position["cost"] += quantity * price + fees
                if cost_method == "fifo":
                    lots.setdefault(key, deque()).append([quantity, quantity * price + fees])
            else:
                if quantity > position["quantity"]:
                    raise PortfolioError("insufficient_shares")
                cost = (
                    position["cost"]
                    if quantity == position["quantity"]
                    else position["cost"] * quantity / position["quantity"]
                )
                if cost_method == "fifo":
                    remaining, cost = quantity, Decimal(0)
                    while remaining:
                        lot = lots[key][0]
                        sold = min(remaining, lot[0])
                        allocated = lot[1] if sold == lot[0] else lot[1] * sold / lot[0]
                        cost += allocated
                        lot[0] -= sold
                        lot[1] -= allocated
                        remaining -= sold
                        if not lot[0]:
                            lots[key].popleft()
                    # Re-sum remaining lots to avoid a rounding residue when a position closes.
                    position["cost"] = sum((lot[1] for lot in lots[key]), Decimal(0))
                else:
                    position["cost"] -= cost
                position["quantity"] -= quantity
                position["realizedPnl"] += quantity * price - fees - cost
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
                    "marketValue": Decimal(0),
                    "realizedPnl": Decimal(0),
                    "missingQuotes": 0,
                },
            )
            total["cost"] += cost
            total["realizedPnl"] += position["realizedPnl"]
            if value is None:
                total["missingQuotes"] += 1
            else:
                total["marketValue"] += value
            positions.append(position)
        for total in totals.values():
            if total["missingQuotes"]:
                total["marketValue"] = None
            total["unrealizedPnl"] = (
                total["marketValue"] - total["cost"] if total["marketValue"] is not None else None
            )
            total["unrealizedPnlPct"] = (
                total["unrealizedPnl"] / total["cost"] * 100
                if total["unrealizedPnl"] is not None and total["cost"]
                else None
            )
    return {"positions": positions, "totals": list(totals.values())}
