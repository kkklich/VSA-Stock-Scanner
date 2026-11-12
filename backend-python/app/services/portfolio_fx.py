"""Load official NBP Table A middle exchange rates in PLN."""

import asyncio
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from app.markets import major_currency
from app.services.cache import LockRegistry, TTLCache

logger = logging.getLogger(__name__)

_TABLE_URL = "https://api.nbp.pl/api/exchangerates/tables/a"
_LOOKBACK = timedelta(days=7)
_TIMEOUT_SECONDS = 4
_CACHE_SECONDS = 300
_RETRY_SECONDS = 60

FxRates = dict[str, list[tuple[date, Decimal]]]
_cache: TTLCache[FxRates] = TTLCache(max_entries=16)
_locks = LockRegistry()


async def get_portfolio_fx(start: date, end: date, currencies: set[str]) -> FxRates:
    """Return dated PLN rates for the requested major currencies, oldest first."""
    wanted = {"GBP" if currency == "GBX" else major_currency(currency) for currency in currencies}
    wanted.discard("PLN")
    if not wanted:
        return {}

    # The previous fixing also covers weekends, bank holidays and today's
    # valuation before NBP has published a new table.
    first = start - _LOOKBACK
    key = f"{first}/{end}"
    rates = _cache.get(key)
    if rates is None:
        async with _locks.get(key):
            rates = _cache.get(key)
            if rates is None:
                rates = await _fetch_rates(first, end)
                _cache.set(key, rates, _CACHE_SECONDS if rates else _RETRY_SECONDS)
    return {currency: rates[currency].copy() for currency in wanted if currency in rates}


async def _fetch_rates(first: date, end: date) -> FxRates:
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS), httpx.AsyncClient() as client:
            response = await client.get(f"{_TABLE_URL}/{first}/{end}/", params={"format": "json"})
            response.raise_for_status()
            tables = response.json(parse_float=Decimal)
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        logger.warning("NBP portfolio exchange rates unavailable: %s", exc)
        return {}

    if not isinstance(tables, list):
        return {}

    rates: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for table in tables:
        try:
            day = date.fromisoformat(table["effectiveDate"])
            entries = table["rates"]
        except (KeyError, TypeError, ValueError):
            continue
        if not first <= day <= end or not isinstance(entries, list):
            continue
        for entry in entries:
            try:
                currency = entry["code"]
                rate = Decimal(str(entry["mid"]))
            except (InvalidOperation, KeyError, TypeError):
                continue
            if isinstance(currency, str) and rate.is_finite() and rate > 0:
                rates[currency][day] = rate
    return {currency: sorted(daily_rates.items()) for currency, daily_rates in rates.items()}
