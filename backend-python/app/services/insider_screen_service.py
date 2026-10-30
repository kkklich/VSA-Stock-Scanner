"""Insider screener over stored filings; never fetch providers per ranking row."""

from __future__ import annotations

import math
from typing import Literal

from app.markets import to_pln_or_none
from app.models.stocks import InsiderScreenSummary, InsiderTransactionItem, StockRankingItem

InsiderActivity = Literal["all", "any", "buy", "sell", "netBuy", "netSell"]


def summarize_insider_activity(
    transactions: list[InsiderTransactionItem],
) -> InsiderScreenSummary:
    counts = {"buy": 0, "sell": 0}
    shares = {"buy": 0, "sell": 0}
    values = {"buy": 0.0, "sell": 0.0}
    unknown: set[str] = set()
    for tx in transactions:
        side = tx.transaction_type
        if not tx.is_open_market or side not in counts:
            continue
        counts[side] += 1
        shares[side] += tx.shares or 0
        amount = tx.value
        if amount is None and tx.shares is not None and tx.price is not None:
            amount = tx.shares * tx.price
        pln = to_pln_or_none(amount, tx.currency)
        if pln is None or not math.isfinite(pln) or pln < 0:
            unknown.add(side)
        else:
            values[side] += pln
    buy = None if "buy" in unknown else round(values["buy"], 2)
    sell = None if "sell" in unknown else round(values["sell"], 2)
    return InsiderScreenSummary(
        purchases_count=counts["buy"], sales_count=counts["sell"],
        purchases_shares=shares["buy"], sales_shares=shares["sell"],
        purchases_value_pln=buy, sales_value_pln=sell,
        net_value_pln=round(buy - sell, 2) if buy is not None and sell is not None else None,
    )


def screen_insider_activity(
    rows: list[StockRankingItem],
    transactions: dict[str, list[InsiderTransactionItem]],
    activity: InsiderActivity,
    min_value: float | None,
) -> list[StockRankingItem]:
    """Apply the selected side/threshold before pagination, without mutating cached rows."""
    result = []
    for row in rows:
        summary = summarize_insider_activity(transactions.get(row.ticker.casefold(), []))
        buy, sell = summary.purchases_value_pln, summary.sales_value_pln
        if activity == "buy":
            matches = summary.purchases_count > 0
            value = buy
        elif activity == "sell":
            matches = summary.sales_count > 0
            value = sell
        elif activity in ("netBuy", "netSell"):
            net = summary.net_value_pln
            value = None if net is None else net if activity == "netBuy" else -net
            matches = value is not None and value > 0
        else:
            matches = summary.purchases_count + summary.sales_count > 0
            value = buy + sell if buy is not None and sell is not None else None
        if matches and (min_value is None or (value is not None and value >= min_value)):
            result.append(row.model_copy(update={"insider_activity": summary}))
    return result
