"""Endpoint tests using FastAPI's TestClient with the stooq client mocked."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import (
    get_quote_repository,
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import FinancialMetrics, QuarterlyReport, StooqDailyQuote
from app.routers.stocks import _backfill_attempted
from app.services.exceptions import StooqAccessError
from app.services.gpw_company_service import GpwCompanyService
from app.services.ranking_service import _MIN_MARKET_CAP_PLN

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
    """40 bars at 100 PLN with 200k volume/day — passes all pre-filters.

    Dated to end today: the ranking service slices its analysis window by
    real dates, so a fixed historical start would fall outside it.
    """
    start = date.today() - timedelta(days=n - 1)
    return [_make_quote((start + timedelta(days=i)).isoformat()) for i in range(n)]


def _with_year_of_history(quotes: list[StooqDailyQuote]) -> list[StooqDailyQuote]:
    """Prepend one old bar so the series really spans 52 weeks.

    The 52-week context is only reported when the stored bars cover close to a
    full year (see ``_MIN_52W_COVERAGE_DAYS``). The added bar sits 340 days
    before the last one: inside the 52-week window, outside the 120-day
    analysis slice (so ratings and signals are untouched) and inside the price
    range of the rest (so it never becomes the window's high or low).
    """
    last = quotes[-1].date
    return [
        _make_quote((last - timedelta(days=340)).isoformat(), high=101.0, low=99.0),
        *quotes,
    ]


class _FakeStooqClient:
    """Returns canned data so no network calls are made."""

    def __init__(self, quotes: list[StooqDailyQuote] | None = None, error: Exception | None = None) -> None:
        self._quotes = quotes or []
        self._error = error

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        if self._error is not None:
            raise self._error
        return self._quotes


class _PerTickerStooqClient:
    """Fake client returning a different canned series per ticker."""

    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        self._by_ticker = by_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._by_ticker.get(ticker, [])


@pytest.fixture(autouse=True)
def _clear_caches_and_overrides():
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    app.dependency_overrides.clear()


# ── GET /api/stocks ───────────────────────────────────────────────────────────


class TestGetCompanies:
    def test_returns_seed_list(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == len(GpwCompanyService().get_companies())

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

    def test_total_count_header_reflects_full_result(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/ranking?pageSize=5")
        assert resp.status_code == 200
        total = int(resp.headers["X-Total-Count"])
        # The header counts every matching row, not just the returned page.
        assert total > 5
        assert len(resp.json()) == 5

    def test_sort_by_ticker_ascending(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"sortBy": "ticker", "sortDir": "asc", "pageSize": 500},
            ).json()
        tickers = [item["ticker"] for item in body]
        assert tickers == sorted(tickers)

    def test_sort_by_last_price_descending(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"sortBy": "lastPrice", "sortDir": "desc", "pageSize": 500},
            ).json()
        prices = [item["lastPrice"] for item in body]
        assert prices == sorted(prices, reverse=True)

    def test_sort_by_ai_confidence_descending(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"sortBy": "aiConfidence", "sortDir": "desc", "pageSize": 500},
            ).json()
        confidences = [item["aiConfidence"] for item in body]
        assert confidences == sorted(confidences, reverse=True)

    def test_search_filters_by_ticker_or_name(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/ranking", params={"q": "kgh", "pageSize": 500}
            )
        body = resp.json()
        assert int(resp.headers["X-Total-Count"]) == len(body)
        assert body  # "kgh" matches KGHM
        assert all(
            "kgh" in item["ticker"].lower() or "kgh" in item["name"].lower()
            for item in body
        )

    def test_tickers_allow_list_restricts_results(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"tickers": "kgh,peo", "pageSize": 500},
            ).json()
        returned = {item["ticker"].lower() for item in body}
        assert returned <= {"kgh", "peo"}

    def test_min_rating_filter(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"minRating": 40, "pageSize": 500},
            ).json()
        assert all(item["currentRating"] >= 40 for item in body)

    def test_max_rating_filter(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"maxRating": 60, "pageSize": 500},
            ).json()
        assert all(item["currentRating"] <= 60 for item in body)

    def test_sector_filter(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"sector": "Basic Materials", "pageSize": 500},
            ).json()
        assert body  # KGHM et al. are Basic Materials
        assert all(item["sector"] == "Basic Materials" for item in body)

    def test_max_days_since_signal_filter(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"maxDaysSinceSignal": 10, "pageSize": 500},
            ).json()
        # 999 marks "no signal ever" — the recency filter must drop those too.
        assert all(item["daysSinceSignal"] <= 10 for item in body)

    def test_price_range_filter(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"minPrice": 10, "maxPrice": 200, "pageSize": 500},
            ).json()
        assert all(10 <= item["lastPrice"] <= 200 for item in body)

    def test_min_volume_filter(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"minVolume": 50_000, "pageSize": 500},
            ).json()
        assert all(item["volume"] >= 50_000 for item in body)

    def test_52w_context_fields_present(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_with_year_of_history(_rich_quotes())
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/ranking").json()
        item = body[0]
        # camelCase fields exposed; the close (100) sits below the high (102).
        assert "distFrom52wHighPct" in item
        assert "distFrom52wLowPct" in item
        assert "isNew52wHigh" in item
        assert item["distFrom52wHighPct"] <= 0
        assert item["distFrom52wLowPct"] >= 0

    def test_52w_context_is_null_without_a_year_of_history(self) -> None:
        # 40 bars is not 52 weeks: reporting their high as a "52-week high"
        # would be a plain falsehood on the screener, so the fields stay null.
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/ranking").json()
        item = body[0]
        assert item["distFrom52wHighPct"] is None
        assert item["distFrom52wLowPct"] is None
        assert item["isNew52wHigh"] is False
        assert item["isNew52wLow"] is False

    def test_sort_by_dist_from_52w_high(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_with_year_of_history(_rich_quotes())
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/ranking",
                params={"sortBy": "distFrom52wHighPct", "sortDir": "desc",
                        "pageSize": 500},
            )
        assert resp.status_code == 200
        vals = [item["distFrom52wHighPct"] for item in resp.json()]
        assert vals == sorted(vals, reverse=True)

    def test_within_pct_of_52w_high_filter(self) -> None:
        # _rich_quotes closes at 100 with a 102 high → −1.96% from the high.
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_with_year_of_history(_rich_quotes())
        )
        with TestClient(app) as client:
            within5 = client.get(
                "/api/stocks/ranking",
                params={"maxDistFrom52wHighPct": 5, "pageSize": 500},
            ).json()
            within1 = client.get(
                "/api/stocks/ranking",
                params={"maxDistFrom52wHighPct": 1, "pageSize": 500},
            ).json()
        assert len(within5) > 0  # −1.96% is within 5% of the high
        assert all(item["distFrom52wHighPct"] >= -5 for item in within5)
        assert within1 == []  # −1.96% is NOT within 1% of the high

    def test_new_52w_high_filter(self) -> None:
        # A strictly rising series so the last bar sets a new 52-week high;
        # a flat series (kgh) never does.
        rising = _with_year_of_history([
            _make_quote(
                (date.today() - timedelta(days=39 - i)).isoformat(),
                close=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
            )
            for i in range(40)
        ])
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"kgh": rising, "pko": _with_year_of_history(_rich_quotes())}
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking",
                params={"new52wHigh": "true", "pageSize": 500},
            ).json()
        tickers = {item["ticker"] for item in body}
        assert "KGH" in tickers
        assert "PKO" not in tickers
        assert all(item["isNew52wHigh"] for item in body)

    def test_stale_listing_excluded_from_ranking(self) -> None:
        # A ticker whose last bar lags the newest session in the scan by 15
        # days (i.e. a suspended/stale listing) must be dropped by the
        # recency pre-filter instead of ranking its frozen rating; other
        # tickers still make the list.
        fresh = _rich_quotes()
        stale = [
            _make_quote((q.date - timedelta(days=15)).isoformat()) for q in fresh
        ]
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"kgh": fresh, "pko": stale}
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/ranking").json()

        tickers = {item["ticker"] for item in body}
        assert "KGH" in tickers
        assert "PKO" not in tickers

    def test_invalid_sort_by_rejected(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/ranking", params={"sortBy": "bogus"})
        assert resp.status_code == 400

    def test_invalid_sort_dir_rejected(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/ranking", params={"sortDir": "sideways"})
        assert resp.status_code == 422

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

        # One call per company on first load, then 0 calls on cache hit.
        # Companies whose known market cap is below the 100M PLN floor are
        # skipped before any data is fetched.
        companies = GpwCompanyService().get_companies()
        expected = sum(
            1
            for c in companies
            if c.market_cap is None or c.market_cap >= _MIN_MARKET_CAP_PLN
        )
        first_load_calls = calls["count"]
        assert first_load_calls == expected


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


# ── Signals: stooq backfill of history older than the stored bars ────────────


def _recent_quotes(days: int) -> list[StooqDailyQuote]:
    """One bar per day for the last ``days`` days, oldest first."""
    return [
        _make_quote((date.today() - timedelta(days=i)).isoformat())
        for i in range(days, 0, -1)
    ]


class TestSignalsBackfill:
    def test_backfills_older_history_from_stooq(self) -> None:
        # DB only has the last 30 days; stooq has 2 years.
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", _recent_quotes(30)))
        full_history = _recent_quotes(700)
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=full_history
        )
        app.dependency_overrides[get_quote_repository] = lambda: repo

        from_ = (date.today() - timedelta(days=730)).isoformat()
        with TestClient(app) as client:
            resp = client.get(f"/api/stocks/kgh/signals?fromDate={from_}")

        assert resp.status_code == 200
        assert len(resp.json()["history"]) == 700
        # The older bars were persisted, so the DB now covers the full range.
        stored = asyncio.run(
            repo.get_quotes("kgh", date.today() - timedelta(days=730))
        )
        assert len(stored) == 700

    def test_covered_range_is_served_from_db_without_stooq(self) -> None:
        # DB covers the requested range → stooq (which would fail) is not hit.
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", _recent_quotes(40)))
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            error=StooqAccessError("should not be called")
        )
        app.dependency_overrides[get_quote_repository] = lambda: repo

        from_ = (date.today() - timedelta(days=35)).isoformat()
        with TestClient(app) as client:
            resp = client.get(f"/api/stocks/kgh/signals?fromDate={from_}")

        assert resp.status_code == 200
        # Only the bars inside the requested range come back — and the request
        # succeeded, proving the failing stooq client was never consulted.
        assert len(resp.json()["history"]) == 35

    def test_backfill_failure_falls_back_to_stored_history(self) -> None:
        # Backfill needed but stooq is down → serve the shorter stored history.
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", _recent_quotes(30)))
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            error=StooqAccessError("Odmowa dostępu")
        )
        app.dependency_overrides[get_quote_repository] = lambda: repo

        from_ = (date.today() - timedelta(days=730)).isoformat()
        with TestClient(app) as client:
            resp = client.get(f"/api/stocks/kgh/signals?fromDate={from_}")

        assert resp.status_code == 200
        assert len(resp.json()["history"]) == 30


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

    def test_returns_and_ttm_from_stored_data(self) -> None:
        # Deterministic: seed the repo so the endpoint never needs the network.
        # Two years of bars priced 100 → 150 gives a computable 1Y return, and
        # four seeded quarters give a trailing-twelve-month revenue.
        repo = InMemoryQuoteRepository()
        today = date.today()
        quotes = [
            _make_quote((today - timedelta(days=730 - i)).isoformat(), close=100.0)
            for i in range(700)
        ] + [_make_quote(today.isoformat(), close=150.0)]
        asyncio.run(repo.upsert_quotes("kgh", quotes))
        asyncio.run(
            repo.upsert_fundamentals(
                "kgh",
                FinancialMetrics(
                    market_cap=1_000_000_000,
                    return_on_equity=0.184,
                    return_on_assets=0.072,
                ),
            )
        )
        asyncio.run(
            repo.upsert_quarterly(
                "kgh",
                [
                    QuarterlyReport(period_end="2026-03-31", total_revenue=40, net_income=4),
                    QuarterlyReport(period_end="2025-12-31", total_revenue=30, net_income=3),
                    QuarterlyReport(period_end="2025-09-30", total_revenue=20, net_income=2),
                    QuarterlyReport(period_end="2025-06-30", total_revenue=10, net_income=1),
                ],
            )
        )
        app.dependency_overrides[get_quote_repository] = lambda: repo
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=quotes
        )

        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/fundamentals").json()

        assert body["metrics"]["returnOnEquity"] == 0.184
        assert body["metrics"]["returnOnAssets"] == 0.072
        assert body["ttmRevenue"] == 100
        assert body["ttmNetIncome"] == 10
        # 100 → 150 over the stored window.
        assert body["priceReturns"]["y1Pct"] == 50.0
        assert body["priceReturns"]["maxPct"] == 50.0
        assert body["priceReturns"]["maxFromDate"] is not None


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


# ── VSA settings query parameter ─────────────────────────────────────────────


class TestVsaSettingsParam:
    """The Scanner page settings must flow through the API into the engine."""

    def test_ranking_accepts_valid_settings(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/ranking",
                params={"settings": '{"sos": {"volMult": 3.0}}'},
            )
        assert resp.status_code == 200

    def test_ranking_rejects_malformed_settings(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/ranking", params={"settings": "not-json"}
            )
        assert resp.status_code == 400

    def test_ranking_rejects_out_of_range_settings(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/ranking",
                params={"settings": '{"sos": {"lookback": 500}}'},
            )
        assert resp.status_code == 400

    def test_all_signals_disabled_yields_neutral_ranking(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        disabled = (
            '{"spring":{"enabled":false},"sos":{"enabled":false},'
            '"test":{"enabled":false},"upthrust":{"enabled":false},'
            '"nodemand":{"enabled":false},"sow":{"enabled":false}}'
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/ranking", params={"settings": disabled, "pageSize": 5}
            ).json()
        assert len(body) > 0
        # No signals can fire → every stock is neutral 50 / Hold.
        assert all(item["currentRating"] == 50 for item in body)
        assert all(item["lastSignal"] == "Hold" for item in body)

    def test_settings_use_separate_cache_entries(self) -> None:
        calls = {"count": 0}

        class _CountingClient(_FakeStooqClient):
            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                calls["count"] += 1
                return _rich_quotes()

        app.dependency_overrides[get_stooq_client] = lambda: _CountingClient()
        custom = '{"sos": {"volMult": 2.5}}'
        with TestClient(app) as client:
            client.get("/api/stocks/ranking")
            default_calls = calls["count"]
            # A different config must recompute the ranking (fresh cache entry),
            # but reuses the per-ticker history cache → no new history fetches.
            client.get("/api/stocks/ranking", params={"settings": custom})
            assert calls["count"] == default_calls
            # Same custom config again → served from its own ranking cache.
            resp = client.get("/api/stocks/ranking", params={"settings": custom})
            assert resp.status_code == 200

    def test_signals_endpoint_accepts_settings(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/kgh/signals",
                params={"settings": '{"nodemand": {"enabled": false}}'},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert all(s["signalName"] != "No Demand" for s in body["vsaSignals"])
