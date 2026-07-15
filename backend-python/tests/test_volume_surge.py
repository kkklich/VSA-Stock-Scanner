"""Tests for the volume-surge scanner (RVOL math) and endpoint."""

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
from app.services.exceptions import StooqAccessError
from app.services.volume_surge_service import compute_surge_metrics

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float, volume: int) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(round(close * 1.02, 2))),
        low=Decimal(str(round(close * 0.98, 2))),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(
    volumes: list[int],
    closes: list[float] | None = None,
    end: date | None = None,
) -> list[StooqDailyQuote]:
    """One daily bar per volume entry, ending at ``end`` (default today)."""
    if end is None:
        end = date.today()
    if closes is None:
        closes = [100.0] * len(volumes)
    days = len(volumes)
    return [
        _quote(end - timedelta(days=days - 1 - i), closes[i], volumes[i])
        for i in range(days)
    ]


def _surge_series(days: int = 60, base_vol: int = 100_000, spike: int = 300_000):
    """Flat 100k-share volume with the last 3 sessions spiking to 300k."""
    volumes = [base_vol] * (days - 3) + [spike] * 3
    return _series(volumes)


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


class _PerTickerStooqClient:
    """Fake client returning a different series per ticker."""

    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        self._by_ticker = by_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._by_ticker.get(ticker, [])


class _FlakyStooqClient(_FakeStooqClient):
    """Fake client that fails for one specific ticker."""

    def __init__(self, quotes: list[StooqDailyQuote], bad_ticker: str) -> None:
        super().__init__(quotes)
        self._bad_ticker = bad_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        if ticker == self._bad_ticker:
            raise StooqAccessError("stooq unavailable")
        return self._quotes


class _CountingStooqClient(_FakeStooqClient):
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        super().__init__(quotes)
        self.calls = 0

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls += 1
        return self._quotes


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


# ── compute_surge_metrics ─────────────────────────────────────────────────────


class TestComputeSurgeMetrics:
    def test_flat_volume_has_ratio_one(self) -> None:
        m = compute_surge_metrics(_series([100_000] * 30))
        assert m is not None
        assert m.volume_ratio == 1.0
        assert m.last_day_ratio == 1.0
        assert m.days_above_baseline == 0

    def test_three_day_spike_triples_the_ratio(self) -> None:
        m = compute_surge_metrics(_surge_series())
        assert m is not None
        assert m.volume_ratio == 3.0
        assert m.last_day_ratio == 3.0
        assert m.days_above_baseline == 3
        assert m.recent_avg_volume == 300_000
        assert m.baseline_avg_volume == 100_000

    def test_single_spike_day_dilutes_multi_day_ratio(self) -> None:
        # Only the last day spikes: recent avg = (100k+100k+400k)/3 = 200k.
        volumes = [100_000] * 29 + [400_000]
        m = compute_surge_metrics(_series(volumes))
        assert m is not None
        assert m.volume_ratio == 2.0
        assert m.last_day_ratio == 4.0
        assert m.days_above_baseline == 1

    def test_baseline_excludes_recent_window(self) -> None:
        # The spike must not inflate its own baseline: with 20 baseline
        # sessions all at 100k, the ratio is exactly 3.0 regardless of how
        # large the recent volumes are.
        volumes = [100_000] * 23 + [300_000] * 3
        m = compute_surge_metrics(_series(volumes), recent_days=3, baseline_days=20)
        assert m is not None
        assert m.baseline_avg_volume == 100_000
        assert m.volume_ratio == 3.0

    def test_price_change_measured_over_recent_window(self) -> None:
        # Close before the window = 100, last close = 110 → +10 %.
        closes = [100.0] * 27 + [104.0, 108.0, 110.0]
        m = compute_surge_metrics(_series([100_000] * 30, closes=closes))
        assert m is not None
        assert m.price_change_pct == 10.0

    def test_insufficient_history_returns_none(self) -> None:
        assert compute_surge_metrics(_series([100_000] * 10)) is None

    def test_zero_baseline_volume_returns_none(self) -> None:
        # A stock suspended during the whole baseline window can't be scored.
        volumes = [0] * 27 + [50_000] * 3
        assert compute_surge_metrics(_series(volumes)) is None

    def test_custom_windows(self) -> None:
        # recent=2, baseline=10: last two sessions at 500k vs 100k baseline.
        volumes = [100_000] * 10 + [500_000] * 2
        m = compute_surge_metrics(_series(volumes), recent_days=2, baseline_days=10)
        assert m is not None
        assert m.volume_ratio == 5.0


# ── GET /api/stocks/volume-surge ──────────────────────────────────────────────


class TestGetVolumeSurge:
    def test_surging_stock_returned_with_expected_fields(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/volume-surge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asOf"] == date.today().isoformat()
        assert body["recentDays"] == 3
        assert body["baselineDays"] == 20
        assert body["minRatio"] == 1.5
        assert body["scannedCount"] == 1
        assert len(body["items"]) == 1

        item = body["items"][0]
        for field in (
            "ticker", "name", "sector", "lastPrice",
            "recentAvgVolume", "baselineAvgVolume",
            "volumeRatio", "lastDayRatio", "daysAboveBaseline",
            "priceChangePct", "currentRating", "lastSignal",
        ):
            assert field in item, f"missing field: {field}"
        assert item["ticker"] == "TST"
        assert item["volumeRatio"] == 3.0
        assert 0 <= item["currentRating"] <= 100

    def test_normal_volume_stock_excluded_but_counted(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_series([200_000] * 60)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert body["items"] == []
        assert body["scannedCount"] == 1

    def test_items_sorted_by_ratio_descending(self) -> None:
        strong = [100_000] * 57 + [500_000] * 3   # ratio 5.0
        mild = [100_000] * 57 + [200_000] * 3     # ratio 2.0
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company("aaa", "A SA"), _company("bbb", "B SA")])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"aaa": _series(mild), "bbb": _series(strong)}
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA"]
        ratios = [i["volumeRatio"] for i in body["items"]]
        assert ratios == sorted(ratios, reverse=True)

    def test_min_ratio_parameter_filters(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()  # ratio 3.0
        )
        with TestClient(app) as client:
            below = client.get("/api/stocks/volume-surge", params={"minRatio": 4.0})
            above = client.get("/api/stocks/volume-surge", params={"minRatio": 2.0})
        assert below.json()["items"] == []
        assert len(above.json()["items"]) == 1

    def test_window_parameters_change_the_result(self) -> None:
        # Volume has been elevated for 10 sessions; with recentDays=1 vs a
        # baseline that still catches the pre-surge sessions the ratio drops.
        volumes = [100_000] * 50 + [300_000] * 10
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_series(volumes)
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/volume-surge",
                params={"recentDays": 10, "baselineDays": 30},
            )
        body = resp.json()
        assert body["recentDays"] == 10
        assert body["baselineDays"] == 30
        assert len(body["items"]) == 1
        assert body["items"][0]["volumeRatio"] == 3.0
        assert body["items"][0]["daysAboveBaseline"] == 10

    def test_invalid_parameters_rejected(self) -> None:
        with TestClient(app) as client:
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"recentDays": 0}
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"baselineDays": 5}
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"minRatio": 0.5}
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"settings": "{not json"}
                ).status_code
                == 400
            )

    def test_illiquid_stock_excluded(self) -> None:
        # 100 shares/day at 100 PLN = 10,000 PLN median turnover < 100k floor.
        volumes = [100] * 57 + [300] * 3
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_series(volumes)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert body["items"] == []
        assert body["scannedCount"] == 0

    def test_market_cap_below_floor_excluded(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [
                    _company("big", market_cap=500_000_000),
                    _company("sml", market_cap=50_000_000),
                ]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert [i["ticker"] for i in body["items"]] == ["BIG"]

    def test_sorting_and_pagination(self) -> None:
        # Three surging stocks with distinct ratios (5.0 / 3.0 / 2.0) and
        # distinct price moves so both sort orders are observable.
        def series(spike: int, last_close: float) -> list[StooqDailyQuote]:
            volumes = [100_000] * 57 + [spike] * 3
            closes = [100.0] * 59 + [last_close]
            return _series(volumes, closes=closes)

        by_ticker = {
            "aaa": series(300_000, 104.0),  # ratio 3.0, +4 %
            "bbb": series(500_000, 98.0),   # ratio 5.0, -2 %
            "ccc": series(200_000, 110.0),  # ratio 2.0, +10 %
        }
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [_company(t, f"{t.upper()} SA") for t in by_ticker]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            by_ticker
        )
        with TestClient(app) as client:
            # Default: volumeRatio descending, one page with all rows.
            body = client.get("/api/stocks/volume-surge").json()
            assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA", "CCC"]
            assert body["totalCount"] == 3

            # Sort by price move ascending.
            body = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "priceChangePct", "sortDir": "asc"},
            ).json()
            assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA", "CCC"]

            # Sort by ticker ascending.
            body = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "ticker", "sortDir": "asc"},
            ).json()
            assert [i["ticker"] for i in body["items"]] == ["AAA", "BBB", "CCC"]

            # Pagination: 2 rows per page → page 1 has 2, page 2 has 1;
            # totalCount always reports all matching rows.
            page1 = client.get(
                "/api/stocks/volume-surge", params={"pageSize": 2, "page": 1}
            ).json()
            page2 = client.get(
                "/api/stocks/volume-surge", params={"pageSize": 2, "page": 2}
            ).json()
            assert [i["ticker"] for i in page1["items"]] == ["BBB", "AAA"]
            assert [i["ticker"] for i in page2["items"]] == ["CCC"]
            assert page1["totalCount"] == 3
            assert page2["totalCount"] == 3

    def test_invalid_sort_by_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/volume-surge", params={"sortBy": "nonsense"}
            )
        assert resp.status_code == 400

    def test_one_failing_ticker_does_not_break_the_scan(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company("bad", "Bad SA"), _company("good", "Good SA")])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FlakyStooqClient(
            quotes=_surge_series(), bad_ticker="bad"
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/volume-surge")
        assert resp.status_code == 200
        body = resp.json()
        assert [i["ticker"] for i in body["items"]] == ["GOOD"]
        assert body["scannedCount"] == 1  # the failed ticker was never scored

    def test_second_request_served_from_response_cache(self) -> None:
        stooq = _CountingStooqClient(quotes=_surge_series())
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        with TestClient(app) as client:
            client.get("/api/stocks/volume-surge")
            first_calls = stooq.calls
            # Clearing the per-ticker history cache proves the second hit is
            # served by the response-level cache, not the shared history cache.
            history_cache.clear()
            client.get("/api/stocks/volume-surge")
        assert first_calls > 0
        assert stooq.calls == first_calls

    def test_different_settings_recompute_and_cache_separately(self) -> None:
        stooq = _CountingStooqClient(quotes=_surge_series())
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        custom = '{"sos": {"volMult": 3.0}}'
        with TestClient(app) as client:
            client.get("/api/stocks/volume-surge")
            # Cold history for the custom-settings request so the recompute
            # is observable through the fetch counter.
            history_cache.clear()
            client.get("/api/stocks/volume-surge", params={"settings": custom})
            calls_after_custom = stooq.calls
            client.get("/api/stocks/volume-surge", params={"settings": custom})
        assert calls_after_custom > 1  # custom settings did recompute
        assert stooq.calls == calls_after_custom  # …and were cached separately

    def test_different_parameters_cached_separately(self) -> None:
        stooq = _CountingStooqClient(quotes=_surge_series())
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        with TestClient(app) as client:
            a = client.get("/api/stocks/volume-surge").json()
            b = client.get(
                "/api/stocks/volume-surge", params={"minRatio": 2.5}
            ).json()
        assert a["minRatio"] == 1.5
        assert b["minRatio"] == 2.5

    def test_rating_matches_ranking_for_same_data(self) -> None:
        # The surge list shows the same VSA rating the ranking page shows.
        closes = [100 + (i % 7) * 2.5 - (i % 3) for i in range(60)]
        volumes = [200_000 + i * 1_000 for i in range(57)] + [900_000] * 3
        quotes = _series(volumes, closes=closes)
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=quotes
        )
        with TestClient(app) as client:
            surge = client.get("/api/stocks/volume-surge").json()
            ranking = client.get("/api/stocks/ranking").json()
        assert len(surge["items"]) == 1
        assert len(ranking) == 1
        assert surge["items"][0]["currentRating"] == ranking[0]["currentRating"]
