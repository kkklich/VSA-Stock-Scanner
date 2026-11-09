"""Service layer for aggregating and formatting insider transactions.

Handles:
- Filtering open-market trades vs. administrative grants/options/buybacks.
- Computing aggregate buy/sell summary metrics (`InsiderSummary`).
- Merging multiple same-day filings into a single daily chart marker (`InsiderChartMarker`)
  keyed on `publication_date` to avoid lookahead bias and prevent chart clutter.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Literal

from app.models.stocks import (
    InsiderChartMarker,
    InsiderPersonSummary,
    InsiderSummary,
    InsiderTransactionItem,
    InsiderTransactionsResponse,
)


def _transaction_value(tx: InsiderTransactionItem) -> Decimal | None:
    """An absent value is unknown, while an explicitly reported zero is valid."""
    if tx.value is not None:
        result = Decimal(str(tx.value))
    elif tx.shares is not None and tx.price is not None:
        result = Decimal(tx.shares) * Decimal(str(tx.price))
    else:
        return None
    return result if result.is_finite() and result >= 0 else None


def summarize_insiders(transactions: list[InsiderTransactionItem]) -> list[InsiderPersonSummary]:
    """Keep named people, reported currencies and unknown amounts separate."""
    groups: dict[tuple[str, str | None], tuple[str, list[InsiderTransactionItem]]] = {}
    for tx in transactions:
        name = " ".join((tx.insider_name or "").split())
        if not name or tx.transaction_type not in ("buy", "sell"):
            continue
        currency = tx.currency.strip().upper() if tx.currency else None
        key = (name.casefold(), currency)
        if key not in groups:
            groups[key] = (name, [])
        groups[key][1].append(tx)

    def shares(items: list[InsiderTransactionItem]) -> int | None:
        if any(tx.shares is None or tx.shares < 0 for tx in items):
            return None
        return sum(tx.shares for tx in items if tx.shares is not None)

    def value(items: list[InsiderTransactionItem]) -> float | None:
        amounts = [_transaction_value(tx) for tx in items]
        if any(amount is None for amount in amounts):
            return None
        return round(float(sum((a for a in amounts if a is not None), Decimal(0))), 2)

    result = []
    for (_, currency), (name, items) in groups.items():
        buys = [tx for tx in items if tx.transaction_type == "buy"]
        sells = [tx for tx in items if tx.transaction_type == "sell"]
        bought, sold = shares(buys), shares(sells)
        buy_value, sell_value = value(buys), value(sells)
        result.append(InsiderPersonSummary(
            insider_name=name,
            currency=currency,
            total_purchases_count=len(buys),
            total_sales_count=len(sells),
            total_purchases_shares=bought,
            total_sales_shares=sold,
            total_purchases_value=buy_value,
            total_sales_value=sell_value,
            net_shares=None if bought is None or sold is None else bought - sold,
            net_value=(
                None if buy_value is None or sell_value is None
                else round(buy_value - sell_value, 2)
            ),
        ))
    return sorted(result, key=lambda row: (row.insider_name.casefold(), row.currency or ""))


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
    warnings: list[str] | None = None,
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
    response_warnings = list(warnings or [])
    cash_trades = [tx for tx in visible if tx.transaction_type in ("buy", "sell")]
    if any(tx.shares is None or _transaction_value(tx) is None for tx in cash_trades):
        response_warnings.append(
            "Część zakupów lub sprzedaży ma nieodczytaną liczbę akcji albo wartość. "
            "Łączne sumy obejmują tylko znane dane; pełny bilans osoby może być nieznany."
        )
    if any(not tx.insider_name for tx in cash_trades):
        response_warnings.append(
            "Transakcje bez rozpoznanej osoby pokazano w szczegółach, "
            "ale pominięto w podsumowaniu osób."
        )
    reported_currencies = {
        tx.currency.strip().upper() if tx.currency and tx.currency.strip() else None
        for tx in cash_trades
    }
    if len(reported_currencies) > 1:
        response_warnings.append(
            "Raporty zawierają różne waluty. Porównuj wartości w podsumowaniu osób, "
            "gdzie każda waluta jest liczona oddzielnie."
        )

    purchases_count = 0
    sales_count = 0
    purchases_shares = 0
    sales_shares = 0
    purchases_value = 0.0
    sales_value = 0.0
    summary_currency = (
        next(iter(reported_currencies))
        if len(reported_currencies) == 1 and None not in reported_currencies
        else currency if not reported_currencies or reported_currencies == {None} else None
    )

    for tx in visible:
        sh = int(tx.shares or 0)
        val = float(_transaction_value(tx) or 0)

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

    # Group by publication_date for chart markers (prevents lookahead bias
    # and merges same-day filings)
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
        day_cash_trades = [tx for tx in day_txs if tx.transaction_type in ("buy", "sell")]
        day_currencies = {
            tx.currency.strip().upper() if tx.currency and tx.currency.strip() else None
            for tx in day_cash_trades
        }
        comparable_values = len(day_currencies) == 1 and None not in day_currencies
        complete_shares = all(tx.shares is not None for tx in day_cash_trades)
        complete_values = all(_transaction_value(tx) is not None for tx in day_cash_trades)
        day_curr = next(iter(day_currencies)) if comparable_values else None

        for tx in day_txs:
            if tx.role and tx.role not in roles_seen:
                roles_seen.append(tx.role)
            sh = int(tx.shares or 0)
            val = float(_transaction_value(tx) or 0)

            if tx.transaction_type == "buy":
                buy_cnt += 1
                buy_sh += sh
                buy_val += val
            elif tx.transaction_type == "sell":
                sell_cnt += 1
                sell_sh += sh
                sell_val += val

        net_sh = buy_sh - sell_sh
        net_val = buy_val - sell_val if comparable_values and complete_values else 0.0

        marker_type: Literal["Bullish", "Bearish", "Watch"]
        if buy_cnt > 0 and sell_cnt == 0:
            marker_type = "Bullish"
        elif sell_cnt > 0 and buy_cnt == 0:
            marker_type = "Bearish"
        elif buy_cnt > 0 and sell_cnt > 0:
            if not complete_shares and not (comparable_values and complete_values):
                marker_type = "Watch"
            elif net_val > 0 or (net_val == 0 and net_sh > 0):
                marker_type = "Bullish"
            elif net_val < 0 or (net_val == 0 and net_sh < 0):
                marker_type = "Bearish"
            else:
                marker_type = "Watch"
        else:
            marker_type = "Watch"

        display_shares = (
            (abs(net_sh) if net_sh != 0 else (buy_sh + sell_sh)) if complete_shares else None
        )
        display_value = (
            (abs(net_val) if net_val != 0 else (buy_val + sell_val))
            if comparable_values and complete_values else None
        )
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
                currency=day_curr,
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
        by_insider=summarize_insiders(visible),
        warnings=list(dict.fromkeys(response_warnings)),
    )
