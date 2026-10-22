"""QVM read API, finished-session filtering and automatic observation capture."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import (
    get_gpw_company_service,
    get_quote_repository,
    get_ranking_cache,
)
from app.main import app
from app.models import FinancialMetrics, GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.long_term_service import build_long_term_ranking, long_term_cache_key
from app.services.market_cache import invalidate_markets
from app.services.refresh_service import RefreshService


class Companies:
    def __init__(self, companies):
        self.companies = companies

    def get_companies(self, market="gpw"):
        return [c for c in self.companies if c.market == market]

    def find(self, ticker):
        return next((c for c in self.companies if c.ticker == ticker), None)


async def seed():
    repo = InMemoryQuoteRepository()
    companies = [GpwCompany(ticker=f"qvm{i}", name=f"Company {i}", sector="Industry")
                 for i in range(6)]
    day = datetime.now(UTC).date() - timedelta(days=1)
    days = []
    while len(days) < 270:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    days.reverse()
    for i, company in enumerate(companies):
        bars = []
        for n, day in enumerate(days):
            close = Decimal(str(50 * (1 + 0.0005 * (i + 1)) ** n))
            bars.append(StooqDailyQuote(date=day, open=close, high=close,
                                       low=close, close=close, volume=100_000))
        await repo.upsert_quotes(company.ticker, bars)
        await repo.upsert_fundamentals(company.ticker, FinancialMetrics(
            pe_ratio=20 - i, return_on_equity=0.1 + i * .02,
            return_on_assets=.04 + i * .01, total_revenue=100_000_000,
            net_income=10_000_000 + i * 1_000_000, market_cap=500_000_000,
            financial_currency="PLN",
        ))
    return repo, companies


def test_refresh_captures_scores_inputs_and_revisions_without_backfill():
    async def run():
        repo, companies = await seed()
        cache = TTLCache()
        refresh = RefreshService(companies, None, TTLCache(), cache, repo=repo)
        assert await refresh._snapshot_long_term(["gpw"]) == 6
        first = await repo.get_long_term_history("qvm5")
        assert len(first) == 1
        assert first[0]["score"] is not None
        assert first[0]["inputs"]["roe"] == pytest.approx(.2)
        assert first[0]["recordedAt"][:10] == datetime.now(UTC).date().isoformat()
        assert first[0]["asOf"] < first[0]["recordedAt"][:10]
        assert first[0]["fundamentalsObservedAt"]
        assert first[0]["modelVersion"] == "qvm-v1"
        await repo.upsert_fundamentals("qvm5", FinancialMetrics(pe_ratio=100))
        await refresh._snapshot_long_term(["gpw"])
        history = await repo.get_long_term_history("qvm5")
        assert len(history) == 2
        assert history[0]["score"] is None
        assert history[1] == first[0]
        assert cache.get(long_term_cache_key("gpw")) is not None
        invalidate_markets(["gpw"], (cache, "ranking"))
        assert cache.get(long_term_cache_key("gpw")) is None

    asyncio.run(run())


def test_future_and_unfinished_bars_are_excluded_and_no_bar_stock_is_not_saved():
    async def run():
        repo, companies = await seed()
        now = datetime.now(UTC).replace(hour=10, minute=0)
        future = now.date() + timedelta(days=2)
        for day in (now.date(), future):
            await repo.upsert_quotes("qvm5", [StooqDailyQuote(
                date=day, open=Decimal(9999), high=Decimal(9999), low=Decimal(9999),
                close=Decimal(9999), volume=100_000,
            )])
        result = await build_long_term_ranking(companies, "gpw", repo, now=now)
        assert all(item.as_of < now.date() for item in result.items)
        empty = GpwCompany(ticker="empty", name="Empty")
        refresh = RefreshService([*companies, empty], None, TTLCache(), TTLCache(), repo=repo)
        await refresh._snapshot_long_term(["gpw"])
        assert await repo.get_long_term_history("empty") == []

    asyncio.run(run())


def test_read_failures_do_not_publish_a_partial_peer_universe():
    class BrokenRepo(InMemoryQuoteRepository):
        async def get_quotes(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(build_long_term_ranking(
            [GpwCompany(ticker="kgh", name="KGHM")], "gpw", BrokenRepo(),
        ))


@pytest.fixture
def api():
    repo, companies = asyncio.run(seed())
    cache = TTLCache()
    app.dependency_overrides[get_quote_repository] = lambda: repo
    app.dependency_overrides[get_gpw_company_service] = lambda: Companies(companies)
    app.dependency_overrides[get_ranking_cache] = lambda: cache
    with TestClient(app) as client:
        yield client, repo
    app.dependency_overrides.clear()


def test_api_rank_and_observation_history_are_read_only(api):
    client, repo = api
    response = client.get("/api/stocks/long-term?market=gpw")
    assert response.status_code == 200
    body = response.json()
    assert body["dbEnabled"] and body["scoredCount"] == 6
    assert body["items"][0]["ticker"] == "qvm5"
    assert not asyncio.run(repo.has_long_term_snapshots())
    assert client.get("/api/stocks/qvm5/long-term-history").json()["items"] == []
    history = client.get("/api/stocks/qvm5/financial-history").json()
    assert len(history["items"]) == 1
    assert history["items"][0]["payload"]["peRatio"] == 15


def test_api_rejects_invalid_market_ticker_limits_and_reports_no_database(api):
    client, _ = api
    assert client.get("/api/stocks/long-term?market=all").status_code == 400
    assert client.get("/api/stocks/missing/long-term-history").status_code == 404
    assert client.get("/api/stocks/qvm5/financial-history?limit=0").status_code == 422
    app.dependency_overrides[get_quote_repository] = lambda: None
    body = client.get("/api/stocks/long-term").json()
    assert body["dbEnabled"] is False and body["items"] == []
    assert client.get("/api/stocks/qvm5/financial-history").json()["dbEnabled"] is False
