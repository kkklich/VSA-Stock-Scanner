"""Error tracking — every failure the app hits, grouped and countable.

The action log (``app/services/action_log.py``) answers *what the app did*.
This answers the next question: *what went wrong, how often, and where*. Before
it, an error existed only as a console line: gone on restart, impossible to
count, and invisible to anyone not watching the terminal at that second.

How it works
------------
Nothing calls this from a hundred places. An ``ErrorTrackingHandler`` is
attached to the root logger, so **every** ``logger.error(...)`` /
``logger.exception(...)`` already written anywhere in the app becomes a tracked
error — including the ones that never reach an HTTP response at all (a single
ticker failing mid-scan, a database write that fell over inside a background
job). Callers that have useful context can also record explicitly.

Errors are **grouped**, not listed one by one. A nightly ingest where 290
tickers fail is one problem seen 290 times, and a screen that shows it as 290
rows hides that fact rather than showing it. The fingerprint is the error's
type, the app source line it came from, and the message *template* (before
``%s`` substitution), so the same fault always lands in the same group.

Where the groups live
---------------------
* **In memory** — the live table, with exact counts since the process started.
* **In the action log** — each group's occurrences are also written as
  ``kind="error"`` entries, which means they inherit the JSON-lines file, the
  ``action_logs`` table, the retention prune and the admin API for free. Those
  writes are throttled per group (at most one entry per
  ``THROTTLE_SECONDS``); the entry carries an ``occurrences`` count of how many
  hits it stands for, so nothing is lost by throttling — a burst costs one row
  instead of 290, and still adds 290 to the total.

This is deliberately local: no Sentry, no external service, no API key (the
same rule the AI-insight engine follows). What it gives up is paging a human at
03:00; what it keeps is that the owner can open one page and see it.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import traceback as tb_module
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The app package root — used to pick the most relevant traceback frame ("our"
# code) rather than the deepest one, which is usually inside a library.
_APP_ROOT = Path(__file__).resolve().parents[1]

# How many distinct groups are kept. Far more than a healthy app produces; when
# it is exceeded the least-recently-seen group is dropped, so a flood of unique
# errors cannot grow the process's memory without bound.
MAX_GROUPS = 200

# At most one action-log entry per group per this many seconds. The in-memory
# count is always exact — only the persisted rows are throttled.
THROTTLE_SECONDS = 60.0

# Length caps: an error record is a signpost, not a data dump.
_MAX_MESSAGE = 500
_MAX_TRACEBACK = 4000
_MAX_WHERE = 200

# Loggers whose output is never tracked. Recording an error raised *by the
# recording machinery* would be a loop; the action log's own failures show up
# in the log summary's counters instead.
_IGNORED_LOGGERS = ("stockpilot.actions", __name__)

# Digits carry the variable part of most messages ("failed for 3 of 290",
# "id=91744"), so two hits of the same fault differ only there. Collapsing them
# is what makes the fingerprint group them together.
_DIGITS_RE = re.compile(r"\d+")


def _normalize(message: str) -> str:
    """Reduce a message to its shape, for grouping."""
    return _DIGITS_RE.sub("#", message).strip()[:200]


def fingerprint_of(error_type: str, where: str | None, message: str) -> str:
    """Stable short id for one *kind* of error.

    Deliberately excludes the values in the message: "Ingest error for KGH"
    and "Ingest error for PKN" are one problem, not two.
    """
    raw = f"{error_type}|{where or ''}|{_normalize(message)}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:12]


def _app_frame(exc: BaseException) -> str | None:
    """The deepest traceback frame that belongs to this application.

    A ``KeyError`` raised three libraries deep is reported at the last line of
    *our* code that led there, which is the line someone can actually fix.
    """
    if exc.__traceback__ is None:
        return None
    frames = tb_module.extract_tb(exc.__traceback__)
    best: str | None = None
    for frame in frames:
        try:
            path = Path(frame.filename).resolve()
            inside = path.is_relative_to(_APP_ROOT)
        except (OSError, ValueError):  # pragma: no cover — exotic filenames
            inside = False
        if inside:
            rel = path.relative_to(_APP_ROOT)
            best = f"{rel.as_posix()}:{frame.lineno} in {frame.name}"
    if best is None and frames:
        # Nothing of ours in the traceback (a failure inside a library task).
        # Fall back to the deepest frame so the group still points somewhere.
        last = frames[-1]
        best = f"{Path(last.filename).name}:{last.lineno} in {last.name}"
    return best[:_MAX_WHERE] if best else None


@dataclass(slots=True)
class ErrorGroup:
    """One *kind* of error and everything seen about it."""

    fingerprint: str
    error_type: str
    # The message template when there is one ("Ingest error for %s: %s"), so a
    # group reads as the fault rather than as its latest victim.
    message: str
    # The most recent fully formatted message, values and all.
    last_message: str
    where: str | None
    source: str | None
    count: int
    first_seen: datetime
    last_seen: datetime
    traceback: str | None = None
    # Whatever the caller knew at the time: ticker, job, route, request id.
    context: dict[str, Any] | None = None
    # Occurrences not yet written to the action log (see THROTTLE_SECONDS).
    pending: int = 0
    last_written: float = field(default=0.0, repr=False)


class ErrorTracker:
    """Groups errors, counts them, and mirrors them into the action log.

    One instance per process (``app/dependencies.py``). Every method is
    non-raising by contract: error tracking that can itself break a request
    would be worse than none.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        action_log: Any | None = None,
        max_groups: int = MAX_GROUPS,
        throttle_seconds: float = THROTTLE_SECONDS,
    ) -> None:
        self._enabled = enabled
        self._action_log = action_log
        self._max_groups = max(1, max_groups)
        self._throttle = throttle_seconds
        # Ordered by recency of last sighting: the oldest is evicted first.
        self._groups: OrderedDict[str, ErrorGroup] = OrderedDict()
        # Not every caller is on the event loop: the market-data client runs
        # yfinance in worker threads, so two failures can be recorded at once
        # and the read-modify-write on a group would race.
        self._lock = threading.Lock()
        self.total_count = 0
        self.started_at = datetime.now(tz=UTC)

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_exception(
        self,
        exc: BaseException,
        *,
        source: str | None = None,
        context: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> ErrorGroup | None:
        """Track one raised exception, with its traceback.

        The same exception object is recorded once even if it is logged again
        further up the stack (the middleware records it, then Starlette's own
        handler logs it): a mark is left on the exception itself, so one
        failure is counted once rather than once per observer.
        """
        if not self._enabled:
            return None
        try:
            if getattr(exc, "_stockpilot_tracked", False):
                return None
            try:
                exc._stockpilot_tracked = True  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — exotic exceptions reject attributes
                pass

            where = _app_frame(exc)
            text = message or str(exc) or exc.__class__.__name__
            trace = "".join(
                tb_module.format_exception(type(exc), exc, exc.__traceback__)
            )
            return self._record(
                error_type=type(exc).__name__,
                message=text,
                last_message=text,
                where=where,
                source=source,
                traceback_text=trace,
                context=context,
            )
        except Exception:  # noqa: BLE001 — tracking must never raise
            return None

    def record_message(
        self,
        message: str,
        *,
        error_type: str = "Error",
        source: str | None = None,
        template: str | None = None,
        where: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ErrorGroup | None:
        """Track an error that was reported without an exception object.

        ``template`` is the un-substituted logging format string when one is
        available; grouping on it is what collapses "Ingest error for KGH",
        "…for PKN" and 288 others into a single countable group.
        """
        if not self._enabled:
            return None
        try:
            return self._record(
                error_type=error_type,
                message=template or message,
                last_message=message,
                where=where,
                source=source,
                traceback_text=None,
                context=context,
            )
        except Exception:  # noqa: BLE001
            return None

    def _record(
        self,
        *,
        error_type: str,
        message: str,
        last_message: str,
        where: str | None,
        source: str | None,
        traceback_text: str | None,
        context: dict[str, Any] | None,
    ) -> ErrorGroup:
        now = datetime.now(tz=UTC)
        message = message[:_MAX_MESSAGE]
        last_message = last_message[:_MAX_MESSAGE]
        key = fingerprint_of(error_type, where, message)

        with self._lock:
            group = self._make_or_update(
                key=key,
                error_type=error_type,
                message=message,
                last_message=last_message,
                where=where,
                source=source,
                traceback_text=traceback_text,
                context=context,
                now=now,
            )
        self._maybe_write(group)
        return group

    def _make_or_update(
        self,
        *,
        key: str,
        error_type: str,
        message: str,
        last_message: str,
        where: str | None,
        source: str | None,
        traceback_text: str | None,
        context: dict[str, Any] | None,
        now: datetime,
    ) -> ErrorGroup:
        """Create or bump one group. Called under the lock."""
        self.total_count += 1
        group = self._groups.get(key)
        if group is None:
            group = ErrorGroup(
                fingerprint=key,
                error_type=error_type,
                message=message,
                last_message=last_message,
                where=where,
                source=source,
                count=1,
                first_seen=now,
                last_seen=now,
                traceback=traceback_text[:_MAX_TRACEBACK] if traceback_text else None,
                context=context,
            )
            self._groups[key] = group
            while len(self._groups) > self._max_groups:
                self._groups.popitem(last=False)
        else:
            group.count += 1
            group.last_seen = now
            group.last_message = last_message
            if traceback_text:
                # Keep the newest traceback: it is the one matching last_seen.
                group.traceback = traceback_text[:_MAX_TRACEBACK]
            if context:
                group.context = context
            self._groups.move_to_end(key)
        return group

    def _maybe_write(self, group: ErrorGroup) -> None:
        """Mirror the group into the action log, at most once per throttle window."""
        if self._action_log is None:
            return
        now = time.monotonic()
        with self._lock:
            if group.last_written and now - group.last_written < self._throttle:
                group.pending += 1
                return
            occurrences = 1 + group.pending
            group.pending = 0
            group.last_written = now
        try:
            self._action_log.record(self._entry_for(group, occurrences))
        except Exception:  # noqa: BLE001 — never let logging break the caller
            pass

    def _entry_for(self, group: ErrorGroup, occurrences: int) -> Any:
        from app.services.action_log import KIND_ERROR, OUTCOME_FAILED, ActionLogEntry

        context = group.context or {}
        return ActionLogEntry(
            # Grouping by action in the log lines up with grouping by error
            # type on the errors screen, so the two views agree.
            action=f"error.{group.error_type}",
            kind=KIND_ERROR,
            outcome=OUTCOME_FAILED,
            started_at=group.last_seen,
            path=context.get("path"),
            request_id=context.get("requestId") or uuid.uuid4().hex[:12],
            detail={
                "fingerprint": group.fingerprint,
                "type": group.error_type,
                "message": group.message,
                "lastMessage": group.last_message,
                "where": group.where,
                "source": group.source,
                # How many hits this one entry stands for, so a throttled burst
                # is still counted correctly when the rows are read back.
                "occurrences": occurrences,
                "traceback": group.traceback,
                "context": context or None,
            },
        )

    # ── Reading back ──────────────────────────────────────────────────────────

    def groups(self, *, since: datetime | None = None) -> list[ErrorGroup]:
        """Groups, most recently seen first."""
        with self._lock:
            rows = list(reversed(self._groups.values()))
        if since is not None:
            rows = [g for g in rows if g.last_seen >= since]
        return rows

    def get(self, fingerprint: str) -> ErrorGroup | None:
        return self._groups.get(fingerprint)

    def count_since(self, since: datetime) -> int:
        """Occurrences belonging to groups last seen within the window.

        An approximation on purpose: the tracker keeps counts per group, not a
        timestamped list of every hit, because the question it answers is "is
        this happening now, and how much" — the action log holds the timeline.

        Takes the lock like every other reader: a failure recorded from a
        worker thread can insert or evict a fingerprint, and iterating the
        group table while that happens raises "OrderedDict mutated during
        iteration". Snapshot first, then add up outside the lock.
        """
        with self._lock:
            rows = list(self._groups.values())
        return sum(g.count for g in rows if g.last_seen >= since)

    def clear(self) -> None:
        with self._lock:
            self._groups.clear()
            self.total_count = 0


# ── The logging bridge ────────────────────────────────────────────────────────


class ErrorTrackingHandler(logging.Handler):
    """Feeds every ERROR-level log record into the tracker.

    Attached to the root logger in the app lifespan. This is what makes the
    error screen complete without editing a hundred call sites: the app already
    logs its failures properly, and every one of those lines now also becomes a
    counted, grouped error.
    """

    def __init__(self, tracker: ErrorTracker, level: int = logging.ERROR) -> None:
        super().__init__(level=level)
        self._tracker = tracker
        # Guards against a loop: if handling a record raises and that raise is
        # itself logged, the second pass is dropped instead of recursing. Held
        # per thread, so a failure logged from a worker thread is not silently
        # swallowed because the main thread happens to be inside emit().
        self._state = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._state, "handling", False) or record.levelno < logging.ERROR:
            return
        if record.name.startswith(_IGNORED_LOGGERS):
            return
        self._state.handling = True
        try:
            context = {"logger": record.name}
            if record.exc_info and record.exc_info[1] is not None:
                self._tracker.record_exception(
                    record.exc_info[1],
                    source=record.name,
                    context=context,
                    message=record.getMessage(),
                )
            else:
                self._tracker.record_message(
                    record.getMessage(),
                    source=record.name,
                    # str() because a logger can be called with a non-string
                    # first argument; the template is only a grouping key.
                    template=str(record.msg),
                    where=f"{Path(record.pathname).name}:{record.lineno}",
                    context=context,
                )
        except Exception:  # noqa: BLE001 — a logging handler must never raise
            pass
        finally:
            self._state.handling = False
