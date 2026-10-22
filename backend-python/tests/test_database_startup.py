"""Configured DB outages must recover in-process and never look like no-DB mode."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app import dependencies, main
from app.db import base, repository
from app.jobs import daily_ingest


async def _until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.001)


async def _health():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test",
    ) as client:
        return await client.get("/health")


@pytest.fixture
def runtime(monkeypatch):
    state = SimpleNamespace(
        available=False, attempts=0, schema_error=False, scheduler_error=False,
        hang=False, probe_cancelled=False, schedulers=[],
    )

    class Engine:
        dispose = AsyncMock()

        @asynccontextmanager
        async def connect(self):
            state.attempts += 1
            if state.hang:
                try:
                    await asyncio.Event().wait()
                finally:
                    state.probe_cancelled = True
            if not state.available:
                raise ConnectionError("database unavailable")
            yield SimpleNamespace(execute=AsyncMock())

        @asynccontextmanager
        async def begin(self):
            if state.schema_error:
                raise ConnectionError("schema transaction failed")
            yield SimpleNamespace(execute=AsyncMock(), run_sync=AsyncMock())

    class Scheduler:
        running = False
        starts = 0
        stops = 0

        def start(self):
            if state.scheduler_error:
                raise RuntimeError("scheduler activation failed")
            self.running = True
            self.starts += 1

        def shutdown(self, wait=False):
            self.running = False
            self.stops += 1

    def build_scheduler(*args, **kwargs):
        scheduler = Scheduler()
        state.schedulers.append(scheduler)
        return scheduler

    state.engine = Engine()
    state.repo = SimpleNamespace(has_today_data=AsyncMock(return_value=False))
    state.plan = AsyncMock(return_value=daily_ingest.BootstrapPlan(full=["gpw"]))
    state.observations = AsyncMock(return_value=[])
    state.refresh = AsyncMock()
    state.live = MagicMock()
    state.live.due_markets.return_value = []
    state.live.run = AsyncMock()
    state.log = MagicMock()
    state.log.start_db_writer = AsyncMock()
    state.log.stop_db_writer = AsyncMock()
    state.http = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(main.settings, "database_url", "postgresql+asyncpg://test/test")
    monkeypatch.setattr(main.settings, "action_log_to_db", True)
    monkeypatch.setattr(main.settings, "live_prices_enabled", True)
    monkeypatch.setattr(main, "_DB_RETRY_DELAY", 0.001)
    monkeypatch.setattr(main, "_DB_MAX_RETRY_DELAY", 0.004)
    monkeypatch.setattr(main, "create_http_client", lambda: state.http)
    monkeypatch.setattr(main, "action_log", state.log)
    monkeypatch.setattr(main, "LivePriceService", lambda **kwargs: state.live)
    monkeypatch.setattr(base, "build_engine", lambda url: state.engine)
    monkeypatch.setattr(base, "build_session_factory", lambda engine: MagicMock())
    monkeypatch.setattr(repository, "PostgresQuoteRepository", lambda factory: state.repo)
    monkeypatch.setattr(daily_ingest.IngestService, "bootstrap_plan", state.plan)
    monkeypatch.setattr(daily_ingest.IngestService, "observation_bootstrap_markets",
                        state.observations)
    monkeypatch.setattr(daily_ingest, "build_scheduler", build_scheduler)
    monkeypatch.setattr(main.RefreshService, "run", state.refresh)
    return state


def _assert_unwired():
    assert dependencies.get_quote_repository() is None
    assert dependencies.get_scheduler() is None
    assert dependencies.get_user_repository() is None
    assert dependencies.get_data_health_repository() is None
    assert dependencies.get_action_log_repository() is None
    assert dependencies.get_live_prices() is None
    assert dependencies.get_refresh_service() is None


def test_outage_beyond_old_retry_limit_recovers_every_service_without_restart(runtime):
    async def scenario():
        async with main.lifespan(main.app):
            await _until(lambda: runtime.attempts >= 7)
            _assert_unwired()
            response = await _health()
            assert response.status_code == 503
            assert response.json()["detail"]["db"] == "initializing"

            main.history_cache.set("outage-data", "stale", 3600)
            main.ranking_cache.set("outage-ranking", "stale", 3600)
            runtime.available = True
            await _until(lambda: dependencies.get_scheduler() is not None)
            assert dependencies.get_quote_repository() is runtime.repo
            assert dependencies.get_user_repository() is not None
            assert dependencies.get_data_health_repository() is not None
            assert dependencies.get_action_log_repository() is not None
            assert dependencies.get_live_prices() is runtime.live
            assert dependencies.get_refresh_service().status().db_enabled is True
            assert main.history_cache.get("outage-data") is None
            assert main.ranking_cache.get("outage-ranking") is None
            assert (await _health()).status_code == 200
            await _until(lambda: runtime.refresh.await_count == 1)
            runtime.refresh.assert_awaited_once_with(
                trigger="bootstrap", markets=["gpw"], full_markets=["gpw"],
            )
            runtime.log.start_db_writer.assert_awaited_once()
            assert len(runtime.schedulers) == 1
            assert runtime.schedulers[0].starts == 1

            # A later outage must report 503, and the wired repository can
            # recover without rebuilding or duplicating the scheduler.
            runtime.repo.has_today_data.side_effect = ConnectionError("lost DB")
            assert (await _health()).status_code == 503
            runtime.repo.has_today_data.side_effect = None
            assert (await _health()).status_code == 200
        _assert_unwired()
        runtime.engine.dispose.assert_awaited_once()
        runtime.http.aclose.assert_awaited_once()
        assert runtime.schedulers[0].stops == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["schema", "bootstrap", "observations", "scheduler"])
def test_partial_initialization_is_retried_without_publishing_services(runtime, stage):
    async def scenario():
        runtime.available = True
        if stage == "schema":
            runtime.schema_error = True
        elif stage == "scheduler":
            runtime.scheduler_error = True
        else:
            query = runtime.plan if stage == "bootstrap" else runtime.observations
            query.side_effect = ConnectionError("startup query failed")
        async with main.lifespan(main.app):
            await _until(lambda: runtime.attempts >= 2)
            _assert_unwired()
            assert (await _health()).status_code == 503
            runtime.refresh.assert_not_awaited()
            runtime.schema_error = runtime.scheduler_error = False
            runtime.plan.side_effect = runtime.observations.side_effect = None
            await _until(lambda: dependencies.get_scheduler() is not None)
            assert (await _health()).status_code == 200
            await _until(lambda: runtime.refresh.await_count == 1)
            assert sum(s.starts for s in runtime.schedulers) == 1
        _assert_unwired()

    asyncio.run(scenario())


def test_shutdown_cancels_a_hung_initialization_before_disposing_engine(runtime):
    async def scenario():
        runtime.hang = True
        async with main.lifespan(main.app):
            await _until(lambda: runtime.attempts == 1)
            assert (await _health()).status_code == 503
        assert runtime.probe_cancelled
        runtime.engine.dispose.assert_awaited_once()
        _assert_unwired()
        assert not any(t.get_name() == "database_startup" for t in asyncio.all_tasks())

    asyncio.run(scenario())


def test_hung_initialization_times_out_and_retries(runtime, monkeypatch):
    monkeypatch.setattr(main, "_DB_INIT_TIMEOUT", 0.01)

    async def scenario():
        runtime.hang = True
        async with main.lifespan(main.app):
            await _until(lambda: runtime.attempts >= 2)
            assert runtime.probe_cancelled
            runtime.hang = False
            runtime.available = True
            await _until(lambda: dependencies.get_scheduler() is not None)
            assert (await _health()).status_code == 200

    asyncio.run(scenario())


def test_readiness_times_out_a_hung_database_probe(runtime, monkeypatch):
    monkeypatch.setattr(main, "_HEALTH_DB_TIMEOUT", 0.01)

    async def hang(*args):
        await asyncio.Event().wait()

    async def scenario():
        runtime.available = True
        async with main.lifespan(main.app):
            await _until(lambda: dependencies.get_scheduler() is not None)
            runtime.repo.has_today_data.side_effect = hang
            response = await asyncio.wait_for(_health(), 2)
            assert response.status_code == 503
            assert response.json()["detail"]["db"] == "unreachable"

    asyncio.run(scenario())


def test_intentional_no_database_mode_remains_healthy(runtime, monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "")

    async def scenario():
        async with main.lifespan(main.app):
            response = await _health()
            assert response.status_code == 200
            assert response.json()["db"] == "disabled"
            assert dependencies.get_refresh_service().status().db_enabled is False
            assert runtime.attempts == 0
            assert dependencies.get_scheduler() is None

    asyncio.run(scenario())
