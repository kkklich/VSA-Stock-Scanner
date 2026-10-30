"""Insider screener contracts: amount integrity, stored coverage and pagination."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import get_quote_repository
from app.main import app
from app.markets import PLN_PER_UNIT
from app.models.stocks import InsiderTransactionItem, StockRankingItem
from app.routers import stocks
from app.services.insider_screen_service import screen_insider_activity, summarize_insider_activity


def trade(side="buy", **overrides):
    return InsiderTransactionItem(**{
        "publication_date": date.today(), "transaction_type": side,
        "shares": 100, "price": 10, "currency": "PLN", "source": "espi",
        "is_open_market": True, **overrides,
    })


def row(ticker):
    return StockRankingItem(
        ticker=ticker, name=ticker, last_price=10, price_change_pct=0,
        current_rating=50, rating_change=0, last_signal="Hold", days_since_signal=999,
        sparkline=[], volume=100000,
    )


def test_values_convert_each_filing_and_derive_missing_amount():
    summary = summarize_insider_activity([
        trade(value=200, currency="USD"),
        trade(shares=20, price=50, currency="GBP"),
        trade("sell", value=100, currency="EUR"),
        trade("grant", value=90000, is_open_market=False),
        trade(value=90000, is_open_market=False),
    ])
    assert summary.purchases_count == 2
    assert summary.sales_count == 1
    assert summary.purchases_shares == 120
    assert summary.purchases_value_pln == 200 * PLN_PER_UNIT["USD"] + 1000 * PLN_PER_UNIT["GBP"]
    assert summary.sales_value_pln == pytest.approx(100 * PLN_PER_UNIT["EUR"])
    assert summary.net_value_pln == summary.purchases_value_pln - summary.sales_value_pln


@pytest.mark.parametrize("overrides", [
    {"price": None}, {"currency": None}, {"currency": "XYZ"},
    {"value": float("nan")}, {"value": -1},
])
def test_incomplete_values_never_pass_thresholds_or_net_screens(overrides):
    rows = [row("aaa")]
    transactions = {"aaa": [trade(), trade(**overrides)]}
    summary = summarize_insider_activity(transactions["aaa"])
    assert summary.purchases_value_pln is None
    assert summary.net_value_pln is None
    assert len(screen_insider_activity(rows, transactions, "buy", None)) == 1
    assert screen_insider_activity(rows, transactions, "buy", 0) == []
    assert screen_insider_activity(rows, transactions, "netBuy", None) == []


@pytest.mark.parametrize(("activity", "minimum", "expected"), [
    ("any", None, ["buy", "sell", "flat"]),
    ("buy", 1000, ["buy", "flat"]),
    ("sell", 1000, ["sell", "flat"]),
    ("netBuy", 500, ["buy"]),
    ("netSell", 500, ["sell"]),
    ("netBuy", 1001, []),
    ("all", 1500, ["flat"]),
])
def test_directions_and_inclusive_thresholds(activity, minimum, expected):
    rows = [row(t) for t in ("buy", "sell", "flat", "none")]
    transactions = {
        "buy": [trade()], "sell": [trade("sell")],
        "flat": [trade(), trade("sell")],
    }
    result = screen_insider_activity(rows, transactions, activity, minimum)
    assert [r.ticker for r in result] == expected
    assert all(r.insider_activity is None for r in rows)


async def test_bulk_repository_filters_publication_dates_sides_and_tickers():
    repo = InMemoryQuoteRepository()
    today = date(2026, 10, 30)
    start = today - timedelta(days=29)
    await repo.upsert_insider_transactions("aaa", [
        trade(publication_date=start, trade_date=start - timedelta(days=20)),
        trade("sell", publication_date=today),
        trade(publication_date=start - timedelta(days=1)),
        trade(publication_date=today + timedelta(days=1)),
        trade("grant", publication_date=today),
        trade(publication_date=today, is_open_market=False),
    ])
    await repo.upsert_insider_transactions("other", [trade(publication_date=today)])
    result = await repo.get_insider_transactions_bulk([" AAA ", "none"], start, today)
    assert len(result["aaa"]) == 2
    assert result["none"] == []
    assert "other" not in result


@pytest.fixture
def client(monkeypatch):
    # Bypass the unrelated ranking computation, keeping the actual query,
    # validation, repository, response serialization and pagination paths.
    monkeypatch.setattr(stocks, "_market_ranking", AsyncMock(return_value=[
        row("aaa"), row("bbb"), row("ccc"),
    ]))
    repo = InMemoryQuoteRepository()
    app.dependency_overrides[get_quote_repository] = lambda: repo
    with TestClient(app) as http:
        yield http, repo
    app.dependency_overrides.pop(get_quote_repository, None)


async def test_api_filters_before_pagination_and_returns_amounts(client):
    http, repo = client
    await repo.upsert_insider_transactions("bbb", [trade()])
    await repo.upsert_insider_transactions("ccc", [trade()])
    repo.get_insider_transactions_bulk = AsyncMock(wraps=repo.get_insider_transactions_bulk)
    response = http.get("/api/stocks/ranking", params={
        "insiderActivity": "buy", "insiderDays": 30, "minInsiderValue": 1000,
        "pageSize": 1, "page": 2, "sortBy": "ticker", "sortDir": "asc",
    })
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    [item] = response.json()
    assert item["ticker"] == "ccc"
    assert item["insiderActivity"]["purchasesValuePln"] == 1000
    assert item["insiderActivity"]["netValuePln"] == 1000
    repo.get_insider_transactions_bulk.assert_awaited_once()


def test_no_filter_does_not_read_insiders(client):
    http, repo = client
    repo.get_insider_transactions_bulk = AsyncMock(side_effect=AssertionError("unexpected read"))
    response = http.get("/api/stocks/ranking")
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "3"
    repo.get_insider_transactions_bulk.assert_not_awaited()


def test_unavailable_storage_is_an_error_not_empty_results(client):
    http, repo = client
    repo.get_insider_transactions_bulk = AsyncMock(side_effect=RuntimeError("offline"))
    assert http.get("/api/stocks/ranking?insiderActivity=buy").status_code == 503
    app.dependency_overrides[get_quote_repository] = lambda: None
    assert http.get("/api/stocks/ranking?insiderActivity=buy").status_code == 503


@pytest.mark.parametrize("query", [
    "insiderActivity=invalid", "insiderDays=0", "insiderDays=366",
    "minInsiderValue=-1", "minInsiderValue=nan", "minInsiderValue=inf",
])
def test_invalid_query_is_rejected(client, query):
    http, _ = client
    assert http.get(f"/api/stocks/ranking?{query}").status_code == 422
