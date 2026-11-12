"""Combine tracked holdings across wallets using dated quotes and exchange rates."""

from datetime import date, timedelta
from decimal import Decimal, localcontext

from starlette.concurrency import run_in_threadpool

from app.markets import major_currency
from app.services.portfolio import holdings
from app.services.portfolio_fx import get_portfolio_fx

SUMMARY_DAYS = 7
MAX_PRICE_AGE_DAYS = 7
MAX_RATE_AGE_DAYS = 7


def _currency_totals(positions):
    totals = {}
    for position in positions:
        if not position["quantity"]:
            continue
        currency = position["currency"]
        total = totals.setdefault(
            currency, {"currency": currency, "marketValue": Decimal(0), "missingQuotes": 0}
        )
        value = position["marketValue"]
        if value is None:
            total["missingQuotes"] += 1
            total["marketValue"] = None
        elif total["marketValue"] is not None:
            total["marketValue"] += value
    return sorted(totals.values(), key=lambda total: total["currency"])


def _historical_positions(wallets, quote_history, day, holdings_cache):
    quotes = {}
    for ticker, history in quote_history.items():
        quote = next((quote for quote in reversed(history) if quote["date"] <= day), None)
        if quote and (day - quote["date"]).days <= MAX_PRICE_AGE_DAYS:
            quotes[ticker] = quote

    cutoff = day.isoformat()
    for wallet in wallets:
        ledger = [entry for entry in wallet["ledger"] if entry["date"] <= cutoff]
        ledger_size, positions = holdings_cache.get(wallet["id"], (0, []))
        # Each cutoff contains all earlier entries, so the same count means the
        # same ledger. Reuse holdings on days without any trades or snapshots.
        if ledger_size != len(ledger):
            positions = holdings(ledger, wallet["costMethod"])
            holdings_cache[wallet["id"]] = (len(ledger), positions)
        for position in positions:
            quote = quotes.get(position["ticker"])
            value = (
                position["quantity"] * quote["price"]
                if quote and position["currency"] == quote["currency"]
                else None
            )
            yield {**position, "marketValue": value}


def _historical_totals(wallets, quote_history, start):
    holdings_cache = {}
    totals = {}
    with localcontext() as context:
        context.prec = 50
        for offset in range(SUMMARY_DAYS):
            day = start + timedelta(days=offset)
            positions = _historical_positions(wallets, quote_history, day, holdings_cache)
            totals[day] = _currency_totals(positions)
    return totals


def _pln_rate(currency, day, rates):
    if currency == "PLN":
        return Decimal(1)
    major = major_currency(currency)
    for effective, rate in reversed(rates.get(major, [])):
        if effective <= day:
            if (day - effective).days > MAX_RATE_AGE_DAYS:
                return None
            return rate / 100 if major != currency else rate
    return None


def _value_point(day, totals, rates, stale_quotes=0):
    value = Decimal(0)
    missing_quotes = 0
    missing_rates = []
    for total in totals:
        missing_quotes += total["missingQuotes"]
        if total["marketValue"] is None:
            continue
        rate = _pln_rate(total["currency"], day, rates)
        if rate is None:
            missing_rates.append(total["currency"])
        else:
            value += total["marketValue"] * rate
    return {
        "date": day,
        "value": None if missing_quotes or missing_rates else value,
        "missingQuotes": missing_quotes,
        "missingRates": missing_rates,
        "staleQuotes": stale_quotes,
    }


def _change(current, previous):
    if current["value"] is None or previous["value"] is None or current["staleQuotes"]:
        return None
    baseline = previous["value"]
    amount = current["value"] - baseline
    return {
        "amount": amount,
        "percent": amount / baseline * 100 if baseline else None,
        "since": previous["date"],
    }


async def portfolio_summary(wallets, valued_wallets, quote_history, today: date) -> dict:
    start = today - timedelta(days=SUMMARY_DAYS)
    totals_by_date = await run_in_threadpool(_historical_totals, wallets, quote_history, start)
    positions = [position for wallet in valued_wallets for position in wallet["positions"]]
    stale_quotes = sum(
        position["quantity"] > 0
        and position["quoteAgeDays"] is not None
        and position["quoteAgeDays"] > MAX_PRICE_AGE_DAYS
        for position in positions
    )
    with localcontext() as context:
        context.prec = 50
        totals_by_date[today] = _currency_totals(positions)
    currencies = {
        total["currency"]
        for totals in totals_by_date.values()
        for total in totals
        if total["marketValue"] is not None and total["currency"] != "PLN"
    }
    rates = await get_portfolio_fx(start, today, currencies) if currencies else {}
    with localcontext() as context:
        context.prec = 50
        points = [
            _value_point(day, totals, rates, stale_quotes if day == today else 0)
            for day, totals in totals_by_date.items()
        ]
        current = points[-1]
        return {
            "currency": "PLN",
            "current": current,
            "history": points,
            "dayChange": _change(current, points[-2]),
            "weekChange": _change(current, points[0]),
            "currencyTotals": totals_by_date[today],
        }
