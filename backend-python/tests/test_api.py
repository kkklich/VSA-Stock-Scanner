"""Endpoint tests using FastAPI's TestClient with the stooq client mocked."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_stooq_client, history_cache
from app.main import app
from app.models import StooqDailyQuote
from app.services.exceptions import StooqAccessError


class _FakeStooqClient:
    """Stand-in for StooqClient that returns canned data (no network)."""

    def __init__(self, quotes=None, error: Exception | None = None) -> None:
        self._quotes = quotes or []
        self._error = error

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        if self._error is not None:
            raise self._error
        return self._quotes


@pytest.fixture(autouse=True)
def _clear_cache():
    history_cache.clear()
    yield
    history_cache.clear()
    app.dependency_overrides.clear()


def test_get_companies_returns_seed_list() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/stocks")

    assert resp.status_code == 200
    body = resp.json()
    assert any(c["ticker"] == "kgh" and c["name"] == "KGHM Polska Miedź" for c in body)


def test_get_history_returns_quotes_and_company_name() -> None:
    quotes = [
        StooqDailyQuote(
            date=date(2026, 6, 25),
            open=Decimal("140.2"),
            high=Decimal("145.0"),
            low=Decimal("139.8"),
            close=Decimal("144.5"),
            volume=120000,
        )
    ]
    app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(quotes=quotes)

    with TestClient(app) as client:
        resp = client.get("/api/stocks/kgh/history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "KGH"
    assert body["name"] == "KGHM Polska Miedź"
    assert body["quotes"][0]["volume"] == 120000


def test_get_history_rejects_inverted_date_range() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/stocks/kgh/history", params={"from": "2026-06-25", "to": "2026-01-01"})
    assert resp.status_code == 400


def test_get_history_maps_stooq_failure_to_502() -> None:
    app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
        error=StooqAccessError("Odmowa dostępu")
    )

    with TestClient(app) as client:
        resp = client.get("/api/stocks/xyz/history")

    assert resp.status_code == 502
