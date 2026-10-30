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

from app.db.models import DailyQuoteRow, PortfolioRow, UserRow
from app.db.portfolio_repository import PortfolioRepository
from app.dependencies import get_user_repository
from app.routers.auth import get_current_user
from app.routers.portfolios import router
from app.services.portfolio import valuation
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
        transaction("pkn", "PLN", "1", "100"),
        transaction("aapl.us", "USD", "2", "200"),
        transaction("hsba.l", "GBp", "3", "400"),
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
    assert totals["PLN"]["marketValue"] is None
    assert totals["PLN"]["unrealizedPnl"] is None
    assert totals["PLN"]["missingQuotes"] == 1
    assert totals["USD"]["marketValue"] == 420
    assert totals["GBp"]["marketValue"] is None
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
