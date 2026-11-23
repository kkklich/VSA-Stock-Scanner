"""Portfolio accounting, private SQL persistence, retry safety and dated sales."""

from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import DailyQuoteRow, PortfolioRow, UserRow
from app.db.portfolio_repository import PortfolioRepository
from app.dependencies import get_user_repository, gpw_company_service
from app.routers.auth import get_current_user
from app.routers.portfolios import router
from app.services.portfolio import XTB_RECONCILIATION, holdings, valuation
from tests.test_watchlists import SQLSession


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    for table in (UserRow, PortfolioRow, DailyQuoteRow):
        table.__table__.create(engine)
    with Session(engine) as session:
        for user_id in (1, 2):
            session.add(
                UserRow(
                    id=user_id,
                    email=f"portfolio{user_id}@example.com",
                    password_hash="test",
                    display_name="Test",
                    created_at=datetime.now(UTC),
                )
            )
        for index, (day, price) in enumerate(((date(2026, 1, 5), 90), (date(2026, 1, 6), 130))):
            session.add(
                DailyQuoteRow(
                    id=index + 1,
                    ticker="kgh",
                    date=day,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=100,
                )
            )
        session.commit()
    app = FastAPI()
    app.include_router(router)
    owner = SimpleNamespace(id=1)
    repo = SimpleNamespace(portfolios=PortfolioRepository(lambda: SQLSession(engine)))
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_user_repository] = lambda: repo
    with TestClient(app) as connection:
        connection.owner, connection.app_instance = owner, app
        yield connection
    engine.dispose()


def create(client):
    response = client.post(
        "/api/portfolios",
        json={
            "id": str(uuid4()),
            "name": "  Emerytura  ",
            "broker": "XTB",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def trade(client, portfolio, **changes):
    payload = {
        "id": str(uuid4()),
        "version": portfolio["version"],
        "ticker": "KGH.WA",
        "date": "2026-01-02",
        "side": "buy",
        "quantity": "10",
        "price": "100",
        "fees": "10",
        "currency": "PLN",
        **changes,
    }
    return client.post(f"/api/portfolios/{portfolio['id']}/transactions", json=payload)


def test_portfolio_only_instrument_preserves_xetra_ticker_and_currency(client, monkeypatch):
    monkeypatch.setattr(settings, "markets", "gpw")
    assert all(company.ticker != "nvd.de" for company in gpw_company_service.get_companies("de"))

    listed = client.get("/api/portfolios/instruments").json()
    nvidia = next(instrument for instrument in listed if instrument["ticker"] == "nvd.de")
    assert nvidia == {
        "ticker": "nvd.de",
        "name": "NVIDIA Corporation",
        "market": "de",
        "currency": "EUR",
    }

    portfolio = create(client)
    assert trade(client, portfolio, ticker="NVD.DE", currency="USD").status_code == 422
    saved = trade(client, portfolio, ticker="NVD.DE", currency="EUR", quantity="0.5")
    assert saved.status_code == 201, saved.text
    (transaction,) = saved.json()["transactions"]
    assert (transaction["ticker"], transaction["currency"], transaction["quantity"]) == (
        "nvd.de",
        "EUR",
        "0.5",
    )


def test_lifecycle_cost_basis_fees_sales_and_latest_quotes(client):
    portfolio = create(client)
    assert portfolio["name"] == "Emerytura"
    assert portfolio["costMethod"] == "fifo"
    purchase = trade(client, portfolio)
    assert purchase.status_code == 201
    sale = trade(
        client, purchase.json(), side="sell", quantity="4", price="120", fees="2", date="2026-01-05"
    )
    assert sale.status_code == 201
    result = client.get("/api/portfolios")
    assert result.headers["cache-control"] == "private, no-store"
    saved = result.json()["items"][0]
    position = saved["positions"][0]
    assert position["quantity"] == 6
    assert position["cost"] == 606
    assert position["averagePrice"] == 101
    assert position["currentPrice"] == 130
    assert position["quoteDate"] == "2026-01-06"
    assert position["marketValue"] == 780
    assert position["realizedPnl"] == 74
    assert position["unrealizedPnl"] == 174
    assert position["unrealizedPnlPct"] == pytest.approx(174 / 606 * 100)
    assert saved["totals"][0]["marketValue"] == 780
    path = f"/api/portfolios/{saved['id']}"
    renamed = client.patch(
        path,
        json={"version": saved["version"], "name": "Nowy", "broker": "Bossa", "costMethod": "fifo"},
    )
    assert renamed.status_code == 200
    assert client.delete(path + f"?version={saved['version']}").status_code == 409
    assert client.delete(path + f"?version={renamed.json()['version']}").status_code == 200
    assert client.get("/api/portfolios").json()["items"] == []


def test_owner_isolation_and_signed_out_access(client):
    portfolio = create(client)
    client.owner.id = 2
    assert client.get("/api/portfolios").json()["items"] == []
    path = f"/api/portfolios/{portfolio['id']}"
    assert trade(client, portfolio).status_code == 404
    assert (
        client.patch(
            path, json={"version": 1, "name": "Stolen", "broker": "Other", "costMethod": "fifo"}
        ).status_code
        == 404
    )
    assert client.delete(path + "?version=1").status_code == 404
    assert client.delete(path + f"/transactions/{uuid4()}?version=1").status_code == 404
    client.app_instance.dependency_overrides.pop(get_current_user)
    assert client.get("/api/portfolios").status_code == 401
    assert client.get("/api/portfolios/instruments").status_code == 401
    assert trade(client, portfolio).status_code == 401


def test_retries_are_idempotent_and_stale_writes_rejected(client):
    portfolio = create(client)
    original = {"id": portfolio["id"], "name": portfolio["name"], "broker": portfolio["broker"]}
    assert client.post("/api/portfolios", json=original).json()["id"] == portfolio["id"]
    trade_id = str(uuid4())
    first = trade(client, portfolio, id=trade_id)
    repeated = trade(client, portfolio, id=trade_id)
    assert first.json() == repeated.json()
    assert trade(client, portfolio, id=trade_id, price="101").status_code == 409
    assert trade(client, portfolio).status_code == 409
    assert len(client.get("/api/portfolios").json()["items"][0]["transactions"]) == 1


def test_backdated_sales_and_purchase_deletion_cannot_create_short_positions(client):
    portfolio = create(client)
    assert trade(client, portfolio, side="sell").status_code == 409
    bought = trade(client, portfolio).json()
    assert trade(client, bought, side="sell", date="2026-01-01").status_code == 409
    assert trade(client, bought, side="sell", quantity="11").status_code == 409
    sold = trade(client, bought, side="sell", quantity="10", date="2026-01-05").json()
    path = f"/api/portfolios/{portfolio['id']}/transactions"
    assert (
        client.delete(
            path + f"/{bought['transactions'][0]['id']}?version={sold['version']}"
        ).status_code
        == 409
    )
    # Removing the sale first leaves a valid ledger; removing the buy then succeeds.
    removed = client.delete(path + f"/{sold['transactions'][1]['id']}?version={sold['version']}")
    assert removed.status_code == 200
    assert (
        client.delete(
            path + f"/{bought['transactions'][0]['id']}?version={removed.json()['version']}"
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "0"},
        {"price": "-1"},
        {"fees": "-1"},
        {"price": "NaN"},
        {"quantity": "Infinity"},
        {"price": "0.000000001"},
        {"date": "2999-01-01"},
        {"currency": "USD"},
        {"ticker": "missing"},
        {"user_id": 2},
    ],
)
def test_invalid_transactions_are_not_saved(client, changes):
    portfolio = create(client)
    assert trade(client, portfolio, **changes).status_code == 422
    assert client.get("/api/portfolios").json()["items"][0]["transactions"] == []


def test_decimal_accounting_mixed_currencies_and_missing_prices():
    def transaction(ticker, currency, quantity, price, side="buy", fees="0"):
        return {
            "ticker": ticker,
            "currency": currency,
            "quantity": quantity,
            "price": price,
            "side": side,
            "fees": fees,
            "date": "2026-01-01",
        }

    ledger = [
        transaction("kgh", "PLN", "0.1", "0.2"),
        transaction("pkn", "PLN", "2", "100"),
        transaction("pkn", "PLN", "1", "110", side="sell"),
        transaction("aapl.us", "USD", "2", "200"),
        transaction("hsba.l", "GBp", "3", "400"),
        transaction("bp.l", "GBp", "1", "400"),
        transaction("bp.l", "GBp", "1", "400", side="sell"),
    ]
    result = valuation(
        ledger,
        {
            "kgh": {"price": Decimal("0.3"), "date": "2026-01-02", "currency": "PLN"},
            "aapl.us": {"price": Decimal(210), "date": "2026-01-02", "currency": "USD"},
            "hsba.l": {"price": Decimal(4), "date": "2026-01-02", "currency": "GBP"},
        },
    )
    assert result["positions"][0]["cost"] == Decimal("0.02")
    assert result["positions"][0]["unrealizedPnl"] == Decimal("0.01")
    totals = {t["currency"]: t for t in result["totals"]}
    assert totals["PLN"] == {
        "currency": "PLN",
        "marketValue": Decimal("0.03"),
        "cost": Decimal("0.02"),
        "unrealizedPnl": Decimal("0.01"),
        "unrealizedPnlPct": Decimal(50),
        "realizedPnl": Decimal(10),
        "missingQuotes": 1,
    }
    assert totals["USD"]["marketValue"] == 420
    assert totals["GBp"]["marketValue"] is None
    assert totals["GBp"]["cost"] == 0
    assert totals["GBp"]["unrealizedPnl"] is None
    assert totals["GBp"]["missingQuotes"] == 1
    # Closing a fractional position zeroes cost exactly, even with repeating average cost.
    closed = valuation(
        [
            transaction("kgh", "PLN", "3", "1", fees="1"),
            transaction("kgh", "PLN", "1", "2", side="sell"),
            transaction("kgh", "PLN", "2", "2", side="sell"),
        ],
        {},
    )
    assert closed["positions"][0]["quantity"] == 0
    assert closed["positions"][0]["cost"] == 0
    assert closed["totals"][0]["marketValue"] == 0
    assert closed["totals"][0]["realizedPnl"] == 2


def test_fifo_and_moving_average_match_published_reference_example():
    # Portfolio Performance's cost-methodology example: same total gain, different allocation.
    # https://help.portfolio-performance.info/en/concepts/cost-methodology/
    trades = [
        {
            "ticker": "kgh",
            "currency": "PLN",
            "quantity": str(quantity),
            "price": str(price),
            "side": side,
            "fees": "0",
            "date": day,
        }
        for quantity, price, side, day in (
            (100, 95, "buy", "2026-01-01"),
            (200, 105, "buy", "2026-01-02"),
            (100, 107, "buy", "2026-01-03"),
            (150, 110, "sell", "2026-01-04"),
        )
    ]
    quotes = {"kgh": {"price": Decimal(110), "currency": "PLN", "date": "2026-01-05"}}
    fifo = valuation(trades, quotes, "fifo")["positions"][0]
    average = valuation(trades, quotes, "moving_average")["positions"][0]
    assert (fifo["realizedPnl"], fifo["unrealizedPnl"]) == (1750, 1050)
    assert (average["realizedPnl"], average["unrealizedPnl"]) == (1050, 1750)
    assert fifo["averagePrice"] == Decimal("105.8")
    assert average["averagePrice"] == 103


def test_cost_method_change_recalculates_without_modifying_trades(client):
    portfolio = create(client)
    first = trade(client, portfolio, fees="0").json()
    second = trade(client, first, price="200", fees="0", date="2026-01-03").json()
    sold = trade(
        client, second, quantity="10", price="150", fees="0", side="sell", date="2026-01-05"
    ).json()
    before = client.get("/api/portfolios").json()["items"][0]
    assert before["positions"][0]["realizedPnl"] == 500
    assert before["positions"][0]["cost"] == 2000
    payload = {
        "version": sold["version"],
        "name": sold["name"],
        "broker": sold["broker"],
        "costMethod": "moving_average",
    }
    path = f"/api/portfolios/{sold['id']}"
    assert client.patch(path, json=payload).status_code == 200
    after = client.get("/api/portfolios").json()["items"][0]
    assert after["costMethod"] == "moving_average"
    assert after["positions"][0]["realizedPnl"] == 0
    assert after["positions"][0]["cost"] == 1500
    assert after["transactions"] == before["transactions"]
    assert (
        client.patch(
            path, json={**payload, "version": after["version"], "costMethod": "lifo"}
        ).status_code
        == 422
    )


def test_newer_intraday_quote_is_used_and_completed_close_takes_precedence(client, monkeypatch):
    import app.routers.portfolios as endpoint

    portfolio = create(client)
    trade(client, portfolio)
    latest = SimpleNamespace(
        price=140, session_date=date(2026, 1, 7), as_of=datetime(2026, 1, 7, 12, tzinfo=UTC)
    )
    monkeypatch.setattr(endpoint, "get_live_prices", lambda: SimpleNamespace(get=lambda _: latest))
    live = client.get("/api/portfolios").json()["items"][0]["positions"][0]
    assert live["currentPrice"] == 140
    assert live["quoteSource"] == "intraday"
    assert live["quoteDate"] == "2026-01-07"
    assert live["quoteAsOf"].startswith("2026-01-07T12:00:00")
    latest.session_date = date(2026, 1, 6)
    closed = client.get("/api/portfolios").json()["items"][0]["positions"][0]
    assert closed["currentPrice"] == 130
    assert closed["quoteSource"] == "close"
    assert closed["quoteAsOf"] is None
    assert closed["quoteAgeDays"] >= 0


@pytest.mark.parametrize(("alias", "ticker"), [("pmg", "gns"), ("dada", "dad")])
def test_broker_ticker_uses_active_listing_quotes(client, monkeypatch, alias, ticker):
    repo = client.app_instance.dependency_overrides[get_user_repository]().portfolios

    async def quote_history(tickers, start, end):
        assert ticker in tickers
        return {ticker: [{"date": date(2026, 1, 6), "price": Decimal("130")}]}

    monkeypatch.setattr(repo, "quote_history", quote_history)
    result = trade(client, create(client), ticker=alias)
    assert result.status_code == 201

    position = client.get("/api/portfolios").json()["items"][0]["positions"][0]
    assert position["ticker"] == alias
    assert position["currentPrice"] == 130


def test_stock_holdings_combines_open_wallet_positions_and_broker_aliases(client):
    wallet = create(client)
    purchase = trade(client, wallet, ticker="dada", quantity="4.125")
    assert purchase.status_code == 201, purchase.text
    sale = trade(client, purchase.json(), ticker="dada", side="sell", quantity="1.25")
    assert sale.status_code == 201, sale.text
    purchase = trade(client, sale.json(), ticker="dad", quantity="0.25")
    assert purchase.status_code == 201, purchase.text

    second_wallet = create(client)
    purchase = trade(client, second_wallet, ticker="dad", quantity="2")
    assert purchase.status_code == 201, purchase.text
    closed_wallet = create(client)
    purchase = trade(client, closed_wallet, ticker="dad", quantity="1")
    assert purchase.status_code == 201, purchase.text
    sale = trade(client, purchase.json(), ticker="dad", side="sell", quantity="1")
    assert sale.status_code == 201, sale.text

    result = client.get("/api/portfolios/holdings/DAD.WA", headers={"X-Expected-User-Id": "1"})
    assert result.headers["cache-control"] == "private, no-store"
    body = result.json()
    assert body["quantity"] == 5.125
    wallets = {item["id"]: item for item in body["wallets"]}
    first = wallets[wallet["id"]]
    assert (first["name"], first["quantity"]) == (wallet["name"], 3.125)
    assert wallets[second_wallet["id"]]["quantity"] == 2
    assert [(t["side"], t["remainingQuantity"]) for t in first["trades"]] == [
        ("buy", 0.25),
        ("sell", None),
        ("buy", 2.875),
    ]
    closed = wallets[closed_wallet["id"]]
    assert closed["quantity"] == 0
    assert closed["positions"] == [
        {"currency": "PLN", "quantity": 0, "cost": 0, "realizedPnl": -20}
    ]
    assert [t["realizedPnl"] for t in closed["trades"]] == [-20, -20]
    assert client.get("/api/portfolios/holdings/dada").json() == result.json()
    assert client.get("/api/portfolios/holdings/kgh").json() == {"quantity": 0, "wallets": []}

    client.owner.id = 2
    assert client.get("/api/portfolios/holdings/dad").json() == {"quantity": 0, "wallets": []}
    mismatch = client.get("/api/portfolios/holdings/dad", headers={"X-Expected-User-Id": "1"})
    assert mismatch.status_code == 409


@pytest.mark.parametrize(
    ("method", "remaining", "realized"),
    [
        ("fifo", [2, 4], [Decimal(96), None, Decimal(96)]),
        ("moving_average", [3, 3], [Decimal(48), Decimal(-12), Decimal(36)]),
    ],
)
def test_stock_trade_profit_uses_wallet_cost_method(method, remaining, realized):
    trade = {"ticker": "kgh", "currency": "PLN", "quantity": "4", "side": "buy", "fees": "4"}
    ledger = [
        {**trade, "id": "first", "price": "100", "date": "2026-01-01"},
        {**trade, "id": "second", "price": "160", "date": "2026-01-02"},
        {
            **trade,
            "id": "sale",
            "quantity": "2",
            "side": "sell",
            "price": "151",
            "fees": "4",
            "date": "2026-01-03",
            "executedAt": "2026-01-03T12:00:00",
        },
    ]
    trades = []
    (position,) = holdings(ledger, method, trade_details=trades)
    assert [t["remainingQuantity"] for t in trades[:2]] == remaining
    assert [t["realizedPnl"] for t in trades] == realized
    assert sum(t["costBasis"] for t in trades[:2]) == position["cost"]
    assert trades[-1]["realizedPnl"] == position["realizedPnl"]
    assert trades[-1]["executedAt"] == "2026-01-03T12:00:00+01:00"


def test_stock_trade_profit_uses_snapshot_basis_without_linking_snapshot_to_old_buys():
    trade = {"ticker": "kgh", "currency": "PLN", "quantity": "2", "side": "buy", "fees": "0"}
    ledger = [
        {**trade, "id": "first", "price": "100", "date": "2026-01-01"},
        {
            "kind": XTB_RECONCILIATION,
            "date": "2026-01-02",
            "positions": [
                {
                    "ticker": "kgh",
                    "currency": "PLN",
                    "quantity": "2",
                    "cost": "250",
                    "lots": [{"quantity": "2", "cost": "250"}],
                }
            ],
        },
        {**trade, "id": "sale", "side": "sell", "price": "150", "date": "2026-01-03"},
    ]
    trades = []
    (position,) = holdings(ledger, "fifo", trade_details=trades)
    assert (trades[0]["remainingQuantity"], trades[0]["realizedPnl"]) == (None, None)
    assert trades[1]["realizedPnl"] == position["realizedPnl"] == 50


def test_account_summary_replays_all_wallets_with_dated_prices_and_rates(client, monkeypatch):
    import app.routers.portfolios as endpoint
    import app.services.portfolio_summary as summary_service

    class ValuationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 12, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(endpoint, "datetime", ValuationClock)
    live = SimpleNamespace(
        price=140, session_date=date(2026, 1, 12), as_of=ValuationClock.now(UTC)
    )
    monkeypatch.setattr(endpoint, "get_live_prices", lambda: {"kgh": live})
    repo = client.app_instance.dependency_overrides[get_user_repository]().portfolios
    with repo._session_factory().session as session:
        for index, (day, price) in enumerate(((date(2026, 1, 5), 10), (date(2026, 1, 9), 12)), 3):
            session.add(
                DailyQuoteRow(
                    id=index, ticker="nvd.de", date=day, open=price, high=price,
                    low=price, close=price, volume=100,
                )
            )
        session.commit()

    purchase = trade(client, create(client)).json()
    assert trade(client, purchase, side="sell", quantity="4", date="2026-01-08").status_code == 201
    foreign_purchase = trade(client, create(client), ticker="NVD.DE", currency="EUR", quantity="2")
    assert foreign_purchase.status_code == 201
    empty_wallet = create(client)

    rates = {
        "EUR": [
            (date(2026, 1, 5), Decimal(4)),
            (date(2026, 1, 9), Decimal("4.25")),
            (date(2026, 1, 12), Decimal("4.5")),
        ]
    }

    async def exchange_rates(start, end, currencies):
        assert (start, end, currencies) == (date(2026, 1, 5), date(2026, 1, 12), {"EUR"})
        return rates

    monkeypatch.setattr(summary_service, "get_portfolio_fx", exchange_rates)
    summary = client.get("/api/portfolios").json()["summary"]
    assert summary["currency"] == "PLN"
    assert summary["current"]["value"] == 948
    assert len(summary["history"]) == 8
    assert summary["history"][-2]["value"] == 882
    assert summary["history"][0]["value"] == 980
    assert summary["dayChange"] == {
        "amount": 66,
        "percent": pytest.approx(66 / 882 * 100),
        "since": "2026-01-11",
        "partial": False,
    }
    assert summary["weekChange"] == {
        "amount": -32,
        "percent": pytest.approx(-32 / 980 * 100),
        "since": "2026-01-05",
        "partial": False,
    }
    wallets = {wallet["walletId"]: wallet for wallet in summary["wallets"]}
    domestic = wallets[purchase["id"]]
    foreign_id = foreign_purchase.json()["id"]
    foreign = wallets[foreign_id]
    empty = wallets[empty_wallet["id"]]
    assert domestic["current"]["value"] == 840
    assert domestic["weekChange"]["amount"] == -60
    assert foreign["current"]["value"] == 108
    assert foreign["dayChange"]["amount"] == 6
    assert foreign["weekChange"]["percent"] == 35
    assert foreign["holdings"] == [{
        "ticker": "nvd.de", "currency": "EUR", "currentValue": 108, "staleQuote": False,
        "dayChange": foreign["dayChange"], "weekChange": foreign["weekChange"], "rangeChange": None,
    }]
    assert domestic["holdings"][0]["weekChange"]["amount"] == -60
    assert empty["current"]["value"] == 0
    assert empty["holdings"] == []
    assert empty["weekChange"]["percent"] is None

    one_day = client.get("/api/portfolios?historyRange=1d").json()["summary"]
    assert one_day["history"] == summary["history"][-2:]
    assert one_day["weekChange"] == summary["weekChange"]
    assert one_day["wallets"] == summary["wallets"]

    rates.clear()
    summary = client.get("/api/portfolios").json()["summary"]
    assert summary["current"]["value"] == 840
    assert summary["current"]["missingRates"] == ["EUR"]
    assert summary["dayChange"]["amount"] == 60
    assert summary["dayChange"]["partial"] is True
    foreign = next(wallet for wallet in summary["wallets"] if wallet["walletId"] == foreign_id)
    assert foreign["current"]["value"] is None
    assert foreign["current"]["missingRates"] == ["EUR"]
    assert foreign["dayChange"] is None
    assert foreign["holdings"][0]["currentValue"] is None
    assert foreign["holdings"][0]["dayChange"] is None
    assert summary["currencyTotals"] == [
        {"currency": "EUR", "marketValue": 24, "missingQuotes": 0},
        {"currency": "PLN", "marketValue": 840, "missingQuotes": 0},
    ]


def test_portfolio_history_ranges_start_on_the_requested_date_or_first_trade(client, monkeypatch):
    import app.routers.portfolios as endpoint

    class ValuationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 31, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(endpoint, "datetime", ValuationClock)
    assert trade(client, create(client), date="2026-01-01").status_code == 201
    for period, start in (("1m", "2026-02-28"), ("all", "2026-01-01")):
        result = client.get("/api/portfolios", params={"historyRange": period})
        assert result.status_code == 200
        summary = result.json()["summary"]
        assert summary["history"][0]["date"] == start
        assert summary["history"][-1]["date"] == "2026-03-31"
        if period == "all":
            january = next(point for point in summary["history"] if point["date"] == "2026-01-06")
            assert january["value"] is not None
    assert client.get("/api/portfolios?historyRange=invalid").status_code == 422


def test_wallet_heatmap_uses_independent_calendar_ranges_and_each_wallets_first_trade(
    client, monkeypatch,
):
    import app.routers.portfolios as endpoint

    class ValuationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 31, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(endpoint, "datetime", ValuationClock)
    monkeypatch.setattr(endpoint, "get_live_prices", lambda: None)
    repo = client.app_instance.dependency_overrides[get_user_repository]().portfolios
    prices = {
        "2025-03-01": 70, "2025-03-31": 80, "2025-12-31": 85, "2026-02-28": 120,
        "2026-03-24": 146, "2026-03-30": 150, "2026-03-31": 160,
    }
    with repo._session_factory().session as session:
        for index, (day, price) in enumerate(prices.items(), 3):
            session.add(DailyQuoteRow(
                id=index, ticker="kgh", date=date.fromisoformat(day), open=price,
                high=price, low=price, close=price, volume=100,
            ))
        session.commit()

    older = trade(client, create(client), date="2025-03-01").json()["id"]
    newer = trade(client, create(client), date="2026-01-06", quantity="2").json()["id"]
    opened_today = trade(client, create(client), date="2026-03-31").json()["id"]
    cutoffs = {
        "all": "2025-03-01", "1y": "2025-03-31", "3m": "2025-12-31",
        "1m": "2026-02-28", "1w": "2026-03-24", "1d": "2026-03-30",
    }
    for period, day in cutoffs.items():
        result = client.get("/api/portfolios", params={"historyRange": "1d", "walletRange": period})
        assert result.status_code == 200
        summary = result.json()["summary"]
        assert [point["date"] for point in summary["history"]] == ["2026-03-30", "2026-03-31"]
        wallets = {wallet["walletId"]: wallet for wallet in summary["wallets"]}
        base_price = prices[day]
        assert wallets[older]["rangeChange"] == {
            "amount": (160 - base_price) * 10,
            "percent": pytest.approx((160 - base_price) / base_price * 100),
            "since": day,
            "partial": False,
        }
        assert wallets[older]["holdings"][0]["rangeChange"] == wallets[older]["rangeChange"]
        if period in {"all", "1y", "3m"}:
            assert wallets[newer]["rangeChange"]["since"] == "2026-01-06"
            assert wallets[newer]["rangeChange"]["amount"] == 60
            assert wallets[opened_today]["rangeChange"] is None
    assert client.get("/api/portfolios?walletRange=invalid").status_code == 422


def test_account_summary_names_missing_holdings_and_compares_shared_price_coverage(
    client, monkeypatch
):
    import app.routers.portfolios as endpoint

    class ValuationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 12, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(endpoint, "datetime", ValuationClock)
    live = {
        ticker: SimpleNamespace(
            price=price, session_date=date(2026, 1, 12), as_of=ValuationClock.now(UTC)
        )
        for ticker, price in (("kgh", 140), ("pzu", 40))
    }
    monkeypatch.setattr(endpoint, "get_live_prices", lambda: live)

    first_wallet = create(client)
    assert trade(client, first_wallet).status_code == 201
    repo = client.app_instance.dependency_overrides[get_user_repository]().portfolios
    with repo._session_factory().session as session:
        session.add(DailyQuoteRow(
            id=3, ticker="ale", date=date(2026, 1, 3), open=20, high=20, low=20,
            close=20, volume=100,
        ))
        session.commit()
    other_wallet = create(client)
    missing = trade(client, other_wallet, ticker="PKN", quantity="1")
    assert missing.status_code == 201
    restored = trade(client, missing.json(), ticker="PZU", quantity="2")
    assert restored.status_code == 201
    assert trade(client, restored.json(), ticker="ALE", quantity="1").status_code == 201

    summary = client.get("/api/portfolios").json()["summary"]
    assert summary["current"]["value"] == 1500
    assert summary["current"]["missingQuotes"] == 1
    assert summary["current"]["staleQuotes"] == 1
    assert summary["missingHoldings"] == [{
        "ticker": "pkn", "currency": "PLN", "walletId": other_wallet["id"],
        "walletName": other_wallet["name"],
    }]
    assert summary["currencyTotals"] == [
        {"currency": "PLN", "marketValue": 1500, "missingQuotes": 1}
    ]
    assert summary["history"][-2]["value"] == 1300
    assert summary["history"][-2]["missingQuotes"] == 3
    assert summary["history"][-1]["value"] == 1480
    assert summary["dayChange"]["amount"] == 100
    assert summary["dayChange"]["partial"] is True
    assert summary["weekChange"]["amount"] == 500
    assert summary["weekChange"]["partial"] is True
    wallets = {wallet["walletId"]: wallet for wallet in summary["wallets"]}
    assert wallets[first_wallet["id"]]["dayChange"]["partial"] is False
    other = wallets[other_wallet["id"]]
    assert other["current"]["value"] == 100
    assert other["current"]["missingQuotes"] == 1
    assert other["current"]["staleQuotes"] == 1
    assert other["dayChange"] is None
    holdings_by_ticker = {holding["ticker"]: holding for holding in other["holdings"]}
    assert holdings_by_ticker["pkn"]["currentValue"] is None
    assert holdings_by_ticker["pzu"]["currentValue"] == 80
    assert holdings_by_ticker["pzu"]["dayChange"] is None
    assert holdings_by_ticker["ale"]["staleQuote"] is True
    assert holdings_by_ticker["ale"]["dayChange"] is None


def test_portfolio_migration_upgrade_and_downgrade():
    engine = create_engine("sqlite://")
    UserRow.__table__.create(engine)
    path = Path(__file__).parents[1] / "alembic/versions/013_portfolios.py"
    spec = spec_from_file_location("portfolio_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "portfolios" in inspect(connection).get_table_names()
            migration.downgrade()
            assert "portfolios" not in inspect(connection).get_table_names()
    engine.dispose()
