"""Tests for the sector-heatmap service (change math) and endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_gpw_company_service,
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import GpwCompany, StooqDailyQuote
from app.services.heatmap_service import _pct_change, compute_changes

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(round(close * 1.02, 2))),
        low=Decimal(str(round(close * 0.98, 2))),
        close=Decimal(str(close)),
        volume=volume,
    )


def _daily_series(
    days: int,
    close: float = 100.0,
    volume: int = 200_000,
    end: date | None = None,
) -> list[StooqDailyQuote]:
    """``days`` consecutive daily bars ending at ``end`` (today), flat at ``close``."""
    if end is None:
        end = date.today()
    return [
        _quote(end - timedelta(days=days - 1 - i), close, volume) for i in range(days)
    ]


def _company(
    ticker: str = "tst",
    name: str = "Test SA",
    sector: str | None = "Banks",
    market_cap: int | None = 500_000_000,
) -> GpwCompany:
    return GpwCompany(ticker=ticker, name=name, sector=sector, market_cap=market_cap)


class _FakeStooqClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._quotes


class _CountingStooqClient(_FakeStooqClient):
    """Fake client that counts live-fetch calls, to assert cache behaviour."""

    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        super().__init__(quotes)
        self.calls = 0

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls += 1
        return self._quotes


class _PerTickerStooqClient:
    """Fake client returning a different canned series per ticker."""

    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        self._by_ticker = by_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._by_ticker.get(ticker, [])


class _FakeCompanyService:
    def __init__(self, companies: list[GpwCompany]) -> None:
        self._companies = companies

    def get_companies(self) -> list[GpwCompany]:
        return self._companies


@pytest.fixture(autouse=True)
def _clear_caches_and_overrides():
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()


# ── compute_changes ───────────────────────────────────────────────────────────


class TestComputeChanges:
    def test_all_horizons_with_long_history(self) -> None:
        # 400 flat days at 100, then the final close jumps to 110.
        quotes = _daily_series(400)
        quotes[-1] = _quote(quotes[-1].date, 110.0)

        d1, m1, y1, mx = compute_changes(quotes)
        assert d1 == 10.0
        assert m1 == 10.0
        assert y1 == 10.0
        assert mx == 10.0

    def test_short_history_has_no_year_change(self) -> None:
        quotes = _daily_series(40)
        d1, m1, y1, mx = compute_changes(quotes)
        assert d1 == 0.0
        assert m1 == 0.0
        assert y1 is None  # no bar from a year ago
        assert mx == 0.0

    def test_too_few_bars_returns_all_none(self) -> None:
        quotes = _daily_series(1)
        assert compute_changes(quotes) == (None, None, None, None)

    def test_gappy_history_does_not_mislabel_1m_change(self) -> None:
        # Bars 400..300 days ago, a long gap, then 30 recent bars. The nearest
        # "1M" baseline candidate is ~300 days old — far beyond the 2x-horizon
        # tolerance — so the 1M change must be None, not a bogus number.
        end = date.today()
        old = [_quote(end - timedelta(days=d), 100.0) for d in range(400, 299, -1)]
        recent = [_quote(end - timedelta(days=d), 100.0) for d in range(29, 0, -1)]
        quotes = old + recent + [_quote(end, 110.0)]

        d1, m1, y1, mx = compute_changes(quotes)
        assert d1 == 10.0
        assert m1 is None  # nearest baseline ~300 days old → outside tolerance
        assert y1 == 10.0  # a bar exists exactly 365 days back → within tolerance
        assert mx == 10.0


class TestPctChange:
    def test_zero_baseline_returns_none(self) -> None:
        assert _pct_change(100.0, 0.0) is None

    def test_negative_baseline_returns_none(self) -> None:
        assert _pct_change(100.0, -5.0) is None

    def test_regular_change(self) -> None:
        assert _pct_change(110.0, 100.0) == 10.0


# ── GET /api/stocks/heatmap ───────────────────────────────────────────────────


class TestGetHeatmap:
    def test_returns_tiles_with_expected_fields(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(40)
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/heatmap")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asOf"] == date.today().isoformat()
        assert len(body["items"]) > 0

        item = body["items"][0]
        for field in (
            "ticker", "name", "sector", "marketCap", "lastPrice",
            "currentRating", "lastSignal",
            "change1D", "change1M", "change1Y", "changeMax",
        ):
            assert field in item, f"missing field: {field}"
        assert 0 <= item["currentRating"] <= 100

    def test_tiles_sorted_by_market_cap_desc(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(40)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()

        caps = [i["marketCap"] for i in body["items"] if i["marketCap"] is not None]
        assert caps == sorted(caps, reverse=True)
        # Unknown caps (if any) must come after all known caps.
        known_seen_after_none = False
        seen_none = False
        for i in body["items"]:
            if i["marketCap"] is None:
                seen_none = True
            elif seen_none:
                known_seen_after_none = True
        assert not known_seen_after_none

    def test_invalid_settings_rejected(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(40)
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/heatmap", params={"settings": "{not json"})
        assert resp.status_code == 400

    def test_short_history_serialises_change1y_as_null(self) -> None:
        # 40 days of history: no bar from a year ago → change1Y must be a
        # literal null in the JSON payload, not a missing key.
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(40)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert "change1Y" in item
        assert item["change1Y"] is None
        assert item["change1D"] is not None


# ── Pre-filters (must match the ranking) ──────────────────────────────────────


class TestHeatmapPreFilters:
    def test_market_cap_below_floor_excluded(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [
                    _company("big", market_cap=500_000_000),
                    _company("sml", market_cap=50_000_000),  # below 100M floor
                ]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(40)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()
        assert [i["ticker"] for i in body["items"]] == ["BIG"]

    def test_illiquid_stock_excluded(self) -> None:
        # Median turnover 100 PLN × 500 shares = 50,000 PLN < 100,000 PLN floor.
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(40, volume=500)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()
        assert body["items"] == []

    def test_stale_history_excluded(self) -> None:
        # A stock suspended 6 months ago has plenty of old bars but none in
        # the ranking's 120-day window — it must NOT get a heatmap tile with
        # its stale price presented as current.
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_daily_series(400, end=date.today() - timedelta(days=180))
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()
        assert body["items"] == []

    def test_listing_lagging_the_market_excluded(self) -> None:
        # A recently suspended stock still has plenty of bars inside the
        # 120-day window, but its last session lags the newest one in the
        # scan by 15 days — the recency pre-filter must drop its tile rather
        # than show its frozen price/rating as current.
        fresh = _daily_series(60)
        stale = _daily_series(60, end=date.today() - timedelta(days=15))
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [_company("frs", "Fresh SA"), _company("stl", "Stale SA")]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"frs": fresh, "stl": stale}
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()
        assert [i["ticker"] for i in body["items"]] == ["FRS"]
        assert body["asOf"] == date.today().isoformat()


# ── Caching behaviour ─────────────────────────────────────────────────────────


class TestHeatmapCaching:
    def test_second_request_served_from_cache(self) -> None:
        stooq = _CountingStooqClient(quotes=_daily_series(40))
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        with TestClient(app) as client:
            client.get("/api/stocks/heatmap")
            first_calls = stooq.calls
            client.get("/api/stocks/heatmap")
        assert first_calls > 0
        assert stooq.calls == first_calls  # no re-fetch on a warm cache

    def test_refresh_style_clear_forces_recompute(self) -> None:
        stooq = _CountingStooqClient(quotes=_daily_series(40))
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        with TestClient(app) as client:
            client.get("/api/stocks/heatmap")
            calls_before = stooq.calls
            # The daily ingest clears both caches after persisting fresh data.
            history_cache.clear()
            ranking_cache.clear()
            client.get("/api/stocks/heatmap")
        assert stooq.calls > calls_before

    def test_different_settings_recompute_and_cache_separately(self) -> None:
        stooq = _CountingStooqClient(quotes=_daily_series(40))
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        custom = '{"sos": {"volMult": 3.0}}'
        with TestClient(app) as client:
            client.get("/api/stocks/heatmap")
            # Cold history for the custom-settings request so the recompute
            # is observable through the fetch counter.
            history_cache.clear()
            client.get("/api/stocks/heatmap", params={"settings": custom})
            calls_after_custom = stooq.calls
            client.get("/api/stocks/heatmap", params={"settings": custom})
        assert calls_after_custom > 1  # custom settings did recompute
        assert stooq.calls == calls_after_custom  # …and were cached separately


# ── Parity with the ranking ───────────────────────────────────────────────────


class TestHeatmapRankingParity:
    def test_rating_matches_ranking_for_same_data(self) -> None:
        # The contract's core promise: for identical input data both pages
        # show the same VSA rating for the same stock.
        closes = [100 + (i % 7) * 2.5 - (i % 3) for i in range(60)]
        end = date.today()
        quotes = [
            _quote(end - timedelta(days=len(closes) - 1 - i), c, 200_000 + i * 1_000)
            for i, c in enumerate(closes)
        ]
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=quotes
        )
        with TestClient(app) as client:
            heatmap = client.get("/api/stocks/heatmap").json()
            ranking = client.get("/api/stocks/ranking").json()

        assert len(heatmap["items"]) == 1
        assert len(ranking) == 1
        assert (
            heatmap["items"][0]["currentRating"] == ranking[0]["currentRating"]
        )
