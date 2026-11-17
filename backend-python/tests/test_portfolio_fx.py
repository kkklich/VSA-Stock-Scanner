import asyncio
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services import portfolio_fx
from app.services.cache import LockRegistry, TTLCache


@pytest.fixture
def nbp(monkeypatch):
    client = httpx.AsyncClient
    monkeypatch.setattr(portfolio_fx, "_cache", TTLCache())
    monkeypatch.setattr(portfolio_fx, "_locks", LockRegistry())

    def mock(handler):
        monkeypatch.setattr(
            portfolio_fx.httpx,
            "AsyncClient",
            lambda: client(transport=httpx.MockTransport(handler)),
        )

    return mock


async def test_fetches_recent_fixings_once_for_different_wallet_currencies(nbp):
    calls = []

    async def table(request):
        calls.append(request.url)
        await asyncio.sleep(0)
        return httpx.Response(
            200,
            json=[
                {
                    "effectiveDate": "2026-11-10",
                    "rates": [{"code": "USD", "mid": 3.61}, {"code": "GBP", "mid": 4.92}],
                },
                {
                    "effectiveDate": "2026-11-06",
                    "rates": [{"code": "GBP", "mid": 4.94}, {"code": "EUR", "mid": 0}],
                },
            ],
        )

    nbp(table)
    start, end = date(2026, 11, 8), date(2026, 11, 12)
    assert await portfolio_fx.get_portfolio_fx(start, end, {"PLN"}) == {}
    usd, pounds = await asyncio.gather(
        portfolio_fx.get_portfolio_fx(start, end, {"USD"}),
        portfolio_fx.get_portfolio_fx(start, end, {"GBp", "GBX", "EUR"}),
    )

    assert usd == {"USD": [(date(2026, 11, 10), Decimal("3.61"))]}
    assert pounds == {
        "GBP": [(date(2026, 11, 6), Decimal("4.94")), (date(2026, 11, 10), Decimal("4.92"))]
    }
    assert calls == [
        httpx.URL(
            "https://api.nbp.pl/api/exchangerates/tables/a/2026-11-01/2026-11-12/?format=json"
        )
    ]


async def test_service_outage_leaves_rates_unavailable(nbp):
    calls = []

    def unavailable(request):
        calls.append(request)
        return httpx.Response(503)

    nbp(unavailable)
    day = date(2026, 11, 12)
    assert await portfolio_fx.get_portfolio_fx(day, day, {"USD"}) == {}
    assert await portfolio_fx.get_portfolio_fx(day, day, {"EUR"}) == {}
    assert len(calls) == 1


async def test_long_ranges_keep_fixings_across_quarter_boundaries(nbp):
    calls = []
    first_days = (date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1))

    def table(request):
        first, last = map(date.fromisoformat, request.url.path.rstrip("/").split("/")[-2:])
        calls.append(first)
        assert (last - first).days < 93
        return httpx.Response(200, json=[{
            "effectiveDate": last.isoformat(),
            "rates": [{"code": "USD", "mid": 3.61}],
        }])

    nbp(table)
    end = date(2026, 7, 12)
    rates = await portfolio_fx.get_portfolio_fx(date(2026, 1, 10), end, {"USD"})
    assert rates == {"USD": [
        (date(2026, 3, 31), Decimal("3.61")),
        (date(2026, 6, 30), Decimal("3.61")),
        (end, Decimal("3.61")),
    ]}
    assert await portfolio_fx.get_portfolio_fx(date(2026, 1, 11), end, {"USD"}) == rates
    assert sorted(calls) == list(first_days)
