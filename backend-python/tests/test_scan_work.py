"""Public whole-market scans share admission, cache reuse and task ownership."""

from __future__ import annotations

import asyncio
from threading import Event

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request, Response

from app import dependencies
from app.models import HeatmapResponse, VolumeSurgeResponse
from app.routers import stocks
from app.services.cache import TTLCache
from app.services.scan_work import ScanWorkBudget


class Companies:
    def get_companies(self, market="gpw"):
        return []


def request(ip="192.0.2.1"):
    return Request({"type": "http", "headers": [], "client": (ip, 1234)})


def scan_dependencies(cache):
    return dict(
        companies=Companies(), stooq=None, cache=cache,
        history_cache=TTLCache(), repo=None,
    )


async def call_endpoint(endpoint, cache, **kwargs):
    if endpoint == "ranking":
        kwargs["response"] = Response()
    return await getattr(stocks, f"get_{endpoint}")(
        **scan_dependencies(cache), **kwargs
    )


def empty_surge(kwargs):
    return VolumeSurgeResponse(**{
        key: kwargs[key] for key in ("recent_days", "baseline_days", "min_ratio")
    })


async def test_distinct_keys_rejected_without_queuing_and_cache_hits_remain_free():
    budget = ScanWorkBudget(max_concurrent=3, misses_per_minute=3)
    cache = TTLCache()
    started = [asyncio.Event() for _ in range(3)]
    finish = asyncio.Event()
    calls = 0

    async def compute(index):
        nonlocal calls
        calls += 1
        started[index].set()
        await finish.wait()
        cache.set(str(index), index, 60)
        return index

    tasks = [asyncio.create_task(budget.run(
        cache, str(i), lambda i=i: compute(i), client_key="client"
    )) for i in range(3)]
    try:
        await asyncio.wait_for(asyncio.gather(*(s.wait() for s in started)), 2)
        for key in range(3, 103):
            with pytest.raises(HTTPException) as exc:
                await budget.run(cache, str(key), lambda: compute(0), client_key="other")
            assert exc.value.status_code == 429
            assert int(exc.value.headers["Retry-After"]) > 0
        assert calls == 3
        assert len(budget._tasks) == 3

        cache.set("warm", [], 60)
        assert await budget.run(cache, "warm", lambda: compute(0), client_key="client") == []
        joined = asyncio.create_task(budget.run(
            cache, "0", lambda: compute(0), client_key="client"
        ))
        await asyncio.sleep(0)
        assert not joined.done()
    finally:
        finish.set()
        await asyncio.gather(*tasks)
    assert await joined == 0
    assert calls == 3
    # Warm reads and same-key joins did not consume or require extra credit.
    assert await budget.run(cache, "0", lambda: compute(0), client_key="client") == 0
    with pytest.raises(HTTPException) as exc:
        await budget.run(cache, "fourth", lambda: compute(0), client_key="client")
    assert exc.value.status_code == 429
    assert await budget.run(cache, "fourth", lambda: compute(0), client_key="other") == 0


async def test_request_cancellation_keeps_slot_until_underlying_worker_finishes():
    budget = ScanWorkBudget(max_concurrent=1)
    cache = TTLCache()
    started = asyncio.Event()
    release = Event()
    loop = asyncio.get_running_loop()
    calls = 0

    def worker():
        nonlocal calls
        calls += 1
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5), "test did not release worker"
        return "finished"

    async def compute():
        result = await asyncio.to_thread(worker)
        cache.set("running", result, 60)
        return result

    caller = asyncio.create_task(budget.run(cache, "running", compute))
    await asyncio.wait_for(started.wait(), 2)
    try:
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        with pytest.raises(HTTPException) as exc:
            await budget.run(cache, "another", compute)
        assert exc.value.status_code == 429
        joined = asyncio.create_task(budget.run(cache, "running", compute))
        await asyncio.sleep(0)
        assert not joined.done()
        assert calls == 1
    finally:
        release.set()
    assert await joined == "finished"
    assert not budget._tasks
    assert calls == 1
    assert await budget.run(cache, "another", compute) == "finished"


async def test_compute_failure_releases_admission_and_does_not_cache_failure():
    budget = ScanWorkBudget(max_concurrent=1)
    cache = TTLCache()
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("provider unavailable")
        return []

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await budget.run(cache, "ranking", compute)
    assert not budget._tasks
    assert cache.get("ranking") is None
    assert await budget.run(cache, "ranking", compute) == []
    assert calls == 2


async def test_refresh_starts_fresh_work_without_joining_previous_generation():
    budget = ScanWorkBudget(max_concurrent=2)
    cache = TTLCache()
    started = [asyncio.Event(), asyncio.Event()]
    finish = asyncio.Event()
    calls = []

    async def compute():
        generation = cache.generation
        calls.append(generation)
        started[generation].set()
        await finish.wait()
        cache.set_if_generation("ranking", generation, 60, generation)
        return generation

    old = asyncio.create_task(budget.run(cache, "ranking", compute))
    await asyncio.wait_for(started[0].wait(), 2)
    cache.clear()
    fresh = asyncio.create_task(budget.run(cache, "ranking", compute))
    try:
        await asyncio.wait_for(started[1].wait(), 2)
        assert len(budget._tasks) == 2
        with pytest.raises(HTTPException) as exc:
            await budget.run(cache, "another", compute)
        assert exc.value.status_code == 429
    finally:
        finish.set()
        results = await asyncio.gather(old, fresh)
    assert results == [0, 1]
    assert calls == [0, 1]
    assert cache.get("ranking") == 1
    assert not budget._tasks


@pytest.mark.usefixtures("archived_methods_enabled")
async def test_ranking_overview_heatmap_surge_and_stats_share_one_ceiling(monkeypatch):
    budget = ScanWorkBudget(max_concurrent=3)
    monkeypatch.setattr(stocks, "_scan_work", budget)
    cache = TTLCache()
    started = {key: asyncio.Event() for key in ("ranking", "heatmap", "volume_surge")}
    finish = asyncio.Event()
    calls = []

    async def ranking(**kwargs):
        calls.append("ranking")
        started["ranking"].set()
        await finish.wait()
        return []

    async def heatmap(**kwargs):
        calls.append("heatmap")
        started["heatmap"].set()
        await finish.wait()
        return HeatmapResponse()

    async def surge(**kwargs):
        calls.append("volume_surge")
        started["volume_surge"].set()
        await finish.wait()
        return empty_surge(kwargs)

    async def forbidden(**kwargs):
        pytest.fail("rejected scanner must not begin work")

    monkeypatch.setattr(stocks, "compute_ranking", ranking)
    monkeypatch.setattr(stocks, "compute_heatmap", heatmap)
    monkeypatch.setattr(stocks, "compute_volume_surge", surge)
    monkeypatch.setattr(stocks, "compute_scanner_stats", forbidden)
    tasks = [asyncio.create_task(call_endpoint(key, cache, request=request())) for key in started]
    try:
        await asyncio.wait_for(asyncio.gather(*(s.wait() for s in started.values())), 2)
        for endpoint, kwargs in (
            ("market_overview", {"vsa_settings": '{"sos":{"volMult":3.0}}'}),
            ("volume_surge", {"recent_days": 2}),
            ("scanner_stats", {}),
        ):
            with pytest.raises(HTTPException) as exc:
                await call_endpoint(endpoint, cache, request=request("192.0.2.2"), **kwargs)
            assert exc.value.status_code == 429
        # The overview can still join its ranking's existing task at capacity.
        overview = asyncio.create_task(call_endpoint("market_overview", cache, request=request()))
        await asyncio.sleep(0)
        assert not overview.done()
        assert len(calls) == 3
    finally:
        finish.set()
        await asyncio.gather(*tasks)
    await overview
    assert sorted(calls) == ["heatmap", "ranking", "volume_surge"]
    assert not budget._tasks


@pytest.mark.parametrize("endpoint", ["ranking", "market_overview", "heatmap", "volume_surge"])
async def test_inactive_classic_settings_reuse_the_default_scan(monkeypatch, endpoint):
    monkeypatch.setattr(stocks, "_scan_work", ScanWorkBudget())
    cache = TTLCache()
    calls = []

    async def compute(**kwargs):
        calls.append(kwargs["config"])
        if endpoint == "heatmap":
            return HeatmapResponse()
        if endpoint == "volume_surge":
            return empty_surge(kwargs)
        return []

    computation = "ranking" if endpoint == "market_overview" else endpoint
    monkeypatch.setattr(stocks, f"compute_{computation}", compute)
    for settings in (None, '{"sos":{"volMult":3.0}}', '{"sos":{"volMult":4.0}}'):
        await call_endpoint(endpoint, cache, vsa_settings=settings)
    assert len(calls) == 1
    assert calls[0].is_default()


@pytest.mark.usefixtures("archived_methods_enabled")
async def test_active_classic_settings_still_compute_distinct_variants(monkeypatch):
    monkeypatch.setattr(stocks, "_scan_work", ScanWorkBudget(max_concurrent=3))
    cache = TTLCache()
    started = asyncio.Event()
    finish = asyncio.Event()
    configs = []

    async def compute(**kwargs):
        configs.append(kwargs["config"].cache_suffix())
        if len(configs) == 3:
            started.set()
        await finish.wait()
        return []

    monkeypatch.setattr(stocks, "compute_ranking", compute)
    tasks = [asyncio.create_task(call_endpoint("ranking", cache, vsa_settings=s)) for s in (
        None, '{"sos":{"volMult":3.0}}', '{"sos":{"volMult":4.0}}',
    )]
    try:
        await asyncio.wait_for(started.wait(), 2)
        assert len(set(configs)) == 3
        with pytest.raises(HTTPException) as exc:
            await call_endpoint("ranking", cache, vsa_settings='{"sos":{"volMult":5.0}}')
        assert exc.value.status_code == 429
    finally:
        finish.set()
        await asyncio.gather(*tasks)


async def test_http_miss_budget_is_shared_across_endpoints_and_returns_retry_header(monkeypatch):
    monkeypatch.setattr(stocks, "_scan_work", ScanWorkBudget(misses_per_minute=1))
    cache = TTLCache()

    async def surge(**kwargs):
        return empty_surge(kwargs)

    monkeypatch.setattr(stocks, "compute_volume_surge", surge)
    app = FastAPI()
    app.include_router(stocks.router)

    def override(value):
        def provide():
            return value
        return provide

    for dependency, value in (
        (dependencies.get_gpw_company_service, Companies()),
        (dependencies.get_stooq_client, None),
        (dependencies.get_ranking_cache, cache),
        (dependencies.get_history_cache, TTLCache()),
        (dependencies.get_quote_repository, None),
        (dependencies.get_live_prices, None),
    ):
        app.dependency_overrides[dependency] = override(value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/stocks/volume-surge")).status_code == 200
        blocked = await client.get("/api/stocks/heatmap")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert (await client.get("/api/stocks/volume-surge")).status_code == 200
