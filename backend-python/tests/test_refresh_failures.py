"""The ingest verdict must agree with refresh status and the parent job log."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import get_refresh_service
from app.jobs.daily_ingest import IngestStats
from app.main import app
from app.models import GpwCompany
from app.services import refresh_service
from app.services.action_log import (
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_SKIPPED,
    OUTCOME_STARTED,
    ActionLogService,
)
from app.services.cache import TTLCache


@pytest.fixture
def pipeline(monkeypatch):
    ingest = SimpleNamespace(run=AsyncMock())
    log = ActionLogService(to_file=False)
    service = refresh_service.RefreshService(
        companies=[GpwCompany(ticker="kgh", name="KGHM", sector="Mining")],
        stooq=None, repo=InMemoryQuoteRepository(), ingest=ingest,
        history_cache=TTLCache(), ranking_cache=TTLCache(), action_log=log,
    )
    ranking = AsyncMock(return_value=[])
    monkeypatch.setattr(refresh_service, "compute_ranking", ranking)
    snapshots = AsyncMock(return_value=0)
    long_term = AsyncMock(return_value=0)
    live = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "_snapshot_ratings", snapshots)
    monkeypatch.setattr(service, "_snapshot_long_term", long_term)
    monkeypatch.setattr(service, "_refresh_live", live)
    return SimpleNamespace(service=service, ingest=ingest, log=log,
                           subsequent=[ranking, snapshots, long_term, live])


@pytest.mark.parametrize("previous_success", [None, datetime(2026, 1, 1, tzinfo=UTC)])
@pytest.mark.parametrize("stats", [
    IngestStats(companies=100, fetched=0, failed=100),
    IngestStats(companies=100, fetched=0, skipped=100),
    IngestStats(companies=100, fetched=89, failed=11),
])
def test_failed_ingest_preserves_success_time_and_stops_pipeline(
    pipeline, stats, previous_success,
):
    svc = pipeline.service
    svc.last_refresh_at = previous_success
    svc.stocks_ranked = svc.snapshots_written = svc.long_term_snapshots_written = 42
    pipeline.ingest.run.return_value = stats

    asyncio.run(svc.run(trigger="manual", request_id="failure-test"))

    assert svc.last_refresh_at == previous_success
    assert svc.last_started_at is not None
    assert svc.last_error and "Ingest failed for gpw" in svc.last_error
    assert f"{stats.failed} failed, {stats.skipped} skipped" in svc.last_error
    assert svc.status().last_error == svc.last_error
    assert svc.status().state == "idle"
    assert svc.stocks_ranked is None
    assert svc.snapshots_written is None
    assert svc.long_term_snapshots_written is None
    for step in pipeline.subsequent:
        step.assert_not_awaited()
    ingest_entry = pipeline.log.recent(action="job.ingest")[0]
    assert ingest_entry.outcome == OUTCOME_FAILED
    assert ingest_entry.detail == stats.as_detail()
    refresh_entries = pipeline.log.recent(action="job.refresh")
    assert [e.outcome for e in refresh_entries] == [OUTCOME_FAILED, OUTCOME_STARTED]
    assert svc.last_error in refresh_entries[0].detail["error"]
    assert refresh_entries[0].detail["markets"] == ["gpw"]
    assert all(e.request_id == "failure-test" for e in [ingest_entry, *refresh_entries])


@pytest.mark.parametrize("stats", [
    IngestStats(companies=100, fetched=100),
    IngestStats(companies=100, fetched=99, failed=1),
    IngestStats(companies=100, fetched=90, failed=10),
    IngestStats(companies=100, fetched=95, skipped=5),
    IngestStats(companies=0),
])
def test_successful_ingest_keeps_existing_tolerance_and_clears_error(pipeline, stats):
    svc = pipeline.service
    previous = datetime(2026, 1, 1, tzinfo=UTC)
    svc.last_refresh_at = previous
    svc.last_error = "Previous ingest failed"
    pipeline.ingest.run.return_value = stats

    asyncio.run(svc.run())

    assert svc.last_refresh_at > previous
    assert svc.last_error is None
    assert svc.stocks_ranked == 0
    for step in pipeline.subsequent:
        step.assert_awaited_once()
    assert pipeline.log.recent(action="job.ingest")[0].outcome == OUTCOME_FINISHED
    assert pipeline.log.recent(action="job.refresh")[0].outcome == OUTCOME_FINISHED


def test_ingest_skipped_because_busy_cannot_report_refresh_success(pipeline):
    pipeline.ingest.run.return_value = None
    asyncio.run(pipeline.service.run())
    assert pipeline.service.last_refresh_at is None
    assert "already running" in pipeline.service.last_error
    assert pipeline.log.recent(action="job.ingest")[0].outcome == OUTCOME_SKIPPED
    assert pipeline.log.recent(action="job.refresh")[0].outcome == OUTCOME_FAILED
    for step in pipeline.subsequent:
        step.assert_not_awaited()


def test_status_endpoint_reports_failed_ingest_then_successful_retry(pipeline, monkeypatch):
    svc = pipeline.service
    monkeypatch.setitem(app.dependency_overrides, get_refresh_service, lambda: svc)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            pipeline.ingest.run.return_value = IngestStats(companies=1, failed=1)
            await svc.run()
            response = await client.get("/api/stocks/refresh/status")
            assert response.status_code == 200
            failed = response.json()
            assert failed["lastRefreshAt"] is None
            assert failed["lastError"] and "Ingest failed" in failed["lastError"]
            assert failed["stocksRanked"] is None

            pipeline.ingest.run.return_value = IngestStats(companies=1, fetched=1)
            await svc.run()
            succeeded = (await client.get("/api/stocks/refresh/status")).json()
            assert succeeded["lastRefreshAt"] is not None
            assert succeeded["lastError"] is None
            assert succeeded["state"] == "idle"

    asyncio.run(scenario())
