"""A tiny thread-safe in-memory TTL cache, plus the per-key lock registry.

This stands in for .NET's ``IMemoryCache``. It is process-local (fine for a
single-instance deployment); swap for Redis if the API is ever horizontally
scaled.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")

# Default ceiling on how many entries one cache holds. It exists because
# several cache keys embed values taken straight from the query string —
# ``history:{ticker}:{from}:{to}`` and ``resp:history:{ticker}:{from}:{to}``
# both carry the caller's own dates — so without a ceiling a visitor clicking
# through chart ranges (or a crawler walking them) grows this process's memory
# until it is restarted. 2048 sits comfortably above what the app itself needs
# at rest: the three full-universe scans keep one entry per tracked company
# each (~290 × 3 ≈ 870) and the per-stock pages add a handful more per company
# actually visited. Anything beyond that is user-driven churn, and the
# least-recently-used entry is the right one to lose.
DEFAULT_MAX_ENTRIES = 2048

# How long a "the data provider has nothing for this ticker" answer is
# remembered by the full-universe scans, in seconds.
#
# Without it, a listing the provider cannot serve — one renamed or delisted on
# the GPW, which happens a few times a year — is re-requested by every single
# scan and re-logged every time, so a perfectly healthy run prints a wall of
# errors and pays a failed round-trip per dead ticker. It is deliberately far
# shorter than the positive history TTL (24h): a passing provider hiccup must
# not be able to hide a healthy stock for a whole trading day.
NEGATIVE_CACHE_SECONDS = 60 * 60


class TTLCache(Generic[T]):
    """Maps string keys to values that expire after a per-entry time-to-live.

    Bounded: at most ``max_entries`` entries are kept, and inserting past that
    drops the least recently used one (expired entries go first — they are dead
    weight nobody will read again, whereas evicting a live entry costs a full
    re-computation).
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1.")
        self._max_entries = max_entries
        # An OrderedDict keeps insertion/access order, which is what turns
        # "drop the least recently used entry" into a single popitem() call.
        self._store: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.Lock()
        self._generation = 0

    def get(self, key: str) -> T | None:
        """Return the cached value for ``key``, or ``None`` if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                # Lazily evict the stale entry.
                del self._store[key]
                return None
            # A read counts as "recently used", so this entry now outranks the
            # ones nobody has asked for.
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: T, ttl_seconds: float) -> None:
        """Cache ``value`` under ``key`` for ``ttl_seconds`` seconds."""
        with self._lock:
            self._admit(key, value, ttl_seconds)

    @property
    def generation(self) -> int:
        """Monotonic counter bumped by every ``clear()``.

        A slow computation can read this before starting and use
        ``set_if_generation`` afterwards, so a result built from pre-refresh
        data is never written back into a cache that was invalidated meanwhile.
        """
        with self._lock:
            return self._generation

    def set_if_generation(
        self, key: str, value: T, ttl_seconds: float, generation: int
    ) -> bool:
        """Cache ``value`` only if no ``clear()`` ran since ``generation`` was read.

        Returns ``True`` when the value was stored, ``False`` when it was
        discarded because the cache has been invalidated in the meantime.
        """
        with self._lock:
            if self._generation != generation:
                return False
            self._admit(key, value, ttl_seconds)
            return True

    def clear(self) -> None:
        """Drop every cached entry (used after the daily ingestion refresh, or in tests)."""
        with self._lock:
            self._store.clear()
            self._generation += 1

    def __len__(self) -> int:
        """How many entries are currently held (expired ones included)."""
        with self._lock:
            return len(self._store)

    # ── internals ────────────────────────────────────────────────────────────

    def _admit(self, key: str, value: T, ttl_seconds: float) -> None:
        """Store one entry and enforce the size ceiling. Caller holds the lock."""
        self._store[key] = (time.monotonic() + ttl_seconds, value)
        self._store.move_to_end(key)
        if len(self._store) <= self._max_entries:
            return

        # Over the ceiling. Sweep entries whose TTL has already run out before
        # touching anything live: they will never be read again, so dropping
        # them is free, while dropping a live entry costs whoever wanted it a
        # full re-computation.
        now = time.monotonic()
        for stale in [
            k for k, (expires_at, _) in self._store.items() if expires_at <= now
        ]:
            if stale != key:
                del self._store[stale]

        # Still over? Then the cache really is full of live entries and the
        # least recently used one has to go (it is at the front of the order).
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)


# Default ceiling on remembered locks per registry. A lock costs almost
# nothing, so this only has to stop unbounded growth; 64 distinct in-flight
# cache keys is far more than the app produces in practice (one per VSA
# settings hash, and the UI sends one settings blob at a time).
DEFAULT_MAX_LOCKS = 64


class LockRegistry:
    """Per-cache-key ``asyncio.Lock``s, with a ceiling on how many are kept.

    The heavy scan endpoints keep one lock per cache key so that N concurrent
    cold requests run ONE full-universe scan instead of N. Those keys embed the
    caller's VSA settings hash, so a client that sends a slightly different
    settings blob every time would otherwise mint a lock per request and never
    give one back.

    A lock that is currently **held** is never forgotten: handing the next
    caller a different lock object for the same key would let two scans run at
    once, which is precisely what the lock exists to prevent. Only idle locks
    are dropped, and an idle lock carries no state, so losing one is free.

    Only ever touched from the event loop (all callers are async endpoints), so
    it needs no thread lock of its own.
    """

    def __init__(self, max_locks: int = DEFAULT_MAX_LOCKS) -> None:
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._max_locks = max(1, max_locks)

    def get(self, key: str) -> asyncio.Lock:
        """The lock for ``key``, creating it if this is the first request for it."""
        lock = self._locks.get(key)
        if lock is not None:
            self._locks.move_to_end(key)
            return lock
        self._prune()
        lock = asyncio.Lock()
        self._locks[key] = lock
        return lock

    def __len__(self) -> int:
        return len(self._locks)

    def _prune(self) -> None:
        """Forget idle locks, oldest first, until there is room for one more."""
        if len(self._locks) < self._max_locks:
            return
        for key, lock in list(self._locks.items()):
            if lock.locked():
                continue  # in use — see the class docstring
            del self._locks[key]
            if len(self._locks) < self._max_locks:
                return
