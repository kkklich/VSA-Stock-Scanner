"""Tests for the in-memory TTL cache and the per-key lock registry.

Both are small, but several endpoints lean on their exact semantics:

* the heavy scan endpoints read ``generation`` before a long computation and
  write the result back with ``set_if_generation``, so a scan that raced the
  nightly refresh is served but never remembered as current;
* the same endpoints keep one ``asyncio.Lock`` per cache key so that N
  concurrent cold requests run ONE full-universe scan instead of N;
* both containers are now bounded, because several cache keys (and every lock
  key) embed values taken straight from the query string.

The bound is the newest of those, so the eviction ORDER is pinned here: an
expired entry is dead weight and goes first, and only then the least recently
used live one — dropping a live entry costs whoever wanted it a full
re-computation.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.cache import DEFAULT_MAX_ENTRIES, LockRegistry, TTLCache

# A TTL long enough that nothing expires during a test run.
_LONG = 300.0
# A TTL that is already spent the moment it is written.
_DEAD = 0.0


# ── TTLCache: the basics the generation guard is built on ─────────────────────


class TestTTLCacheBasics:
    def test_stores_and_returns_a_value(self) -> None:
        cache: TTLCache[str] = TTLCache()
        cache.set("k", "v", _LONG)
        assert cache.get("k") == "v"

    def test_missing_key_is_none(self) -> None:
        cache: TTLCache[str] = TTLCache()
        assert cache.get("nope") is None

    def test_get_lazily_evicts_an_expired_entry(self) -> None:
        # The entry is still counted until somebody asks for it; the read is
        # what drops it. Nothing sweeps the cache on a timer.
        cache: TTLCache[str] = TTLCache()
        cache.set("k", "v", _DEAD)
        assert len(cache) == 1
        assert cache.get("k") is None
        assert len(cache) == 0

    def test_clear_empties_the_cache(self) -> None:
        cache: TTLCache[str] = TTLCache()
        cache.set("a", "1", _LONG)
        cache.set("b", "2", _LONG)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None

    def test_max_entries_must_be_at_least_one(self) -> None:
        with pytest.raises(ValueError):
            TTLCache(max_entries=0)

    def test_default_ceiling_clears_the_app_s_resting_footprint(self) -> None:
        # ~290 tracked companies × the three full-universe scans that each keep
        # one history entry per ticker. If the default ever dropped below that,
        # the scans would evict each other's work on every run.
        assert DEFAULT_MAX_ENTRIES > 290 * 3


# ── TTLCache: the size ceiling and its eviction order ─────────────────────────


class TestTTLCacheBound:
    def test_never_grows_past_the_ceiling(self) -> None:
        cache: TTLCache[int] = TTLCache(max_entries=5)
        for i in range(50):
            cache.set(f"k{i}", i, _LONG)
        assert len(cache) == 5

    def test_least_recently_used_live_entry_is_the_one_dropped(self) -> None:
        cache: TTLCache[str] = TTLCache(max_entries=3)
        cache.set("a", "1", _LONG)
        cache.set("b", "2", _LONG)
        cache.set("c", "3", _LONG)

        # Reading "a" makes it the most recently used, so "b" is now the
        # coldest entry and the right one to lose.
        assert cache.get("a") == "1"
        cache.set("d", "4", _LONG)

        assert cache.get("b") is None  # evicted
        assert cache.get("a") == "1"  # survived because it was read
        assert cache.get("c") == "3"
        assert cache.get("d") == "4"

    def test_expired_entries_are_dropped_before_any_live_one(self) -> None:
        # "dead" is already expired, so it costs nothing to lose; "a" is live
        # and losing it would cost a full re-computation. The expired one goes.
        cache: TTLCache[str] = TTLCache(max_entries=3)
        cache.set("dead", "stale", _DEAD)
        cache.set("a", "1", _LONG)
        cache.set("b", "2", _LONG)
        cache.set("c", "3", _LONG)  # one over the ceiling

        assert len(cache) == 3
        assert cache.get("dead") is None
        assert cache.get("a") == "1"  # oldest LIVE entry, but kept
        assert cache.get("b") == "2"
        assert cache.get("c") == "3"

    def test_the_entry_just_written_is_never_the_one_evicted(self) -> None:
        # A cache of one: writing must leave the new value readable, not
        # immediately sacrifice it to its own ceiling.
        cache: TTLCache[str] = TTLCache(max_entries=1)
        cache.set("a", "1", _LONG)
        cache.set("b", "2", _LONG)
        assert cache.get("b") == "2"
        assert cache.get("a") is None


# ── TTLCache: generation / set_if_generation ─────────────────────────────────


class TestTTLCacheGeneration:
    """Several endpoints depend on these exact semantics — see the module note."""

    def test_generation_starts_at_zero_and_only_clear_bumps_it(self) -> None:
        cache: TTLCache[str] = TTLCache()
        assert cache.generation == 0
        cache.set("a", "1", _LONG)
        cache.get("a")
        assert cache.generation == 0
        cache.clear()
        assert cache.generation == 1
        cache.clear()
        assert cache.generation == 2

    def test_write_succeeds_when_no_clear_happened(self) -> None:
        cache: TTLCache[str] = TTLCache()
        generation = cache.generation
        assert cache.set_if_generation("k", "v", _LONG, generation) is True
        assert cache.get("k") == "v"

    def test_write_is_discarded_when_a_clear_happened_meanwhile(self) -> None:
        # The shape of a scan that started before the nightly refresh and
        # finished after it: the caller still gets its result, but the cache
        # must not remember pre-refresh data as current.
        cache: TTLCache[str] = TTLCache()
        generation = cache.generation
        cache.clear()  # the refresh lands mid-computation
        assert cache.set_if_generation("k", "v", _LONG, generation) is False
        assert cache.get("k") is None

    def test_a_later_generation_can_write_again(self) -> None:
        cache: TTLCache[str] = TTLCache()
        cache.clear()
        generation = cache.generation
        assert cache.set_if_generation("k", "v", _LONG, generation) is True
        assert cache.get("k") == "v"

    def test_guarded_writes_obey_the_size_ceiling_too(self) -> None:
        cache: TTLCache[int] = TTLCache(max_entries=2)
        for i in range(10):
            assert cache.set_if_generation(f"k{i}", i, _LONG, cache.generation) is True
        assert len(cache) == 2


# ── LockRegistry ──────────────────────────────────────────────────────────────


class TestLockRegistry:
    def test_same_key_always_returns_the_same_lock(self) -> None:
        # The whole point: two concurrent requests for one cache key must
        # contend on ONE lock object, or both would run the same scan.
        registry = LockRegistry()
        assert registry.get("ranking:full") is registry.get("ranking:full")

    def test_different_keys_get_different_locks(self) -> None:
        # Different VSA settings are different computations and must not queue
        # behind each other.
        registry = LockRegistry()
        assert registry.get("ranking:full") is not registry.get("ranking:full:custom")

    def test_number_of_remembered_locks_is_bounded(self) -> None:
        # The key embeds the caller's settings hash, which is user-supplied: a
        # client sending a fresh blob every time must not grow this forever.
        registry = LockRegistry(max_locks=4)
        for i in range(200):
            registry.get(f"key-{i}")
        assert len(registry) <= 4

    def test_idle_locks_are_forgotten_oldest_first(self) -> None:
        registry = LockRegistry(max_locks=2)
        first = registry.get("a")
        registry.get("b")
        registry.get("c")  # pushes the registry over, so "a" is dropped
        assert registry.get("a") is not first

    def test_a_lock_kept_warm_by_use_survives_the_prune(self) -> None:
        registry = LockRegistry(max_locks=3)
        hot = registry.get("hot")
        for i in range(20):
            registry.get(f"cold-{i}")
            registry.get("hot")  # touched again, so never the oldest
        assert registry.get("hot") is hot

    async def test_a_held_lock_is_never_handed_out_as_a_new_object(self) -> None:
        # Forgetting a HELD lock would give the next caller a different lock
        # for the same key — two scans running at once, which is exactly what
        # the lock exists to prevent. The ceiling yields instead.
        registry = LockRegistry(max_locks=2)
        held = registry.get("busy")
        async with held:
            for i in range(20):
                registry.get(f"other-{i}")
            assert registry.get("busy") is held
            assert held.locked()

    async def test_a_lock_released_again_becomes_prunable(self) -> None:
        registry = LockRegistry(max_locks=2)
        lock = registry.get("busy")
        async with lock:
            pass
        assert not lock.locked()
        for i in range(20):
            registry.get(f"other-{i}")
        assert len(registry) <= 2

    async def test_two_waiters_on_one_key_run_one_at_a_time(self) -> None:
        """The behaviour the endpoints buy with this class, end to end."""
        registry = LockRegistry()
        concurrent = 0
        peak = 0

        async def critical_section() -> None:
            nonlocal concurrent, peak
            async with registry.get("shared"):
                concurrent += 1
                peak = max(peak, concurrent)
                await asyncio.sleep(0)  # give the others a chance to barge in
                concurrent -= 1

        await asyncio.gather(*(critical_section() for _ in range(5)))
        assert peak == 1
