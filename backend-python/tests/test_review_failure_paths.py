"""Regression coverage for partial scans, per-market outages and snapshot loss."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app import dependencies
from app.db.repository import InMemoryQuoteRepository
from app.jobs.daily_ingest import IngestService, IngestStats, MarketIngestStats
from app.main import app
from app.models import GpwCompany
from app.services import ranking_service
from app.services.action_log import OUTCOME_FAILED, OUTCOME_FINISHED, ActionLogService
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.refresh_service import RefreshService, ingest_outcome
from tests.test_ranking import _series

# Exercise the preserved legacy behavior only through an explicit opt-in.
pytestmark = pytest.mark.usefixtures("archived_methods_enabled")


def _company(ticker="kgh"):
    return GpwCompany(ticker=ticker, name=ticker.upper(), sector="Test")


def _dependency(value):
    return lambda: value


@pytest.mark.parametrize("fault", ["database", "analysis", "provider"])
@pytest.mark.parametrize("path", ["/api/stocks/ranking", "/api/stocks/scanner/stats"])
def test_incomplete_scan_returns_503_without_caching_and_retry_recovers(monkeypatch, fault, path):
    async def scenario():
        companies = SimpleNamespace(get_companies=lambda market="gpw": [_company()])
        repo = InMemoryQuoteRepository()
        bars = _series([100.] * 40)
        if fault != "provider":
            await repo.upsert_quotes("kgh", bars)
        provider = SimpleNamespace(get_daily_history=AsyncMock(return_value=bars))
        cache, history = TTLCache(), TTLCache()
        from app.services import scanner_service
        service = ranking_service if path.endswith("ranking") else scanner_service
        original = service.detect_signals
        if fault == "database":
            original_read = repo.get_quotes
            monkeypatch.setattr(repo, "get_quotes",
                                AsyncMock(side_effect=ConnectionError("offline")))
        elif fault == "analysis":
            monkeypatch.setattr(service, "detect_signals", lambda *a, **k: 1 / 0)
        else:
            # Yahoo wraps a transport failure with its original cause.
            error = StooqAccessError("provider unavailable")
            error.__cause__ = TimeoutError("network timeout")
            provider.get_daily_history.side_effect = error
        for dependency, value in (
            (dependencies.get_gpw_company_service, companies),
            (dependencies.get_quote_repository, repo),
            (dependencies.get_stooq_client, provider),
            (dependencies.get_ranking_cache, cache),
            (dependencies.get_history_cache, history),
        ):
            monkeypatch.setitem(app.dependency_overrides, dependency, _dependency(value))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.get(path)
            assert response.status_code == 503, response.text
            assert len(cache) == 0
            if fault == "database":
                monkeypatch.setattr(repo, "get_quotes", original_read)
            elif fault == "analysis":
                monkeypatch.setattr(service, "detect_signals", original)
            else:
                provider.get_daily_history.side_effect = None
            response = await client.get(path)
            assert response.status_code == 200, response.text
            assert response.json()
            assert len(cache) == 1

    asyncio.run(scenario())


def test_failed_ranking_preserves_existing_cache_and_success_time(monkeypatch):
    async def scenario():
        repo = InMemoryQuoteRepository()
        monkeypatch.setattr(repo, "get_quotes", AsyncMock(side_effect=ConnectionError("offline")))
        cache = TTLCache()
        cache.set(ranking_service.ranking_cache_key("gpw"), ["last good ranking"], 3600)
        svc = RefreshService(
            [_company()], None, TTLCache(), cache, repo=repo,
            ingest=SimpleNamespace(run=AsyncMock(return_value=IngestStats(companies=1, fetched=1))),
        )
        previous = datetime(2026, 1, 1, tzinfo=UTC)
        svc.last_refresh_at = previous
        await svc.run()
        assert svc.last_refresh_at == previous
        assert "Ranking incomplete" in svc.last_error
        assert cache.get(ranking_service.ranking_cache_key("gpw")) == ["last good ranking"]

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["provider", "skipped", "empty", "write", "repair"])
def test_small_market_outage_fails_real_ingest_and_refresh(monkeypatch, failure):
    async def scenario():
        companies = [_company(f"stock{i}.us") for i in range(20)] + [_company("small.as")]
        repo = InMemoryQuoteRepository()
        bars = _series([100.] * 40)
        for company in companies:
            await repo.upsert_quotes(company.ticker, bars)
        original_write = repo.upsert_quotes
        if failure == "write":
            async def write(ticker, quotes):
                if ticker == "small.as":
                    raise ConnectionError("market write failed")
                return await original_write(ticker, quotes)
            monkeypatch.setattr(repo, "upsert_quotes", write)

        class Provider:
            calls = 0

            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                if ticker == "small.as":
                    self.calls += 1
                    if failure == "provider":
                        raise ConnectionError("market feed failed")
                    if failure == "skipped":
                        raise StooqAccessError("no data")
                    if failure == "empty":
                        return []
                    if failure == "repair":
                        if self.calls > 1:
                            raise ConnectionError("corporate-action repair failed")
                        return [q.model_copy(update={
                            "open": q.open / 10, "high": q.high / 10,
                            "low": q.low / 10, "close": q.close / 10,
                        }) for q in bars]
                return bars

        history, ranking = TTLCache(), TTLCache()
        provider = Provider()
        ingest = IngestService(companies, provider, repo, history, ranking)
        monkeypatch.setattr(ingest, "_ingest_fundamentals", AsyncMock())
        log = ActionLogService(to_file=False)
        svc = RefreshService(companies, provider, history, ranking,
                             repo=repo, ingest=ingest, action_log=log)
        await svc.run(markets=["us", "nl"])
        entry = log.recent(action="job.ingest")[0]
        assert entry.detail["fetched"] == 20
        assert entry.detail["byMarket"]["us"]["fetched"] == 20
        nl = entry.detail["byMarket"]["nl"]
        assert nl["companies"] == 1 and nl["fetched"] == 0
        assert nl["skipped" if failure in {"skipped", "empty"} else "failed"] == 1
        assert entry.outcome == OUTCOME_FAILED
        assert log.recent(action="job.refresh")[0].outcome == OUTCOME_FAILED
        assert svc.last_refresh_at is None
        assert "Ingest failed for nl" in svc.last_error

    asyncio.run(scenario())


def test_per_market_failure_threshold_keeps_tolerance():
    stats = IngestStats(companies=1000, fetched=998, failed=2, by_market={
        "us": MarketIngestStats(companies=980, fetched=980),
        "nl": MarketIngestStats(companies=20, fetched=18, failed=2),
    })
    assert ingest_outcome(stats) == OUTCOME_FINISHED  # exactly 10%, still tolerated
    stats.by_market["nl"].failed = 3
    stats.by_market["nl"].fetched = 17
    assert ingest_outcome(stats) == OUTCOME_FAILED


def test_snapshot_failure_reports_partial_writes_and_retry_preserves_saved_history(monkeypatch):
    async def scenario():
        companies = [_company("aaa"), _company("bbb")]
        repo = InMemoryQuoteRepository()
        for company in companies:
            await repo.upsert_quotes(company.ticker, _series([100.] * 40))
        original_write = repo.upsert_rating_snapshots

        async def fail_one(ticker, points):
            if ticker == "aaa":
                raise ConnectionError("snapshot table write failed")
            await original_write(ticker, points)

        monkeypatch.setattr(repo, "upsert_rating_snapshots", fail_one)
        log = ActionLogService(to_file=False)
        svc = RefreshService(companies, None, TTLCache(), TTLCache(), repo=repo,
                             action_log=log)
        previous = datetime(2026, 1, 1, tzinfo=UTC)
        svc.last_refresh_at = previous
        await svc.run()
        assert svc.last_refresh_at == previous
        assert "Rating snapshots incomplete: 1 of 2" in svc.last_error
        assert svc.snapshots_written == 1
        assert log.recent(action="job.refresh")[0].outcome == OUTCOME_FAILED
        saved = await repo.get_rating_history("bbb", date.today() - timedelta(days=100))
        assert saved
        recovered_write = AsyncMock(wraps=original_write)
        monkeypatch.setattr(repo, "upsert_rating_snapshots", recovered_write)
        await svc.run()
        assert svc.last_refresh_at > previous
        assert svc.last_error is None
        assert svc.snapshots_written == 1
        assert [call.args[0] for call in recovered_write.await_args_list] == ["aaa"]
        assert await repo.get_rating_history("bbb", date.today() - timedelta(days=100)) == saved

    asyncio.run(scenario())
