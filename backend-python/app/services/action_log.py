"""Action log — a persistent record of *what the app did and when*.

Every API call and every background job writes one entry here. Before this
existed the app only printed to the console, which vanishes on restart, so
questions like "when did the last refresh actually run?", "which screens were
hit before it broke?" or "did the nightly job fail silently?" had no answer.

An entry goes to up to three places, in this order:

  1. **A rotating JSON-lines file** — ``logs/actions.jsonl`` next to the
     backend (see ``Settings.action_log_path``). Written synchronously, so a
     record survives even if the process is killed a moment later. Rotation
     caps the disk cost at ``(backups + 1) x max_bytes``.
  2. **The ``action_logs`` database table** — when a database is configured.
     Queued and written in batches by a background worker, never on the
     request's own path, and dropped rather than blocking if the queue backs
     up (a full log queue must never make the API slow).
  3. **An in-memory ring buffer** of the most recent entries, so
     ``GET /api/admin/logs`` still answers when the app runs without a
     database.

Two kinds of entry:

  * ``kind="request"`` — one per HTTP call, written by ``ActionLogMiddleware``:
    route, status, duration, response size, client, request id.
  * ``kind="job"`` — the side-effectful work, written by the callers
    themselves: ``POST /api/stocks/refresh`` and the nightly ingest record
    *started* / *finished* / *failed* with their own outcome numbers
    (tickers fetched vs failed, stocks ranked, error text). A status code
    cannot say whether a background job that was accepted with 202 later
    succeeded — this is what makes a silently failing nightly job visible.

Nothing sensitive is recorded: the ``settings`` query parameter (a whole VSA
configuration blob) is reduced to a short hash, anything whose name looks like
a credential is masked, and values are truncated.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_WARSAW = ZoneInfo("Europe/Warsaw")

# Outcomes. Requests get one derived from the status code; jobs report their
# own. Kept as plain strings so the admin endpoint can filter on them.
OUTCOME_OK = "ok"
OUTCOME_CLIENT_ERROR = "client_error"
OUTCOME_SERVER_ERROR = "server_error"
OUTCOME_STARTED = "started"
OUTCOME_FINISHED = "finished"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"

# Kinds. "request" and "job" entries are written here; "error" entries come
# from the error tracker (app/services/error_tracker.py), which mirrors every
# grouped failure into this same log so it inherits the file, the table, the
# retention prune and the admin API.
KIND_REQUEST = "request"
KIND_JOB = "job"
KIND_ERROR = "error"

# Query-parameter names whose VALUE is never stored verbatim.
_HASHED_PARAMS = frozenset({"settings"})
_MASKED_PARAMS = frozenset(
    {"token", "key", "apikey", "api_key", "password", "passwd", "secret",
     "authorization", "auth", "signature", "session"}
)

# Length caps — one log line must never become a payload dump.
_MAX_PARAM_VALUE = 80
_MAX_QUERY = 500
_MAX_USER_AGENT = 200
_MAX_ERROR = 500

# Queue/batch sizing for the database writer.
_QUEUE_MAX = 5000
_BATCH_MAX = 200
_BATCH_WAIT_SECONDS = 1.0
# How often the writer deletes rows past the retention window.
_PRUNE_INTERVAL_SECONDS = 6 * 60 * 60
# How long a shutdown waits for the writer to flush before giving up on it.
_STOP_TIMEOUT_SECONDS = 5.0

# Put on the queue to ask the writer to flush its current batch and finish.
_SHUTDOWN = object()


# ── The entry ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ActionLogEntry:
    """One recorded action. The same shape reaches the file, the DB and the API."""

    action: str
    kind: str = "request"
    outcome: str = OUTCOME_OK
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    duration_ms: float | None = None
    method: str | None = None
    path: str | None = None
    query: str | None = None
    status_code: int | None = None
    response_bytes: int | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    # Free-form extras: job counters, error text. JSON-serialisable only.
    detail: dict[str, Any] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """The JSON-lines form. Carries both UTC and Warsaw local time.

        UTC is what the database stores and what sorts correctly; the local
        time is there because the owner reads the file with GPW session times
        in mind ("did the 18:00 job run?") and should not have to convert.
        """
        return {
            "ts": self.started_at.astimezone(UTC).isoformat(),
            "tsLocal": self.started_at.astimezone(_WARSAW).isoformat(),
            "requestId": self.request_id,
            "kind": self.kind,
            "action": self.action,
            "outcome": self.outcome,
            "method": self.method,
            "path": self.path,
            "query": self.query,
            "status": self.status_code,
            "durationMs": (
                round(self.duration_ms, 1) if self.duration_ms is not None else None
            ),
            "bytes": self.response_bytes,
            "clientIp": self.client_ip,
            "userAgent": self.user_agent,
            "detail": self.detail,
        }


# ── Sanitising helpers ────────────────────────────────────────────────────────


def sanitize_query(raw: str) -> str | None:
    """Reduce a raw query string to something safe and short to store.

    ``settings`` (the whole VSA engine configuration) becomes a short hash, so
    two calls made with the same configuration are still recognisably the same
    without the blob ever being written down. Credential-looking names are
    masked, every value is truncated, and the whole string is capped.
    """
    if not raw:
        return None
    parts: list[str] = []
    for key, value in parse_qsl(raw, keep_blank_values=True):
        low = key.lower()
        if low in _HASHED_PARAMS:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
            parts.append(f"{key}=sha256:{digest}")
        elif low in _MASKED_PARAMS:
            parts.append(f"{key}=***")
        else:
            if len(value) > _MAX_PARAM_VALUE:
                value = value[:_MAX_PARAM_VALUE] + "…"
            parts.append(f"{key}={value}")
    joined = "&".join(parts)
    if len(joined) > _MAX_QUERY:
        joined = joined[:_MAX_QUERY] + "…"
    return joined or None


def outcome_for_status(status_code: int) -> str:
    if status_code >= 500:
        return OUTCOME_SERVER_ERROR
    if status_code >= 400:
        return OUTCOME_CLIENT_ERROR
    return OUTCOME_OK


def _content_length(response: Response) -> int | None:
    """Response size in bytes, when the response declares one.

    A streaming response has no Content-Length; the field stays ``None``
    rather than being guessed.
    """
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _client_ip(request: Request) -> str | None:
    """The caller's address, honouring the reverse proxy in production.

    In the deployed stack Nginx and the web container sit in front of the API,
    so ``request.client`` is the proxy. The first entry of X-Forwarded-For is
    the original client.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    if request.client is not None:
        return request.client.host
    return None


# ── The service ───────────────────────────────────────────────────────────────


class ActionLogService:
    """Records entries to the file, the database queue and the memory buffer.

    One instance per process, created in ``app/dependencies.py``. Safe to use
    before ``start()`` has been called (the DB half is simply inactive), which
    matters because requests can arrive while the lifespan is still wiring the
    database up.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        to_file: bool = True,
        directory: Path | None = None,
        file_max_bytes: int = 10 * 1024 * 1024,
        file_backups: int = 5,
        memory_entries: int = 2000,
        exclude_paths: Iterable[str] = ("/health",),
    ) -> None:
        self._enabled = enabled
        self._to_file = to_file
        self._directory = directory
        self._file_max_bytes = file_max_bytes
        self._file_backups = file_backups
        self._exclude_paths = frozenset(exclude_paths)
        self._recent: deque[ActionLogEntry] = deque(maxlen=max(1, memory_entries))

        self._file_logger: logging.Logger | None = None
        self._file_path: Path | None = None

        self._repo: Any | None = None
        self._queue: asyncio.Queue[ActionLogEntry] | None = None
        self._worker: asyncio.Task | None = None
        # The loop the queue and its worker belong to. Needed because record()
        # is reachable from worker threads — see the note there.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._retention_days = 0
        # Counters for the admin summary — how healthy the log itself is.
        self.recorded_count = 0
        self.dropped_count = 0
        self.db_written_count = 0

    # ── Wiring ────────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def file_path(self) -> Path | None:
        """Absolute path of the JSON-lines file, or None when file logging is off."""
        return self._file_path

    @property
    def db_active(self) -> bool:
        return self._repo is not None and self._worker is not None

    def excludes(self, path: str) -> bool:
        return path in self._exclude_paths

    def open_file(self) -> None:
        """Create the log directory and attach the rotating file handler.

        Failing to open the file is logged and then ignored: an unwritable
        directory must degrade the audit trail, not stop the application from
        serving.
        """
        if not (self._enabled and self._to_file) or self._directory is None:
            return
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            path = self._directory / "actions.jsonl"
            handler = RotatingFileHandler(
                path,
                maxBytes=self._file_max_bytes,
                backupCount=self._file_backups,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            file_logger = logging.getLogger("stockpilot.actions")
            file_logger.setLevel(logging.INFO)
            # Own handler only: these lines are JSON records, not console text,
            # and must not be duplicated into the app's normal stdout logging.
            file_logger.propagate = False
            for existing in list(file_logger.handlers):
                file_logger.removeHandler(existing)
                existing.close()
            file_logger.addHandler(handler)
            self._file_logger = file_logger
            self._file_path = path
            logger.info("Action log writing to %s", path)
        except OSError as exc:
            logger.error("Could not open the action log file (%s) — file logging off.", exc)
            self._file_logger = None
            self._file_path = None

    def close_file(self) -> None:
        if self._file_logger is None:
            return
        for handler in list(self._file_logger.handlers):
            self._file_logger.removeHandler(handler)
            handler.close()
        self._file_logger = None
        self._file_path = None

    async def start_db_writer(self, repo: Any, retention_days: int) -> None:
        """Begin mirroring entries into the database.

        Called from the lifespan once the database is known to be reachable.
        """
        if not self._enabled or repo is None:
            return
        self._repo = repo
        self._retention_days = retention_days
        self._queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        # Remembered so record() can tell "I am on the loop that owns this
        # queue" from "I am on some other thread" (see record()).
        self._loop = asyncio.get_running_loop()
        self._worker = asyncio.create_task(self._drain_queue(), name="action_log_writer")

    async def stop_db_writer(self) -> None:
        """Flush what is queued and stop the worker.

        The worker is asked to stop with a sentinel rather than cancelled: a
        cancellation lands mid-batch and throws away the entries it had already
        taken off the queue — which is the tail of the log, the part a shutdown
        most needs to explain.
        """
        worker, self._worker = self._worker, None
        if worker is not None:
            try:
                if self._queue is not None:
                    self._queue.put_nowait(_SHUTDOWN)
                await asyncio.wait_for(worker, timeout=_STOP_TIMEOUT_SECONDS)
            except (asyncio.QueueFull, TimeoutError):
                # Queue jammed or the write is hanging — take the loss rather
                # than holding up the shutdown.
                worker.cancel()
                try:
                    await worker
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 — shutdown must not raise
                logger.exception("Action-log writer stopped with an error.")
        # One last synchronous flush so a shutdown does not lose the tail.
        if self._repo is not None and self._queue is not None:
            pending: list[ActionLogEntry] = []
            while not self._queue.empty():
                pending.append(self._queue.get_nowait())
            pending = [e for e in pending if e is not _SHUTDOWN]
            if pending:
                try:
                    await self._repo.insert_many(pending)
                except Exception:  # noqa: BLE001
                    logger.exception("Final action-log flush failed.")
        self._repo = None
        self._queue = None
        self._loop = None

    # ── Recording ─────────────────────────────────────────────────────────────

    def record(self, entry: ActionLogEntry) -> None:
        """Record one entry. Never raises, never blocks, safe from any thread."""
        if not self._enabled:
            return
        self.recorded_count += 1
        self._recent.append(entry)

        if self._file_logger is not None:
            try:
                self._file_logger.info(
                    json.dumps(entry.to_json_dict(), ensure_ascii=False, default=str)
                )
            except Exception:  # noqa: BLE001 — logging must not break the caller
                logger.exception("Failed to write an action-log line.")

        queue = self._queue
        if queue is None:
            return

        # Not every caller is on the event loop. The error tracker is attached
        # to the ROOT logger, so any logger.error() from a worker thread — the
        # market-data client runs yfinance in threads — lands here. An
        # asyncio.Queue is not thread-safe: put_nowait wakes a waiting getter
        # by completing a Future directly, and the drain worker is essentially
        # always parked in `await queue.get()`, so doing that off the loop
        # corrupts the loop's own state. Hand the work to the loop instead.
        loop = self._loop
        if loop is not None and not self._on_owning_loop(loop):
            try:
                loop.call_soon_threadsafe(self._enqueue, queue, entry)
            except RuntimeError:
                # The loop is closing or already closed — the file and the ring
                # buffer still hold the entry; only the database copy is lost.
                self.dropped_count += 1
            return

        self._enqueue(queue, entry)

    @staticmethod
    def _on_owning_loop(loop: asyncio.AbstractEventLoop) -> bool:
        """True when the caller is running on ``loop`` itself."""
        try:
            return asyncio.get_running_loop() is loop
        except RuntimeError:
            # No running loop at all: a plain worker thread.
            return False

    def _enqueue(self, queue: asyncio.Queue, entry: ActionLogEntry) -> None:
        """Put one entry on the writer's queue. Only ever runs on the loop."""
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            # Deliberate: the API stays fast and the file already has the
            # record. The counter makes the loss visible in the summary.
            self.dropped_count += 1

    def log_job(
        self,
        action: str,
        outcome: str,
        *,
        duration_ms: float | None = None,
        detail: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ActionLogEntry:
        """Convenience for background work (refresh, ingest, scheduler)."""
        entry = ActionLogEntry(
            action=action,
            kind="job",
            outcome=outcome,
            duration_ms=duration_ms,
            detail=detail,
        )
        if request_id is not None:
            entry.request_id = request_id
        self.record(entry)
        return entry

    # ── Reading back ──────────────────────────────────────────────────────────

    def recent(
        self,
        *,
        kind: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ActionLogEntry]:
        """Filtered view of the in-memory buffer, newest first.

        The fallback for ``GET /api/admin/logs`` when no database is
        configured — the app is designed to run stateless, and an audit trail
        that only exists with PostgreSQL would be missing exactly when the
        owner is running the app the simple way.
        """
        rows = [e for e in reversed(self._recent)]
        if kind:
            rows = [e for e in rows if e.kind == kind]
        if action:
            needle = action.lower()
            rows = [e for e in rows if needle in e.action.lower()]
        if outcome:
            rows = [e for e in rows if e.outcome == outcome]
        if since is not None:
            rows = [e for e in rows if e.started_at >= since]
        if until is not None:
            rows = [e for e in rows if e.started_at <= until]
        return rows

    # ── Background worker ─────────────────────────────────────────────────────

    async def _drain_queue(self) -> None:
        """Batch queued entries into the database; prune old rows periodically."""
        assert self._queue is not None
        next_prune = time.monotonic()
        while True:
            try:
                stopping = False
                batch: list[ActionLogEntry] = []
                first = await self._queue.get()
                if first is _SHUTDOWN:
                    stopping = True
                else:
                    batch.append(first)
                # Grab whatever else is already waiting, up to a batch, so a
                # burst of requests costs one INSERT rather than one each.
                deadline = time.monotonic() + _BATCH_WAIT_SECONDS
                while not stopping and len(batch) < _BATCH_MAX:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        nxt = await asyncio.wait_for(
                            self._queue.get(), timeout=remaining
                        )
                    except TimeoutError:
                        break
                    if nxt is _SHUTDOWN:
                        # Write what this batch already holds, then finish.
                        stopping = True
                        break
                    batch.append(nxt)

                if batch and self._repo is not None:
                    try:
                        await self._repo.insert_many(batch)
                        self.db_written_count += len(batch)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Could not write %d action-log rows to the database.",
                            len(batch),
                        )

                if self._retention_days > 0 and time.monotonic() >= next_prune:
                    next_prune = time.monotonic() + _PRUNE_INTERVAL_SECONDS
                    cutoff = datetime.now(tz=UTC) - timedelta(days=self._retention_days)
                    try:
                        deleted = await self._repo.prune(cutoff)
                        if deleted:
                            logger.info(
                                "Action log: pruned %d rows older than %s.",
                                deleted,
                                cutoff.date(),
                            )
                    except Exception:  # noqa: BLE001
                        logger.exception("Action-log prune failed.")

                if stopping:
                    return
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — the writer must never die
                logger.exception("Action-log writer error; continuing.")
                await asyncio.sleep(1.0)


# ── Middleware ────────────────────────────────────────────────────────────────


class ActionLogMiddleware(BaseHTTPMiddleware):
    """Records one entry per HTTP request.

    Preflight ``OPTIONS`` calls are skipped. This middleware is added last in
    ``main.py`` and Starlette builds its stack front-to-back, so it is the
    OUTERMOST layer and a preflight reaches it before CORS answers it — the
    skip has to be here rather than implied by the ordering. A preflight is the
    browser asking permission; logging it would double every recorded action
    while saying nothing about what the app actually did.

    Every response carries an ``X-Request-Id`` header holding the same id as
    the log line, so a screen the owner is looking at can be tied to its entry.
    """

    def __init__(
        self,
        app: ASGIApp,
        service: ActionLogService,
        error_tracker: Any | None = None,
    ) -> None:
        super().__init__(app)
        self._service = service
        # Optional: an endpoint that raised is recorded here with the route and
        # request id attached. The tracker would see the exception anyway (the
        # server logs it a moment later), but only as a bare traceback with no
        # idea which call produced it.
        self._error_tracker = error_tracker

    async def dispatch(self, request: Request, call_next) -> Response:
        service = self._service
        if (
            not service.enabled
            or request.method == "OPTIONS"
            or service.excludes(request.url.path)
        ):
            return await call_next(request)

        request_id = uuid.uuid4().hex[:12]
        # Make it reachable from the endpoint, so a job started by a request
        # can be logged under the same id as the request that started it.
        request.state.request_id = request_id
        started_at = datetime.now(tz=UTC)
        started = time.perf_counter()
        status_code: int | None = None
        error: str | None = None
        response_bytes: int | None = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            response_bytes = _content_length(response)
            response.headers["X-Request-Id"] = request_id
            return response
        except Exception as exc:  # noqa: BLE001 — record, then re-raise unchanged
            # An endpoint that blew up is exactly the event the log exists for,
            # and FastAPI's own handler turns it into a bare 500 that says
            # nothing. Record what it was, then let it propagate untouched.
            status_code = 500
            error = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR]
            if self._error_tracker is not None:
                self._error_tracker.record_exception(
                    exc,
                    source="api",
                    context={
                        "requestId": request_id,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            # The matched route template ("/api/stocks/{ticker}/signals") is
            # the action; the concrete path is kept separately. Grouping by
            # template is what makes "which actions ran today" answerable.
            route = request.scope.get("route")
            action = getattr(route, "path", None) or request.url.path
            user_agent = request.headers.get("user-agent")
            service.record(
                ActionLogEntry(
                    action=action,
                    kind="request",
                    outcome=(
                        OUTCOME_SERVER_ERROR
                        if error is not None
                        else outcome_for_status(status_code or 500)
                    ),
                    started_at=started_at,
                    request_id=request_id,
                    duration_ms=duration_ms,
                    method=request.method,
                    path=request.url.path,
                    query=sanitize_query(request.url.query),
                    status_code=status_code,
                    response_bytes=response_bytes,
                    client_ip=_client_ip(request),
                    user_agent=user_agent[:_MAX_USER_AGENT] if user_agent else None,
                    detail={"error": error} if error is not None else None,
                )
            )
