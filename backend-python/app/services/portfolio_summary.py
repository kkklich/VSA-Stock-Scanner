"""Combine tracked holdings across wallets using dated quotes and exchange rates."""

from bisect import bisect_right
from calendar import monthrange
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal, localcontext
from itertools import chain
from operator import itemgetter
from typing import Literal

from starlette.concurrency import run_in_threadpool

from app.markets import major_currency
from app.services.portfolio import holdings
from app.services.portfolio_fx import get_portfolio_fx

SUMMARY_DAYS = 7
MAX_PRICE_AGE_DAYS = 7
MAX_RATE_AGE_DAYS = 7
HoldingKey = tuple[str, str, str]
PositionValues = dict[HoldingKey, Decimal | None]
HistoryRange = Literal["1d", "1w", "1m", "3m", "6m", "1y", "all"]
_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}
_by_date = itemgetter("date")
_fixing_date = itemgetter(0)


def history_start_date(wallets, today: date, period: HistoryRange) -> date:
    if period == "1d":
        return today - timedelta(days=1)
    if period == "1w":
        return today - timedelta(days=SUMMARY_DAYS)

    first_entry = min(
        (entry["date"] for wallet in wallets for entry in wallet["ledger"]),
        default=today.isoformat(),
    )
    first_day = min(date.fromisoformat(first_entry), today)
    if period == "all":
        return first_day
    year, month_index = divmod(today.year * 12 + today.month - 1 - _MONTHS[period], 12)
    month = month_index + 1
    return max(first_day, date(year, month, min(today.day, monthrange(year, month)[1])))


def wallet_baseline_dates(wallets, today: date, period: HistoryRange | None) -> dict[str, date]:
    if period is None:
        return {}
    return {
        wallet["id"]: history_start_date([wallet], today, period)
        for wallet in wallets if wallet["ledger"]
    }


def _currency_totals(positions: PositionValues):
    totals = {}
    for (_, _, currency), value in positions.items():
        total = totals.setdefault(
            currency, {"currency": currency, "marketValue": None, "missingQuotes": 0}
        )
        if value is None:
            total["missingQuotes"] += 1
        else:
            total["marketValue"] = (total["marketValue"] or Decimal(0)) + value
    return sorted(totals.values(), key=lambda total: total["currency"])


def _historical_positions(wallets, ledgers, quote_history, day, holdings_cache):
    quotes = {}
    for ticker, history in quote_history.items():
        index = bisect_right(history, day, key=_by_date)
        quote = history[index - 1] if index else None
        if quote and (day - quote["date"]).days <= MAX_PRICE_AGE_DAYS:
            quotes[ticker] = quote

    cutoff = day.isoformat()
    for wallet in wallets:
        ledger = ledgers[wallet["id"]]
        size = bisect_right(ledger, cutoff, key=_by_date)
        ledger_size, positions = holdings_cache.get(wallet["id"], (0, []))
        # Each cutoff contains all earlier entries, so the same count means the
        # same ledger. Reuse holdings on days without any trades or snapshots.
        if ledger_size != size:
            positions = holdings(ledger[:size], wallet["costMethod"])
            holdings_cache[wallet["id"]] = (size, positions)
        for position in positions:
            if not position["quantity"]:
                continue
            quote = quotes.get(position["ticker"])
            currency = position["currency"]
            value = (
                position["quantity"] * quote["price"]
                if quote and currency == quote["currency"]
                else None
            )
            yield (wallet["id"], position["ticker"], currency), value


def _historical_values(wallets, quote_history, days: Iterable[date]):
    ledgers = {wallet["id"]: sorted(wallet["ledger"], key=_by_date) for wallet in wallets}
    holdings_cache = {}
    for day in days:
        yield day, dict(_historical_positions(wallets, ledgers, quote_history, day, holdings_cache))


def _pln_rate(currency, day, rates):
    if currency == "PLN":
        return Decimal(1)
    major = major_currency(currency)
    history = rates.get(major, [])
    index = bisect_right(history, day, key=_fixing_date)
    if index:
        effective, rate = history[index - 1]
        if (day - effective).days <= MAX_RATE_AGE_DAYS:
            return rate / 100 if major != currency else rate
    return None


def _value_point(day, positions: PositionValues, rates, stale_quotes=0):
    exchange_rates = {
        currency: _pln_rate(currency, day, rates)
        for currency in {key[2] for key, value in positions.items() if value is not None}
    }
    converted = {}
    missing_quotes = 0
    for key, value in positions.items():
        if value is None:
            missing_quotes += 1
            continue
        rate = exchange_rates[key[2]]
        if rate is not None:
            converted[key] = value * rate
    point = {
        "date": day,
        "value": sum(converted.values(), Decimal(0)) if converted or not positions else None,
        "missingQuotes": missing_quotes,
        "missingRates": sorted(
            currency for currency, rate in exchange_rates.items() if rate is None
        ),
        "staleQuotes": stale_quotes,
    }
    return point, converted


def _change(since, current_positions, previous_positions, current, previous, stale_holdings):
    active = current_positions.keys() | previous_positions.keys()
    # An absent position is worth zero. An open position with missing data is
    # excluded at both endpoints, so restored coverage cannot create a gain.
    comparable = active - (
        (current_positions.keys() - current.keys())
        | (previous_positions.keys() - previous.keys())
        | stale_holdings
    )
    if active and not comparable:
        return None
    zero = Decimal(0)
    baseline = sum((previous.get(key, zero) for key in comparable), zero)
    amount = sum((current.get(key, zero) for key in comparable), zero) - baseline
    return {
        "amount": amount,
        "percent": amount / baseline * 100 if baseline else None,
        "since": since,
        "partial": comparable != active,
    }


def _positions_by_wallet(positions: PositionValues) -> dict[str, PositionValues]:
    grouped = defaultdict(dict)
    for key, value in positions.items():
        grouped[key[0]][key] = value
    return grouped


def _value_history(
    wallet_ids: list[str], valuation_days, current_positions, stale_holdings, history_start,
    today, rates,
    wallet_baselines: dict[str, date],
):
    baselines = {
        today - timedelta(days=1): "dayChange",
        today - timedelta(days=SUMMARY_DAYS): "weekChange",
    }
    wallet_comparisons = defaultdict(list)
    for wallet_id in wallet_ids:
        for day, key in baselines.items():
            wallet_comparisons[day].append((wallet_id, key))
        selected_day = wallet_baselines.get(wallet_id)
        if selected_day is not None and selected_day < today:
            wallet_comparisons[selected_day].append((wallet_id, "rangeChange"))
    history = []
    changes = {}
    with localcontext() as context:
        context.prec = 50
        current, current_pln = _value_point(today, current_positions, rates, len(stale_holdings))
        wallet_positions = _positions_by_wallet(current_positions)
        wallet_pln = {}
        wallet_summaries = {}
        for wallet_id in wallet_ids:
            positions = wallet_positions.get(wallet_id, {})
            point, wallet_pln[wallet_id] = _value_point(
                today, positions, rates, len(stale_holdings & positions.keys())
            )
            wallet_summaries[wallet_id] = {
                "walletId": wallet_id, "current": point, "rangeChange": None,
            }
        for day, positions in valuation_days:
            point, converted = _value_point(day, positions, rates)
            if day >= history_start:
                history.append(point)
            if day in baselines:
                changes[baselines[day]] = _change(
                    day, current_positions, positions, current_pln, converted, stale_holdings
                )
            if day in wallet_comparisons:
                previous_positions = _positions_by_wallet(positions)
                previous_pln = _positions_by_wallet(converted)
                for wallet_id, change_key in wallet_comparisons[day]:
                    wallet_summaries[wallet_id][change_key] = _change(
                        day, wallet_positions.get(wallet_id, {}),
                        previous_positions.get(wallet_id, {}), wallet_pln[wallet_id],
                        previous_pln.get(wallet_id, {}), stale_holdings,
                    )
        latest = current
        if stale_holdings:
            # Keep last-known quotes in the headline and apply the chart's quote age limit today.
            chart_positions = {
                key: None if key in stale_holdings else value
                for key, value in current_positions.items()
            }
            latest, _ = _value_point(today, chart_positions, rates, len(stale_holdings))
        history.append(latest)
        return (
            current, history, changes, _currency_totals(current_positions),
            list(wallet_summaries.values()),
        )


async def portfolio_summary(
    wallets, valued_wallets, quote_history, today: date, history_start: date,
    wallet_baselines: dict[str, date],
) -> dict:
    baseline_days = {
        today - timedelta(days=1), today - timedelta(days=SUMMARY_DAYS), *wallet_baselines.values(),
    }
    extra_days = sorted(day for day in baseline_days if day < history_start)
    start = extra_days[0] if extra_days else history_start
    chart_days = (
        history_start + timedelta(days=offset) for offset in range((today - history_start).days)
    )
    current_positions = {}
    missing_holdings = []
    stale_holdings = set()
    for wallet in valued_wallets:
        for position in wallet["positions"]:
            if not position["quantity"]:
                continue
            ticker, currency = position["ticker"], position["currency"]
            key = (wallet["id"], ticker, currency)
            current_positions[key] = position["marketValue"]
            if position["marketValue"] is None:
                missing_holdings.append({
                    "ticker": ticker, "currency": currency,
                    "walletId": wallet["id"], "walletName": wallet["name"],
                })
            quote_date = position["quoteDate"]
            if quote_date and (today - quote_date).days > MAX_PRICE_AGE_DAYS:
                stale_holdings.add(key)
    currencies = {
        quotes[-1]["currency"] for quotes in quote_history.values() if quotes
    }
    currencies.update(currency for (_, _, currency), value in current_positions.items()
                      if value is not None)
    currencies.discard("PLN")
    rates = await get_portfolio_fx(start, today, currencies) if currencies else {}
    current, history, changes, totals, wallet_summaries = await run_in_threadpool(
        _value_history, [wallet["id"] for wallet in valued_wallets],
        _historical_values(wallets, quote_history, chain(extra_days, chart_days)),
        current_positions, stale_holdings, history_start, today, rates, wallet_baselines,
    )
    return {
        "currency": "PLN",
        "current": current,
        "history": history,
        **changes,
        "wallets": wallet_summaries,
        "currencyTotals": totals,
        "missingHoldings": sorted(
            missing_holdings,
            key=lambda item: (item["ticker"], item["walletName"], item["currency"]),
        ),
    }
