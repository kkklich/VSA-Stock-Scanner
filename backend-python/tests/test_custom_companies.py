"""New listings require login, survive restarts and enter every scanner list."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.custom_company_repository import CustomCompanyRepository
from app.db.models import CompanyRow, CustomCompanyRow, DailyQuoteRow, UserRow
from app.db.user_repository import UserRepository
from app.dependencies import get_user_repository
from app.models import StooqDailyQuote
from app.routers import custom_companies as api
from app.routers.auth import get_current_user
from app.services.gpw_company_service import GpwCompanyService
from tests.test_watchlists import SQLSession

URL = "/api/custom-stocks"
PAYLOAD = {"ticker": "NEWSTOCK", "name": "New Company", "country": "Poland", "market": "gpw"}


class StockSession(SQLSession):
    async def merge(self, row):
        return self.session.merge(row)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    for table in (UserRow.__table__, CompanyRow.__table__, CustomCompanyRow.__table__):
        table.create(engine)
    # SQLite autoincrement requires exactly INTEGER, unlike PostgreSQL BIGINT.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE daily_quotes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ticker TEXT, date DATE, open NUMERIC, high NUMERIC, low NUMERIC, "
            "close NUMERIC, volume BIGINT)"
        )
    with Session(engine) as session:
        session.add(UserRow(id=1, email="one@example.com", password_hash="test",
                            display_name="One", created_at=datetime.now(UTC)))
        session.commit()
    service = GpwCompanyService()
    service.custom_repository = CustomCompanyRepository(lambda: StockSession(engine))
    monkeypatch.setattr(api, "gpw_company_service", service)
    quote = StooqDailyQuote(date=date(2026, 11, 20), open=10, high=11, low=9, close=10, volume=100)
    prices = AsyncMock(return_value=[quote])
    monkeypatch.setattr(api, "yahoo_client", SimpleNamespace(get_daily_history=prices))
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_user_repository] = lambda: UserRepository(
        lambda: StockSession(engine)
    )
    with TestClient(app) as connection:
        connection.service = service
        connection.engine = engine
        connection.prices = prices
        yield connection
    engine.dispose()


async def test_add_persists_prices_and_reloads_into_scanners(client):
    shared = client.service.enabled_companies()
    result = client.post(URL, json=PAYLOAD)
    assert result.status_code == 201, result.text
    assert result.json()["ticker"] == "newstock"
    assert client.service.find("NEWSTOCK").name == "New Company"
    assert any(c.ticker == "newstock" for c in shared)
    assert any(c.ticker == "newstock" for c in client.service.get_companies())
    restored = GpwCompanyService()
    for company in await client.service.custom_repository.list():
        restored.add_company(company)
    assert restored.find("newstock").country == "Poland"
    with Session(client.engine) as session:
        assert session.scalar(select(DailyQuoteRow.close)) == 10
    assert client.post(URL, json=PAYLOAD).status_code == 409
    assert client.prices.await_count == 1


def test_login_and_expected_account_required(client):
    assert client.post(URL, json=PAYLOAD, headers={"X-Expected-User-Id": "2"}).status_code == 409
    client.app.dependency_overrides.pop(get_current_user)
    assert client.post(URL, json=PAYLOAD).status_code == 401
    client.prices.assert_not_awaited()


@pytest.mark.parametrize("changes", [
    {"name": "  "}, {"country": ""}, {"ticker": "../bad"}, {"market": "unknown"},
    {"market": "us"}, {"ticker": "x" * 21},
])
def test_invalid_input_does_not_download_or_save(client, changes):
    assert client.post(URL, json={**PAYLOAD, **changes}).status_code == 422
    assert client.service.find("newstock") is None
    client.prices.assert_not_awaited()


async def test_provider_failure_does_not_save(client):
    client.prices.return_value = []
    assert client.post(URL, json=PAYLOAD).json()["detail"]["code"] == "no_price_history"
    client.prices.side_effect = RuntimeError("provider unavailable")
    assert client.post(URL, json=PAYLOAD).status_code == 502
    assert await client.service.custom_repository.list() == []
    assert client.service.find("newstock") is None


def test_foreign_ticker_and_market(client, monkeypatch):
    monkeypatch.setattr(settings, "markets", "all")
    wrong_market = client.post(URL, json={**PAYLOAD, "ticker": "ZZNEW.DE", "market": "us"})
    assert wrong_market.status_code == 422
    client.prices.assert_not_awaited()
    response = client.post(URL, json={**PAYLOAD, "ticker": "ZZNEW", "market": "us"})
    assert response.status_code == 201, response.text
    assert response.json()["ticker"] == "zznew.us"
    assert response.json()["currency"] == "USD"


def test_storage_outage_cannot_report_success(client):
    client.service.custom_repository = None
    assert client.post(URL, json=PAYLOAD).status_code == 503
    client.prices.assert_not_awaited()
