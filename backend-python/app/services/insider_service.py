"""Service layer for aggregating and formatting insider transactions.

Handles:
- Filtering open-market trades vs. administrative grants/options/buybacks.
- Computing aggregate buy/sell summary metrics (`InsiderSummary`).
- Merging multiple same-day filings into a single daily chart marker (`InsiderChartMarker`)
  keyed on `publication_date` to avoid lookahead bias and prevent chart clutter.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from app.models.stocks import (
    InsiderChartMarker,
    InsiderSummary,
    InsiderTransactionItem,
    InsiderTransactionsResponse,
)


def _format_compact_shares(shares: int | None) -> str:
    """Format share count concisely for chart labels (e.g. 15000 -> '15k')."""
    if not shares:
        return ""
    n = abs(int(shares))
    if n >= 1_000_000:
        val = n / 1_000_000
        return f"{val:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        val = n / 1_000
        return f"{val:.1f}k".replace(".0k", "k")
    return str(n)


def build_insider_response(
    ticker: str,
    *,
    name: str | None = None,
    market: str | None = None,
    currency: str | None = None,
    transactions: list[InsiderTransactionItem],
    include_all: bool = False,
) -> InsiderTransactionsResponse:
    """Build the full API response with filtered list, summary, and daily chart markers."""
    if include_all:
        visible = list(transactions)
    else:
        visible = [
            tx
            for tx in transactions
            if tx.is_open_market and tx.transaction_type in ("buy", "sell")
        ]

    # Sort transactions newest first by publication_date, then trade_date
    visible.sort(
        key=lambda t: (
            t.publication_date,
            t.trade_date or t.publication_date,
            t.id or 0,
        ),
        reverse=True,
    )

    purchases_count = 0
    sales_count = 0
    purchases_shares = 0
    sales_shares = 0
    purchases_value = 0.0
    sales_value = 0.0
    summary_currency: str | None = currency

    for tx in visible:
        if tx.currency and not summary_currency:
            summary_currency = tx.currency
        sh = int(tx.shares or 0)
        val = float(tx.value or 0.0)
        if not val and sh and tx.price:
            val = float(sh) * float(tx.price)

        if tx.transaction_type == "buy":
            purchases_count += 1
            purchases_shares += sh
            purchases_value += val
        elif tx.transaction_type == "sell":
            sales_count += 1
            sales_shares += sh
            sales_value += val

    summary = InsiderSummary(
        total_purchases_count=purchases_count,
        total_sales_count=sales_count,
        total_purchases_shares=purchases_shares,
        total_sales_shares=sales_shares,
        total_purchases_value=round(purchases_value, 2),
        total_sales_value=round(sales_value, 2),
        net_shares=purchases_shares - sales_shares,
        net_value=round(purchases_value - sales_value, 2),
        currency=summary_currency,
    )

    # Group by publication_date for chart markers (prevents lookahead bias and merges same-day filings)
    by_day: dict[str, list[InsiderTransactionItem]] = defaultdict(list)
    for tx in visible:
        day_str = tx.publication_date.isoformat()
        by_day[day_str].append(tx)

    chart_markers: list[InsiderChartMarker] = []
    for day_str in sorted(by_day.keys()):
        day_txs = by_day[day_str]
        buy_sh = 0
        sell_sh = 0
        buy_val = 0.0
        sell_val = 0.0
        buy_cnt = 0
        sell_cnt = 0
        roles_seen: list[str] = []
        day_curr: str | None = None

        for tx in day_txs:
            if tx.currency and not day_curr:
                day_curr = tx.currency
            if tx.role and tx.role not in roles_seen:
                roles_seen.append(tx.role)
            sh = int(tx.shares or 0)
            val = float(tx.value or 0.0)
            if not val and sh and tx.price:
                val = float(sh) * float(tx.price)

            if tx.transaction_type == "buy":
                buy_cnt += 1
                buy_sh += sh
                buy_val += val
            elif tx.transaction_type == "sell":
                sell_cnt += 1
                sell_sh += sh
                sell_val += val

        net_sh = buy_sh - sell_sh
        net_val = buy_val - sell_val

        marker_type: Literal["Bullish", "Bearish", "Watch"]
        if buy_cnt > 0 and sell_cnt == 0:
            marker_type = "Bullish"
        elif sell_cnt > 0 and buy_cnt == 0:
            marker_type = "Bearish"
        elif buy_cnt > 0 and sell_cnt > 0:
            if net_val > 0 or (net_val == 0 and net_sh > 0):
                marker_type = "Bullish"
            elif net_val < 0 or (net_val == 0 and net_sh < 0):
                marker_type = "Bearish"
            else:
                marker_type = "Watch"
        else:
            marker_type = "Watch"

        display_shares = abs(net_sh) if net_sh != 0 else (buy_sh + sell_sh)
        display_value = abs(net_val) if net_val != 0 else (buy_val + sell_val)
        compact_sh = _format_compact_shares(display_shares)

        if marker_type == "Bullish":
            label = f"INS +{compact_sh}" if compact_sh else "INS BUY"
        elif marker_type == "Bearish":
            label = f"INS -{compact_sh}" if compact_sh else "INS SELL"
        else:
            label = f"INS ({len(day_txs)})"

        chart_markers.append(
            InsiderChartMarker(
                date=day_str,
                type=marker_type,
                label=label,
                shares=display_shares or None,
                value=round(display_value, 2) if display_value else None,
                currency=day_curr or summary_currency,
                transaction_count=len(day_txs),
                roles=roles_seen,
            )
        )

    return InsiderTransactionsResponse(
        ticker=ticker,
        name=name,
        market=market,
        currency=summary_currency,
        summary=summary,
        transactions=visible,
        chart_markers=chart_markers,
    )
