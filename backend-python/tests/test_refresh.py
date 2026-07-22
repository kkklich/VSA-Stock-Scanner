"""Tests for the refresh pipeline: RefreshService, rating snapshots and the
/refresh + /rating-history endpoints."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import (
    get_quote_repository,
    get_refresh_service,
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import GpwCompany, RatingPoint, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.refresh_service import RefreshService, build_rating_points

# ── Shared helpers ────────────────────────────────────────────────────────────


def _company(ticker: str = "kgh") -> GpwCompany:
    return GpwCompany(ticker=ticker, name=ticker.upper(), sector="Test")


def _quote(d: date, close: float = 100.0, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close - 1)),
        high=Decimal(str(close + 2)),
        low=Decimal(str(close - 2)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _rich_quotes(n: int = 40) -> list[StooqDailyQuote]:
    # Ends today: the ranking step slices its analysis window by real dates,
    # so a fixed historical start would fall outside it.
    start = date.today() - timedelta(days=n - 1)
    return [_quote(start + timedelta(days=i)) for i in range(n)]


class _FakeStooq:
    """Canned data source — no network."""

    def __init__(self, quotes: list[StooqDailyQuote] | None = None) -> None:
        self._quotes = quotes if quotes is not None else _rich_quotes()

    async def get_daily_history(self, ticker: str, from_date=None, to_date=None):
        return self._quotes


def _make_service(
    repo: InMemoryQuoteRepository | None,
    quotes: list[StooqDailyQuote] | None = None,
) -> RefreshService:
    return RefreshService(
        companies=[_company("kgh")],
        stooq=_FakeStooq(quotes),
        history_cache=TTLCache(),
        ranking_cache=TTLCache(),
        repo=repo,
    )


# ── build_rating_points ───────────────────────────────────────────────────────


class TestBuildRatingPoints:
    def test_one_point_per_bar(self) -> None:
        quotes = _rich_quotes(40)
        points = build_rating_points(quotes)
        assert len(points) == 40
        assert [p.date for p in points] == [q.date for q in quotes]

    def test_ratings_are_in_range_and_close_is_kept(self) -> None:
        points = build_rating_points(_rich_quotes(40))
        assert all(0 <= p.rating <= 100 for p in points)
        assert all(p.verdict for p in points)
        assert points[-1].close == 100.0

    def test_too_few_bars_returns_empty(self) -> None:
        assert build_rating_points(_rich_quotes(10)) == []

    def test_illiquid_stock_returns_empty(self) -> None:
        start = date(2026, 1, 2)
        quotes = [
            _quote(start + timedelta(days=i), volume=100)  # ~10k PLN turnover
            for i in range(40)
        ]
        assert build_rating_points(quotes) == []


# ── InMemoryQuoteRepository: rating snapshots ────────────────────────────────


class TestRatingSnapshotsRepo:
    def test_upsert_and_get_sorted(self) -> None:
        repo = InMemoryQuoteRepository()
        pts = [
            RatingPoint(date=date(2026, 7, 2), rating=60, verdict="Buy", close=10.0),
            RatingPoint(date=date(2026, 7, 1), rating=50, verdict="Hold", close=9.5),
        ]
        asyncio.run(repo.upsert_rating_snapshots("kgh", pts))
        result = asyncio.run(repo.get_rating_history("kgh", date(2026, 1, 1)))
        assert [p.date for p in result] == [date(2026, 7, 1), date(2026, 7, 2)]

    def test_upsert_overwrites_same_date(self) -> None:
        repo = InMemoryQuoteRepository()
        d = date(2026, 7, 1)
        asyncio.run(repo.upsert_rating_snapshots(
            "kgh", [RatingPoint(date=d, rating=50, verdict="Hold")]
        ))
        asyncio.run(repo.upsert_rating_snapshots(
            "kgh", [RatingPoint(date=d, rating=70, verdict="Buy")]
        ))
        result = asyncio.run(repo.get_rating_history("kgh", date(2026, 1, 1)))
        assert len(result) == 1
        assert result[0].rating == 70

    def test_date_window_filters(self) -> None:
        repo = InMemoryQuoteRepository()
        pts = [
            RatingPoint(date=date(2026, 7, i), rating=50, verdict="Hold")
            for i in (1, 2, 3)
        ]
        asyncio.run(repo.upsert_rating_snapshots("kgh", pts))
        result = asyncio.run(
            repo.get_rating_history("kgh", date(2026, 7, 2), date(2026, 7, 2))
        )
        assert [p.date for p in result] == [date(2026, 7, 2)]


# ── RefreshService ────────────────────────────────────────────────────────────


class TestRefreshService:
    def test_run_stores_rating_snapshots(self) -> None:
        repo = InMemoryQuoteRepository()
        svc = _make_service(repo)
        asyncio.run(svc.run())

        history = asyncio.run(repo.get_rating_history("kgh", date(2020, 1, 1)))
        assert len(history) == 40  # one snapshot per bar (backfill)
        assert history[0].date < history[-1].date
        assert svc.last_refresh_at is not None
        assert svc.last_error is None
        assert svc.stocks_ranked == 1

    def test_run_without_db_completes(self) -> None:
        svc = _make_service(repo=None)
        asyncio.run(svc.run())
        assert svc.last_refresh_at is not None
        assert svc.last_error is None
        status = svc.status()
        assert status.state == "idle"
        assert status.db_enabled is False

    def test_status_reports_db_enabled(self) -> None:
        svc = _make_service(InMemoryQuoteRepository())
        assert svc.status().db_enabled is True
        assert svc.status().state == "idle"


# ── Endpoints ─────────────────────────────────────────────────────────────────


class TestRefreshEndpoints:
    def _override(self) -> RefreshService:
        svc = _make_service(InMemoryQuoteRepository())
        app.dependency_overrides[get_refresh_service] = lambda: svc
        return svc

    def _cleanup(self) -> None:
        app.dependency_overrides.clear()
        history_cache.clear()
        ranking_cache.clear()

    def test_post_refresh_returns_202_and_status(self) -> None:
        self._override()
        try:
            with TestClient(app) as client:
                resp = client.post("/api/stocks/refresh")
                assert resp.status_code == 202
                body = resp.json()
                assert body["state"] in ("idle", "running")
                assert body["dbEnabled"] is True

                status_resp = client.get("/api/stocks/refresh/status")
                assert status_resp.status_code == 200
        finally:
            self._cleanup()

    def test_get_status_shape(self) -> None:
        self._override()
        try:
            with TestClient(app) as client:
                body = client.get("/api/stocks/refresh/status").json()
            for field in (
                "state", "lastStartedAt", "lastRefreshAt",
                "lastError", "stocksRanked", "dbEnabled",
            ):
                assert field in body, f"Missing field: {field}"
        finally:
            self._cleanup()


class TestRatingHistoryEndpoint:
    def _cleanup(self) -> None:
        app.dependency_overrides.clear()
        history_cache.clear()
        ranking_cache.clear()

    def test_serves_stored_snapshots(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_rating_snapshots("kgh", [
            RatingPoint(date=date.today() - timedelta(days=1), rating=55,
                        verdict="Hold", close=100.0),
            RatingPoint(date=date.today(), rating=62, verdict="Buy", close=101.0),
        ]))
        app.dependency_overrides[get_quote_repository] = lambda: repo
        try:
            with TestClient(app) as client:
                resp = client.get("/api/stocks/kgh/rating-history")
            assert resp.status_code == 200
            body = resp.json()
            assert body["ticker"] == "KGH"
            assert body["source"] == "db"
            assert [p["rating"] for p in body["points"]] == [55, 62]
        finally:
            self._cleanup()

    def test_falls_back_to_computed_history(self) -> None:
        # No repo, so history must be derived from the (fake) live quotes.
        recent = [
            _quote(date.today() - timedelta(days=i))
            for i in range(40, 0, -1)
        ]
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooq(recent)
        try:
            with TestClient(app) as client:
                resp = client.get("/api/stocks/kgh/rating-history")
            assert resp.status_code == 200
            body = resp.json()
            assert body["source"] == "computed"
            assert len(body["points"]) == 40
        finally:
            self._cleanup()

    def test_invalid_ticker_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/__bad__/rating-history")
        assert resp.status_code == 400
