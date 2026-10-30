"""Ranking CPU work must leave the API loop free, including on cache hits."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from app.main import app
from app.models import GpwCompany, StooqDailyQuote
from app.services import ranking_service as ranking
from app.services import scanner_service as scanner
from app.services.cache import TTLCache

TODAY = date(2026, 9, 22)


def _inputs(count=3, warm=False):
    companies = [GpwCompany(ticker=f"test{i}", name=f"Test {i}", sector="Test")
                 for i in range(count)]
    quotes = [StooqDailyQuote(
        date=TODAY - timedelta(days=39 - i), open=Decimal(100),
        high=Decimal(101), low=Decimal(99), close=Decimal(100), volume=200_000,
    ) for i in range(40)]
    cache = TTLCache()
    if warm:
        start = TODAY - timedelta(days=ranking.CONTEXT_HISTORY_DAYS)
        for company in companies:
            cache.set(f"history:{company.ticker}:{start}:None", quotes, 3600)
    loop_thread = threading.get_ident()

    class Provider:
        async def get_daily_history(self, ticker, from_date=None):
            assert threading.get_ident() == loop_thread, "Async I/O left its loop"
            assert not warm, "Warm ranking should reuse cached quotes"
            return quotes

    return dict(companies=companies, stooq=Provider(), history_cache=cache,
                history_cache_ttl=3600, today=TODAY)


@pytest.mark.parametrize("warm", [False, True])
@pytest.mark.parametrize("service,stage", [
    (ranking, "detect_signals"), (ranking, "compute_weekly_view"),
    (ranking, "analyze_stock"), (ranking, "_evaluate_methods"),
    (scanner, "detect_signals"),
])
def test_health_responds_while_ranking_analysis_is_blocked(
    monkeypatch, warm, service, stage, request,
):
    """A handshake proves overlap without depending on a millisecond threshold."""
    if service is ranking and stage == "analyze_stock":
        # This stage belongs to Classic VSA; test its preserved scheduling
        # behavior only when explicitly reactivated, never in the live app.
        request.getfixturevalue("archived_methods_enabled")
    async def scenario():
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        entered = asyncio.Event()
        release = threading.Event()
        original = getattr(service, stage)

        def blocked(*args, **kwargs):
            # Fail promptly on the old implementation rather than blocking the
            # test's own event loop. The service catches analysis exceptions,
            # so the missing handshake will then fail the test below.
            assert threading.get_ident() != loop_thread
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(10), "Test did not release ranking analysis"
            return original(*args, **kwargs)

        monkeypatch.setattr(service, stage, blocked)
        compute = ranking.compute_ranking if service is ranking else scanner.compute_scanner_stats
        task = asyncio.create_task(compute(**_inputs(warm=warm)))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
            ) as client:
                response = await asyncio.wait_for(client.get("/health"), 5)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            assert not task.done(), "Health must respond before analysis finishes"
        finally:
            release.set()
            rows = await asyncio.wait_for(task, 10)
        assert len(rows) == (3 if service is ranking else 6)

    asyncio.run(scenario())


@pytest.mark.parametrize("service", [ranking, scanner])
def test_concurrent_scans_and_cancellation_do_not_queue_whole_markets(monkeypatch, service):
    async def scenario():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        two_submissions = asyncio.Event()
        release = threading.Event()
        calls = []

        class RecordingExecutor(ThreadPoolExecutor):
            submissions = 0

            def submit(self, fn, /, *args, **kwargs):
                self.submissions += 1
                if self.submissions == 2:
                    two_submissions.set()
                return super().submit(fn, *args, **kwargs)

        executor = RecordingExecutor(max_workers=1)
        monkeypatch.setattr(service, "_ANALYSIS_EXECUTOR", executor)
        original = service.detect_signals

        def blocked(*args, **kwargs):
            calls.append(threading.get_ident())
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(10)
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "detect_signals", blocked)
        compute = ranking.compute_ranking if service is ranking else scanner.compute_scanner_stats
        tasks = [asyncio.create_task(compute(**_inputs(50, True)))
                 for _ in range(2)]
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await asyncio.wait_for(two_submissions.wait(), 5)
            assert executor.submissions == 2  # one stock per scan, not 100
            assert len(calls) == 1  # one shared worker across both scans
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert all(isinstance(result, asyncio.CancelledError) for result in results)
        finally:
            release.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # Drain the worker before restoring monkeypatches. Its running
            # stock may finish; the queued cancelled scan must never start.
            await loop.run_in_executor(executor, lambda: None)
            executor.shutdown(wait=True)
        assert len(calls) == 1

    asyncio.run(scenario())
