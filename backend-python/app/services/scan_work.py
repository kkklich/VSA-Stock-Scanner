"""Bound public full-market cache misses without queuing distinct scans."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from threading import Lock
from typing import TypeVar

from fastapi import HTTPException, status

from app.services.auth import LoginThrottle
from app.services.cache import TTLCache

T = TypeVar("T")


class ScanWorkBudget:
    """A process-local work ceiling and per-client miss budget.

    Only admitted compute tasks enter the registry: a new key never waits for
    a slot or creates a per-key lock. Requests for existing work share its task.
    The task owns admission until it finishes, including when all its HTTP
    callers disconnect. Cache hits and joins consume no miss budget.

    This applies to public requests; scheduled refreshes retain their own
    existing scheduling and concurrency limits.
    """

    def __init__(
        self, *, max_concurrent: int = 3, misses_per_minute: int = 24
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be positive")
        self._max_concurrent = max_concurrent
        self._clients = LoginThrottle(
            max_failures=misses_per_minute, window_seconds=60
        )
        # Include cache identity and loop so isolated app/test instances never
        # reuse each other's data or await a task owned by another event loop.
        self._tasks: dict[tuple[TTLCache, str, int, asyncio.AbstractEventLoop], asyncio.Task] = {}
        self._lock = Lock()

    async def run(
        self,
        cache: TTLCache,
        key: str,
        compute: Callable[[], Awaitable[T]],
        *,
        client_key: str | None = None,
    ) -> T:
        cached = cache.get(key)
        if cached is not None:
            return cached

        # A refresh invalidates running results too: callers arriving afterwards
        # must not join a scan built from the previous data generation.
        task_key = (cache, key, cache.generation, asyncio.get_running_loop())
        # Admission and publishing the task are one synchronous operation. No
        # database, provider call, or await occurs under this short-lived lock.
        with self._lock:
            task = self._tasks.get(task_key)
            if task is None:
                if len(self._tasks) >= self._max_concurrent:
                    raise HTTPException(
                        status.HTTP_429_TOO_MANY_REQUESTS,
                        "Market scans are busy. Please try again shortly.",
                        headers={"Retry-After": "5"},
                    )
                if client_key is not None and not self._clients.admit(client_key):
                    raise HTTPException(
                        status.HTTP_429_TOO_MANY_REQUESTS,
                        "Too many uncached market scans. Please try again shortly.",
                        headers={"Retry-After": str(
                            self._clients.retry_after_seconds(client_key)
                        )},
                    )

                async def run_compute() -> T:
                    return await compute()

                task = asyncio.create_task(run_compute())
                self._tasks[task_key] = task
                task.add_done_callback(lambda done: self._finished(task_key, done))

        return await asyncio.shield(task)

    def _finished(self, key: tuple, task: asyncio.Task) -> None:
        with self._lock:
            if self._tasks.get(key) is task:
                del self._tasks[key]
        if not task.cancelled():
            # Observe errors even when every caller has disconnected.
            task.exception()
