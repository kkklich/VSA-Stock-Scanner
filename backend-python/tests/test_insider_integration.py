"""ESPI detail, per-person balances and refresh reach the chart's API."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import get_history_cache, get_quote_repository
from app.main import app
from app.models.stocks import InsiderTransactionItem
from app.routers import stocks
from app.services.cache import TTLCache
from app.services.espi_client import EspiClient
from app.services.insider_service import build_insider_response


def trade(**changes):
    return InsiderTransactionItem(**{
        "publication_date": date(2026, 9, 16),
        "trade_date": date(2026, 9, 9),
        "insider_name": "Jan Testowy", "role": "Prezes Zarządu",
        "transaction_type": "buy", "is_open_market": True,
        "shares": 5000, "price": 198, "currency": "PLN", "value": 990000,
        "source": "espi", "source_url": "https://www.gpw.pl/komunikat?geru_id=123",
        **changes,
    })


def test_person_balances_keep_currency_and_actual_zero_separate_from_unknown():
    response = build_insider_response("TEST", transactions=[
        trade(),
        trade(insider_name=" JAN   TESTOWY ", shares=None, value=None),
        trade(transaction_type="sell", shares=100, price=0, value=0),
        trade(currency="EUR", shares=10, price=5, value=None),
        trade(transaction_type="gift", shares=100000, is_open_market=False),
        trade(insider_name=None, shares=100),
    ], include_all=True)
    assert len(response.by_insider) == 2
    by_currency = {person.currency: person for person in response.by_insider}
    pln = by_currency["PLN"]
    assert pln.total_purchases_count == 2
    assert pln.total_sales_count == 1
    assert pln.total_purchases_shares is None
    assert pln.total_purchases_value is None
    assert pln.total_sales_shares == 100
    assert pln.total_sales_value == 0
    assert pln.net_shares is None
    assert pln.net_value is None
    assert by_currency["EUR"].total_purchases_shares == 10
    assert by_currency["EUR"].total_purchases_value == 50
    assert any("nieodczytaną" in warning for warning in response.warnings)
    assert any("bez rozpoznanej osoby" in warning for warning in response.warnings)
    assert any("różne waluty" in warning for warning in response.warnings)


def test_person_balances_use_the_same_visibility_filter_as_details():
    rows = [trade(), trade(is_open_market=False, shares=7, value=1400)]
    default = build_insider_response("TEST", transactions=rows)
    all_rows = build_insider_response("TEST", transactions=rows, include_all=True)
    assert len(default.transactions) == 1
    assert default.by_insider[0].total_purchases_shares == 5000
    assert len(all_rows.transactions) == 2
    assert all_rows.by_insider[0].total_purchases_shares == 5007


def test_reported_currency_overrides_the_company_quote_currency():
    response = build_insider_response(
        "TEST", currency="PLN", transactions=[trade(currency="EUR", value=100)]
    )
    assert response.summary.currency == "EUR"
    assert response.currency == "EUR"
    assert response.summary.total_purchases_value == 100
    assert response.chart_markers[0].currency == "EUR"


def test_mixed_currency_markers_use_complete_share_balance_and_no_money_total():
    response = build_insider_response("TEST", currency="PLN", transactions=[
        trade(currency="EUR", shares=100, price=1, value=100),
        trade(transaction_type="sell", currency="PLN", shares=50, price=4, value=200),
    ])
    marker, = response.chart_markers
    assert marker.type == "Bullish"
    assert marker.shares == 50
    assert marker.value is None
    assert marker.currency is None
    assert response.summary.currency is None


def test_unknown_currency_has_no_money_marker_and_incomplete_share_balance_is_neutral():
    unknown = build_insider_response("TEST", currency="PLN", transactions=[trade(currency=None)])
    assert unknown.chart_markers[0].value is None
    assert unknown.chart_markers[0].currency is None
    incomplete = build_insider_response("TEST", transactions=[
        trade(currency="EUR", shares=None),
        trade(transaction_type="sell", currency="PLN", shares=50),
    ])
    assert incomplete.chart_markers[0].type == "Watch"
    assert incomplete.chart_markers[0].shares is None


def test_same_currency_unknown_buy_amount_does_not_create_a_partial_sell_signal():
    response = build_insider_response("TEST", transactions=[
        trade(currency="PLN", shares=None, price=None, value=None),
        trade(transaction_type="sell", currency="PLN", shares=100, price=2, value=200),
    ])
    marker, = response.chart_markers
    assert marker.type == "Watch"
    assert marker.shares is None
    assert marker.value is None

    complete_values = build_insider_response("TEST", transactions=[
        trade(currency="PLN", shares=None, price=None, value=500),
        trade(transaction_type="sell", currency="PLN", shares=100, price=2, value=200),
    ])
    assert complete_values.chart_markers[0].type == "Bullish"
    assert complete_values.chart_markers[0].value == 300


def test_api_returns_espi_details_and_person_balance_with_refresh(monkeypatch):
    cache = TTLCache()
    rows = [trade()]

    async def fetch(**kwargs):
        stocks._espi_client.warnings = ["Nie odczytano drugiego PDF."]
        return rows

    fetch_mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(stocks._espi_client, "get_company_insider_transactions", fetch_mock)
    app.dependency_overrides[get_history_cache] = lambda: cache
    app.dependency_overrides[get_quote_repository] = lambda: None
    try:
        with TestClient(app) as http:
            result = http.get("/api/stocks/cbf/insider-transactions?refresh=true")
        assert result.status_code == 200
        body = result.json()
        assert body["ticker"] == "CBF"
        assert body["transactions"][0]["shares"] == 5000
        assert body["transactions"][0]["price"] == 198
        assert body["transactions"][0]["value"] == 990000
        assert body["transactions"][0]["tradeDate"] == "2026-09-09"
        assert body["chartMarkers"][0]["date"] == "2026-09-16"
        assert body["byInsider"][0]["insiderName"] == "Jan Testowy"
        assert body["byInsider"][0]["totalPurchasesShares"] == 5000
        assert body["byInsider"][0]["netValue"] == 990000
        assert "Nie odczytano drugiego PDF." in body["warnings"]
        assert any("50 ostatnich" in warning for warning in body["warnings"])
        fetch_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_history_cache, None)
        app.dependency_overrides.pop(get_quote_repository, None)


async def test_refresh_bypasses_checked_cache_and_replaces_old_diagnostics(monkeypatch):
    cache = TTLCache()
    rows = [trade()]
    fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(stocks._espi_client, "get_company_insider_transactions", fetch)
    stocks._espi_client.warnings = []
    cache.set("insider-checked:TEST", True, 86400)
    cache.set("insider-warnings:TEST", ["Stary błąd"], 86400)
    kwargs = dict(company=None, market="gpw", currency="PLN", repo=None, stooq=None, cache=cache)

    assert await stocks._load_ticker_insider_transactions("TEST", **kwargs) == []
    fetch.assert_not_awaited()
    assert await stocks._load_ticker_insider_transactions("TEST", refresh=True, **kwargs) == rows
    assert cache.get("insider-warnings:TEST") == []
    fetch.assert_awaited_once()
    assert await stocks._load_ticker_insider_transactions("TEST", **kwargs) == rows
    fetch.assert_awaited_once()


async def test_failed_fetch_uses_short_retry_and_preserves_cached_rows(monkeypatch):
    cache = TTLCache()
    rows = [trade()]
    cache.set("insider-data:TEST", rows, 86400)
    fetch = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr(stocks._espi_client, "get_company_insider_transactions", fetch)
    set_entry = cache.set
    ttl_by_key = {}

    def capture_ttl(key, value, ttl):
        ttl_by_key[key] = ttl
        set_entry(key, value, ttl)

    monkeypatch.setattr(cache, "set", capture_ttl)
    result = await stocks._load_ticker_insider_transactions(
        "TEST", company=None, market="gpw", currency="PLN", repo=None,
        stooq=None, cache=cache, refresh=True,
    )
    assert result == rows
    assert ttl_by_key["insider-checked:TEST"] == stocks._INSIDER_RETRY_TTL_SECONDS
    assert any("Nie udało się odświeżyć" in text for text in cache.get("insider-warnings:TEST"))


async def test_live_rows_survive_a_repository_write_failure(monkeypatch):
    cache = TTLCache()
    rows = [trade()]
    repo = InMemoryQuoteRepository()
    monkeypatch.setattr(repo, "upsert_insider_transactions", AsyncMock(side_effect=RuntimeError()))
    fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(stocks._espi_client, "get_company_insider_transactions", fetch)
    stocks._espi_client.warnings = []
    result = await stocks._load_ticker_insider_transactions(
        "TEST", company=None, market="gpw", currency="PLN", repo=repo,
        stooq=None, cache=cache, refresh=True,
    )
    assert result == rows
    repeated = await stocks._load_ticker_insider_transactions(
        "TEST", company=None, market="gpw", currency="PLN", repo=repo,
        stooq=None, cache=cache,
    )
    assert repeated == rows
    fetch.assert_awaited_once()


async def test_concurrent_tickers_do_not_share_espi_diagnostics(monkeypatch):
    client = EspiClient(max_concurrent=1)
    monkeypatch.setattr(stocks, "_espi_client", client)

    async def listing(url, data):
        await asyncio.sleep(0)
        ticker = data["searchText"]
        return (
            '<li><span class="date">16-09-2026</span>'
            f'<strong class="name">{ticker} S.A.</strong>'
            f'<a href="komunikat?geru_id={1 if ticker == "AAA" else 2}">Raport</a>'
            '<p>Powiadomienie art. 19 MAR</p></li>'
        )

    async def report(url):
        await asyncio.sleep(0)
        link = '<a href="attachment/AAA.pdf">PDF</a>' if "geru_id=1" in url else ""
        return f'<div class="report-data"><p>Nabycie akcji</p>{link}</div>'

    monkeypatch.setattr(client, "_post_form", listing)
    monkeypatch.setattr(client, "_get_url", report)
    monkeypatch.setattr(client, "_get_pdf", AsyncMock(return_value=None))
    monkeypatch.setattr(client, "_get_issuer_pdf", AsyncMock(return_value=None))
    cache = TTLCache()
    kwargs = dict(company=None, market="gpw", currency="PLN", repo=None, stooq=None, cache=cache)
    await asyncio.gather(
        stocks._load_ticker_insider_transactions("AAA", **kwargs),
        stocks._load_ticker_insider_transactions("BBB", **kwargs),
    )
    assert any("AAA.pdf" in text for text in cache.get("insider-warnings:AAA"))
    assert cache.get("insider-warnings:BBB") == []
