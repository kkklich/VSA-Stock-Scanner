"""A tiny thread-safe in-memory TTL cache.

This stands in for .NET's ``IMemoryCache``. It is process-local (fine for a
single-instance deployment); swap for Redis if the API is ever horizontally
scaled.
"""

from __future__ import annotations

import threading
import time
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Maps string keys to values that expire after a per-entry time-to-live."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, T]] = {}
        self._lock = threading.Lock()

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
            return value

    def set(self, key: str, value: T, ttl_seconds: float) -> None:
        """Cache ``value`` under ``key`` for ``ttl_seconds`` seconds."""
        with self._lock:
            self._store[key] = (time.monotonic() + ttl_seconds, value)

    def clear(self) -> None:
        """Drop every cached entry (used after the daily ingestion refresh, or in tests)."""
        with self._lock:
            self._store.clear()
