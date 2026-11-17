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
_FIRST_FIXING = date(2002, 1, 2)
_MAX_REQUEST_DAYS = 93
_PARALLEL_REQUESTS = 6
_TIMEOUT_SECONDS = 4
_CACHE_SECONDS = 300
_HISTORICAL_CACHE_SECONDS = 86400
_RETRY_SECONDS = 60

FxRates = dict[str, list[tuple[date, Decimal]]]
_cache: TTLCache[FxRates] = TTLCache(max_entries=128)
_locks = LockRegistry()


async def get_portfolio_fx(start: date, end: date, currencies: set[str]) -> FxRates:
    """Return dated PLN rates for the requested major currencies, oldest first."""
    wanted = {"GBP" if currency == "GBX" else major_currency(currency) for currency in currencies}
    wanted.discard("PLN")
    if not wanted:
        return {}

    # The previous fixing also covers weekends, bank holidays and today's
    # valuation before NBP has published a new table.
    first = max(start, _FIRST_FIXING + _LOOKBACK) - _LOOKBACK
    if first > end:
        return {}
    if (end - first).days < _MAX_REQUEST_DAYS:
        window = await _cached_rates(first, end, _CACHE_SECONDS)
        return {currency: window[currency].copy() for currency in wanted if currency in window}

    # Use calendar quarters so rolling ranges can reuse completed windows.
    windows = []
    quarter = date(first.year, (first.month - 1) // 3 * 3 + 1, 1)
    while quarter <= end:
        next_quarter = (
            date(quarter.year + 1, 1, 1) if quarter.month == 10
            else date(quarter.year, quarter.month + 3, 1)
        )
        last = min(next_quarter - timedelta(days=1), end)
        ttl = _HISTORICAL_CACHE_SECONDS if last < end else _CACHE_SECONDS
        windows.append((max(quarter, _FIRST_FIXING), last, ttl))
        quarter = next_quarter

    rates: FxRates = defaultdict(list)
    for index in range(0, len(windows), _PARALLEL_REQUESTS):
        batch = windows[index:index + _PARALLEL_REQUESTS]
        for window in await asyncio.gather(*(_cached_rates(*bounds) for bounds in batch)):
            for currency in wanted & window.keys():
                rates[currency].extend(fixing for fixing in window[currency] if fixing[0] >= first)
    return dict(rates)


async def _cached_rates(first: date, end: date, ttl: int) -> FxRates:
    key = f"{first}/{end}"
    rates = _cache.get(key)
    if rates is None:
        async with _locks.get(key):
            rates = _cache.get(key)
            if rates is None:
                rates = await _fetch_rates(first, end)
                _cache.set(key, rates, ttl if rates else _RETRY_SECONDS)
    return rates


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
