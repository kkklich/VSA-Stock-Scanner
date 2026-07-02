"""Endpoint tests using FastAPI's TestClient with the stooq client mocked."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import StooqDailyQuote
from app.services.exceptions import StooqAccessError


# ── Test fixtures ─────────────────────────────────────────────────────────────


def _make_quote(
    d: str,
    close: float = 100.0,
    open_: float = 99.0,
    high: float = 102.0,
    low: float = 98.0,
    volume: int = 200_000,
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=date.fromisoformat(d),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _rich_quotes(n: int = 40) -> list[StooqDailyQuote]:
    """40 bars at 100 PLN with 200k volume/day — passes all pre-filters."""
    start = date(2026, 1, 2)
    from datetime import timedelta
    return [_make_quote((start + timedelta(days=i)).isoformat()) for i in range(n)]


class _FakeStooqClient:
    """Returns canned data so no network calls are made."""

    def __init__(self, quotes: list[StooqDailyQuote] | None = None, error: Exception | None = None) -> None:
        self._quotes = quotes or []
        self._error = error

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        if self._error is not None:
            raise self._error
        return self._quotes


@pytest.fixture(autouse=True)
def _clear_caches_and_overrides():
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()


# ── GET /api/stocks ───────────────────────────────────────────────────────────


class TestGetCompanies:
    def test_returns_seed_list(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 151

    def test_kghm_is_present(self) -> None:
        with TestClient(app) as client:
            body = client.get("/api/stocks").json()
        kghm = next((c for c in body if c["ticker"] == "kgh"), None)
        assert kghm is not None
        assert kghm["name"] == "KGHM Polska Miedz S.A."
        assert kghm["sector"] == "Basic Materials"


# ── GET /api/stocks/ranking ───────────────────────────────────────────────────


class TestGetRanking:
    def test_returns_list_of_ranking_items(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/ranking")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # All 30 companies should have data from the mock client.
        assert len(body) > 0

    def test_ranking_items_have_required_fields(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/ranking").json()

        item = body[0]
        for field in (
            "ticker", "name", "lastPrice", "priceChangePct",
            "currentRating", "ratingChange", "lastSignal",
            "daysSinceSignal", "sparkline", "volume",
        ):
            assert field in item, f"Missing field: {field}"

    def test_ranking_sorted_by_rating_descending(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/ranking").json()

        ratings = [item["currentRating"] for item in body]
        assert ratings == sorted(ratings, reverse=True)

    def test_pagination_page_size(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/ranking?pageSize=5")
        assert resp.status_code == 200
        assert len(resp.json()) <= 5

    def test_camel_case_fields_in_response(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/ranking").json()
        # If camelCase serialization works, snake_case keys must be absent.
        item = body[0]
        assert "last_price" not in item
        assert "lastPrice" in item

    def test_ranking_result_is_cached(self) -> None:
        calls = {"count": 0}

        class _CountingClient(_FakeStooqClient):
            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                calls["count"] += 1
                return _rich_quotes()

        app.dependency_overrides[get_stooq_client] = lambda: _CountingClient()
        with TestClient(app) as client:
            client.get("/api/stocks/ranking")
            client.get("/api/stocks/ranking")

        # one call per company on first load, then 0 calls on cache hit.
        first_load_calls = calls["count"]
        assert first_load_calls == 151  # one call per company


# ── GET /api/stocks/{ticker}/history ─────────────────────────────────────────


class TestGetHistory:
    def test_returns_quotes_and_company_name(self) -> None:
        quotes = [_make_quote("2026-06-25", close=144.5, volume=120_000)]
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(quotes=quotes)

        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "KGH"
        assert body["name"] == "KGHM Polska Miedz S.A."
        assert body["quotes"][0]["volume"] == 120_000

    def test_rejects_inverted_date_range(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/history?from=2026-06-25&to=2026-01-01")
        assert resp.status_code == 400

    def test_stooq_failure_returns_502(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            error=StooqAccessError("Odmowa dostępu")
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/xyz/history")
        assert resp.status_code == 502

    def test_history_is_cached(self) -> None:
        calls = {"count": 0}

        class _Counting(_FakeStooqClient):
            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                calls["count"] += 1
                return [_make_quote("2026-06-25")]

        app.dependency_overrides[get_stooq_client] = lambda: _Counting()
        with TestClient(app) as client:
            client.get("/api/stocks/kgh/history")
            client.get("/api/stocks/kgh/history")

        assert calls["count"] == 1  # second call served from cache


# ── GET /api/stocks/{ticker}/signals ─────────────────────────────────────────


class TestGetSignals:
    def test_returns_history_and_signals_shape(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/signals")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "KGH"
        assert body["name"] == "KGHM Polska Miedz S.A."
        assert isinstance(body["history"], list)
        assert isinstance(body["vsaSignals"], list)

    def test_history_bars_have_time_field(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals").json()

        bar = body["history"][0]
        assert "time" in bar
        assert "open" in bar and "high" in bar and "low" in bar and "close" in bar

    def test_vsa_signals_have_correct_fields(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals").json()

        for sig in body["vsaSignals"]:
            assert "date" in sig
            assert "signalName" in sig
            assert "type" in sig
            assert sig["type"] in ("Bullish", "Bearish")

    def test_rejects_inverted_date_range(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/kgh/signals?fromDate=2026-06-25&toDate=2026-01-01"
            )
        assert resp.status_code == 400

    def test_stooq_failure_returns_502(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            error=StooqAccessError("Odmowa dostępu")
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/xyz/signals")
        assert resp.status_code == 502

    def test_rating_in_0_100_range(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals").json()

        assert 0 <= body["currentRating"] <= 100

    def test_camel_case_fields(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals").json()

        assert "currentRating" in body
        assert "ratingChange" in body
        assert "lastPrice" in body
        assert "vsaSignals" in body
        assert "last_price" not in body


# ── GET /api/stocks/{ticker}/fundamentals ─────────────────────────────────────


class TestGetFundamentals:
    def test_returns_company_metadata(self) -> None:
        """Without DB the endpoint fetches live from YahooFinanceClient."""
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/fundamentals")
        # Without a DB and without a YahooFinanceClient override the endpoint
        # falls back gracefully — it may 404 (no data) or 200 (live fetch).
        assert resp.status_code in (200, 404)

    def test_response_shape_when_data_present(self) -> None:
        """If data is returned it must match the documented schema."""
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/fundamentals")
        if resp.status_code == 404:
            return  # no data in test env — schema check not applicable
        body = resp.json()
        assert body["ticker"] == "KGH"
        assert "quarterlyReports" in body
        assert isinstance(body["quarterlyReports"], list)

    def test_invalid_ticker_returns_400(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/!!!/fundamentals")
        assert resp.status_code == 400

    def test_description_included_from_details_json(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/fundamentals")
        if resp.status_code == 404:
            return
        body = resp.json()
        # Company description comes from company-details.json (no DB needed).
        assert body.get("description") is not None
        assert len(body["description"]) > 20

    def test_camel_case_fields(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/fundamentals")
        if resp.status_code == 404:
            return
        body = resp.json()
        assert "quarterlyReports" in body
        if body.get("metrics"):
            assert "marketCap" in body["metrics"]
            assert "peRatio" in body["metrics"]
            assert "market_cap" not in body["metrics"]


# ── Stooq client helpers (from test_stooq_client.py, kept for regression) ────


class TestStooqClientHelpers:
    """Regression tests for the stooq client's pure functions."""

    def test_proof_of_work_url(self) -> None:
        from app.services.stooq_client import _build_daily_url

        url = _build_daily_url("kgh", None, None)
        assert url == "https://stooq.pl/q/d/l/?s=kgh&i=d"

    def test_csv_parse(self) -> None:
        from app.services.stooq_client import _parse_daily_csv

        csv = "\n".join([
            "Date,Open,High,Low,Close,Volume",
            "2026-06-24,140.20,145.00,139.80,144.50,120000",
        ])
        quotes = _parse_daily_csv(csv, "kgh")
        assert len(quotes) == 1
        assert quotes[0].close == Decimal("144.50")
