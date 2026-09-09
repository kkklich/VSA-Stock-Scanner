"""Cache discipline on the two full-universe endpoints: /ranking and /scanner/stats.

Both endpoints are expensive (a scan of every tracked company) and both are
served from one process-wide cache, so two failure modes matter and neither
shows up as an error anywhere:

* **the stampede** — N cold requests arriving together each start their OWN
  identical scan, and every extra scan competes with the others for the same
  database connections and Yahoo slots, so the cold page gets *slower* the more
  people want it. One lock per cache key collapses them into one computation;
* **the stale write-back** — a scan that STARTED before the nightly refresh
  cleared the caches finishes afterwards and writes its pre-refresh result back
  with a fresh 24-hour TTL. Reading ``generation`` first and writing through
  ``set_if_generation`` serves that caller but refuses to remember the result.

The heatmap and volume-surge endpoints have had this pattern for a while; these
tests cover the two that only gained it in the same change as this file.

The endpoint coroutines are called directly (rather than through TestClient) so
the tests can hold the cache instance and drive real concurrency; the scan
itself is replaced by a counting stand-in, since what is under test is the
discipline around the scan, not the scan.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from fastapi import Response

from app.models import GpwCompany, StockRankingItem
from app.routers import stocks
from app.services.cache import TTLCache

# ── Fixtures ──────────────────────────────────────────────────────────────────


class _FakeCompanyService:
    def get_companies(self) -> list[GpwCompany]:
        return [GpwCompany(ticker="kgh", name="KGHM", sector="Mining", market_cap=None)]


class _CountingCache(TTLCache):
    """A cache that records how many reads found nothing.

    This is what makes the stampede test meaningful. Without it, a run whose
    tasks happened to execute one after another would also see a single
    computation — and pass while proving nothing. Counting the cold reads shows
    that every caller really was inside the cold path at the same time.
    """

    def __init__(self) -> None:
        super().__init__()
        self.misses = 0

    def get(self, key: str):  # type: ignore[override]
        value = super().get(key)
        if value is None:
            self.misses += 1
        return value


def _ranking_row(ticker: str = "KGH") -> StockRankingItem:
    return StockRankingItem(
        ticker=ticker,
        name="KGHM",
        last_price=100.0,
        price_change_pct=0.0,
        current_rating=50,
        rating_change=0,
        last_signal="Hold",
        days_since_signal=999,
        sparkline=[100.0],
        volume=200_000,
    )


@dataclass
class _RawStat:
    """The shape ``compute_scanner_stats`` returns, as the router reads it."""

    signal: str = "Spring"
    count: int = 10
    success_pct: float = 60.0
    reward_risk: float | None = 1.5
    active_count: int = 2


async def _call_ranking(cache: TTLCache) -> list[StockRankingItem]:
    """Invoke the ranking endpoint with explicit dependencies."""
    return await stocks.get_ranking(
        response=Response(),
        companies=_FakeCompanyService(),
        stooq=None,
        cache=cache,
        history_cache=TTLCache(),
        repo=None,
    )


async def _call_scanner_stats(cache: TTLCache):
    return await stocks.get_scanner_stats(
        companies=_FakeCompanyService(),
        stooq=None,
        cache=cache,
        history_cache=TTLCache(),
        repo=None,
    )


@pytest.fixture
def cache() -> _CountingCache:
    return _CountingCache()


# ── One computation per cache key, however many callers arrive ────────────────


class TestConcurrentColdRequests:
    async def test_ranking_computes_once_for_many_simultaneous_callers(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        calls = 0
        first_call_started = asyncio.Event()
        may_finish = asyncio.Event()

        async def fake_compute(**_kwargs) -> list[StockRankingItem]:
            nonlocal calls
            calls += 1
            first_call_started.set()
            await may_finish.wait()  # hold the scan open while the others pile up
            return [_ranking_row()]

        monkeypatch.setattr(stocks, "compute_ranking", fake_compute)

        callers = 5
        tasks = [asyncio.create_task(_call_ranking(cache)) for _ in range(callers)]
        await first_call_started.wait()
        # Let every other task run far enough to miss the cache and block on
        # the lock. If this window were too short the misses assertion below
        # would fail, so the test cannot pass for the wrong reason.
        await asyncio.sleep(0.05)
        may_finish.set()
        results = await asyncio.gather(*tasks)

        assert cache.misses >= callers, "callers were not concurrently in the cold path"
        assert calls == 1, "each concurrent caller started its own full scan"
        # Every caller still gets the answer, not just the one that computed it.
        assert all(len(rows) == 1 for rows in results)
        assert all(rows[0].ticker == "KGH" for rows in results)

    async def test_scanner_stats_computes_once_for_many_simultaneous_callers(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        calls = 0
        first_call_started = asyncio.Event()
        may_finish = asyncio.Event()

        async def fake_compute(**_kwargs) -> list[_RawStat]:
            nonlocal calls
            calls += 1
            first_call_started.set()
            await may_finish.wait()
            return [_RawStat()]

        monkeypatch.setattr(stocks, "compute_scanner_stats", fake_compute)

        callers = 5
        tasks = [asyncio.create_task(_call_scanner_stats(cache)) for _ in range(callers)]
        await first_call_started.wait()
        await asyncio.sleep(0.05)
        may_finish.set()
        results = await asyncio.gather(*tasks)

        assert cache.misses >= callers
        assert calls == 1
        assert all(len(stats) == 1 for stats in results)
        assert all(stats[0].signal == "Spring" for stats in results)

    async def test_different_settings_are_not_serialised_behind_each_other(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        """Two different VSA settings are two different computations.

        They must get different locks, or the second user would wait out the
        first user's whole scan for a result that could not be reused anyway.
        """
        in_flight = 0
        peak = 0
        both_arrived = asyncio.Event()

        async def fake_compute(**_kwargs) -> list[StockRankingItem]:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            if in_flight == 2:
                both_arrived.set()
            await both_arrived.wait()
            in_flight -= 1
            return [_ranking_row()]

        monkeypatch.setattr(stocks, "compute_ranking", fake_compute)

        async def call(vsa_settings: str | None):
            return await stocks.get_ranking(
                response=Response(),
                vsa_settings=vsa_settings,
                companies=_FakeCompanyService(),
                stooq=None,
                cache=cache,
                history_cache=TTLCache(),
                repo=None,
            )

        await asyncio.wait_for(
            asyncio.gather(call(None), call('{"sos": {"volMult": 3.0}}')), timeout=5
        )
        assert peak == 2  # ran side by side, not one after the other

    async def test_a_warm_cache_never_takes_the_lock_path_at_all(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        calls = 0

        async def fake_compute(**_kwargs) -> list[StockRankingItem]:
            nonlocal calls
            calls += 1
            return [_ranking_row()]

        monkeypatch.setattr(stocks, "compute_ranking", fake_compute)

        await _call_ranking(cache)
        await _call_ranking(cache)
        await _call_ranking(cache)
        assert calls == 1


# ── A result that raced the nightly refresh is served, never cached ──────────


class TestGenerationGuard:
    async def test_ranking_result_computed_during_a_refresh_is_not_cached(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        calls = 0

        async def fake_compute(**_kwargs) -> list[StockRankingItem]:
            nonlocal calls
            calls += 1
            # The nightly ingest finishes and clears the caches while this
            # scan is still reading pre-refresh data.
            cache.clear()
            return [_ranking_row()]

        monkeypatch.setattr(stocks, "compute_ranking", fake_compute)

        rows = await _call_ranking(cache)
        assert len(rows) == 1  # the caller is still answered

        # …but the cache did not keep it: the next request recomputes rather
        # than serving pre-refresh numbers for the whole TTL.
        assert cache.get("ranking:full") is None
        await _call_ranking(cache)
        assert calls == 2

    async def test_ranking_result_is_cached_when_no_refresh_intervenes(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        async def fake_compute(**_kwargs) -> list[StockRankingItem]:
            return [_ranking_row()]

        monkeypatch.setattr(stocks, "compute_ranking", fake_compute)

        await _call_ranking(cache)
        assert cache.get("ranking:full") is not None

    async def test_scanner_stats_computed_during_a_refresh_is_not_cached(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        calls = 0

        async def fake_compute(**_kwargs) -> list[_RawStat]:
            nonlocal calls
            calls += 1
            cache.clear()
            return [_RawStat()]

        monkeypatch.setattr(stocks, "compute_scanner_stats", fake_compute)

        stats = await _call_scanner_stats(cache)
        assert len(stats) == 1  # served

        assert cache.get("scanner:stats") is None  # but not remembered
        await _call_scanner_stats(cache)
        assert calls == 2

    async def test_scanner_stats_is_cached_when_no_refresh_intervenes(
        self, monkeypatch: pytest.MonkeyPatch, cache: _CountingCache
    ) -> None:
        async def fake_compute(**_kwargs) -> list[_RawStat]:
            return [_RawStat()]

        monkeypatch.setattr(stocks, "compute_scanner_stats", fake_compute)

        await _call_scanner_stats(cache)
        assert cache.get("scanner:stats") is not None
