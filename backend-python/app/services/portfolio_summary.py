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
HoldingKey = tuple[str, str, str]
PositionValues = dict[HoldingKey, Decimal | None]


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


def _historical_values(wallets, quote_history, start):
    holdings_cache = {}
    values = {}
    with localcontext() as context:
        context.prec = 50
        for offset in range(SUMMARY_DAYS):
            day = start + timedelta(days=offset)
            values[day] = dict(_historical_positions(wallets, quote_history, day, holdings_cache))
    return values


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


async def portfolio_summary(wallets, valued_wallets, quote_history, today: date) -> dict:
    start = today - timedelta(days=SUMMARY_DAYS)
    values_by_date = await run_in_threadpool(_historical_values, wallets, quote_history, start)
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
    values_by_date[today] = current_positions
    currencies = {
        currency
        for positions in values_by_date.values()
        for (_, _, currency), value in positions.items()
        if value is not None and currency != "PLN"
    }
    rates = await get_portfolio_fx(start, today, currencies) if currencies else {}
    yesterday = today - timedelta(days=1)
    with localcontext() as context:
        context.prec = 50
        points = {
            day: _value_point(day, values, rates, len(stale_holdings) if day == today else 0)
            for day, values in values_by_date.items()
        }
        current, current_pln = points[today]
        history = [point for point, _ in points.values()]
        if stale_holdings:
            # Keep last-known values in the headline. Apply the same quote age
            # cutoff throughout the chart so stale quotes do not reappear today.
            chart_positions = {
                key: None if key in stale_holdings else value
                for key, value in current_positions.items()
            }
            history[-1], _ = _value_point(today, chart_positions, rates, len(stale_holdings))
        changes = {
            label: _change(
                day, current_positions, values_by_date[day], current_pln, points[day][1],
                stale_holdings,
            )
            for label, day in (("dayChange", yesterday), ("weekChange", start))
        }
        return {
            "currency": "PLN",
            "current": current,
            "history": history,
            **changes,
            "currencyTotals": _currency_totals(current_positions),
            "missingHoldings": sorted(
                missing_holdings,
                key=lambda item: (item["ticker"], item["walletName"], item["currency"]),
            ),
        }
