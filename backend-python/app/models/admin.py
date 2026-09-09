"""API models for the admin endpoints (the action log / audit trail).

Same convention as the market-data models: snake_case in Python, camelCase in
the JSON the frontend sees.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    """Base that serialises field names to camelCase for the frontend."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class ActionLogItem(_CamelModel):
    """One recorded action — an API call or a background job."""

    # ISO-8601 UTC, e.g. "2026-09-08T16:04:11.482000+00:00".
    timestamp: str
    # The same instant in Europe/Warsaw, because that is the clock the GPW
    # session and the nightly job run on.
    timestamp_local: str
    request_id: str
    # "request" | "job".
    kind: str
    # Route template ("/api/stocks/{ticker}/signals") or job name ("job.refresh").
    action: str
    # ok | client_error | server_error | started | finished | failed | skipped.
    outcome: str
    duration_ms: float | None = None
    method: str | None = None
    path: str | None = None
    query: str | None = None
    status_code: int | None = None
    response_bytes: int | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    # Job counters, or the error text of a failed action.
    detail: dict[str, Any] | None = None


class ActionLogResponse(_CamelModel):
    """Response payload for ``GET /api/admin/logs``."""

    # "database" when the rows came from the action_logs table, "memory" when
    # they came from the in-process ring buffer (no database configured).
    source: str
    total_count: int
    page: int
    page_size: int
    items: list[ActionLogItem]


class ActionLogSummaryResponse(_CamelModel):
    """Response payload for ``GET /api/admin/logs/summary``.

    The operational read: is the log itself healthy, and did the last refresh
    and nightly ingest actually finish?
    """

    as_of: str
    source: str
    enabled: bool
    # Absolute path of the rotating JSON-lines file, or None when file logging
    # is switched off.
    file_path: str | None
    db_active: bool
    retention_days: int
    # Counters since the process started.
    recorded_count: int
    db_written_count: int
    dropped_count: int
    # Window the counts below cover, in hours.
    window_hours: int
    total_in_window: int
    # action → count, biggest first.
    by_action: dict[str, int]
    # outcome → count.
    by_outcome: dict[str, int]
    # The most recent entry per job name, so a silent nightly failure shows up.
    last_jobs: list[ActionLogItem]


# ── Error tracking ────────────────────────────────────────────────────────────


class ErrorGroupItem(_CamelModel):
    """One *kind* of error, with how often it has happened.

    Errors are grouped rather than listed: a nightly ingest where 290 tickers
    fail is one problem seen 290 times, and 290 rows would hide that.
    """

    fingerprint: str
    error_type: str
    # The message template ("Ingest error for %s: %s") — the group's identity.
    message: str
    # The newest fully substituted message, values and all.
    last_message: str | None = None
    # Source line it came from, "services/ranking_service.py:210 in scan_one".
    where: str | None = None
    # Logger or subsystem that reported it.
    source: str | None = None
    count: int
    first_seen: str
    last_seen: str
    last_seen_local: str
    traceback: str | None = None
    # Whatever was known at the time: route, request id, job, ticker.
    context: dict[str, Any] | None = None


class ErrorListResponse(_CamelModel):
    """Response payload for ``GET /api/admin/errors``."""

    as_of: str
    # "database" when the groups were rebuilt from stored error entries,
    # "memory" when they come from the live in-process table.
    source: str
    window_hours: int
    # Occurrences in the window, and how many distinct problems they are.
    total_count: int
    group_count: int
    # When the in-process table started counting (a restart resets it). The
    # database source reaches further back than this.
    tracked_since: str | None = None
    items: list[ErrorGroupItem]


# ── System health ─────────────────────────────────────────────────────────────


class IngestHealth(_CamelModel):
    """Did the data refresh run, and did it work?

    The question the whole screen exists for. A background job accepted with a
    202 can never report its own outcome over HTTP, so "the nightly job ran"
    was previously unanswerable without reading the server's console.
    """

    # ok | running | stale | failed | never
    status: str
    # One plain-language line, ready to show.
    summary: str
    running: bool
    last_run_at: str | None = None
    last_run_local: str | None = None
    last_outcome: str | None = None
    last_trigger: str | None = None
    duration_ms: float | None = None
    age_hours: float | None = None
    # Last run that actually finished (as opposed to failed).
    last_success_at: str | None = None
    last_success_local: str | None = None
    last_error: str | None = None
    # Counters from the last ingest inside that refresh.
    stocks_ranked: int | None = None
    fetched: int | None = None
    skipped: int | None = None
    failed: int | None = None
    bars_written: int | None = None
    # The scheduled 18:00 Warsaw run this check measures against, and whether
    # a run has happened since it came due.
    expected_at: str | None = None
    expected_local: str | None = None
    ran_since_expected: bool | None = None
    next_run_at: str | None = None
    next_run_local: str | None = None
    # False when no scheduler is running at all (the app has no database, so
    # the nightly job was never started) — otherwise "no run last night" would
    # look like a failure when it is a configuration.
    scheduler_active: bool
    schedule: str


class DataHealth(_CamelModel):
    """How fresh and how complete the stored market data is."""

    # ok | updating | stale | empty | disabled | error
    status: str
    summary: str
    db_enabled: bool
    latest_bar_date: str | None = None
    earliest_bar_date: str | None = None
    latest_snapshot_date: str | None = None
    # Calendar days between the newest stored bar and today.
    session_age_days: int | None = None
    tickers_tracked: int
    tickers_with_data: int | None = None
    # Tickers whose newest bar is the newest bar in the table, and those behind.
    tickers_current: int | None = None
    tickers_behind: int | None = None
    coverage_pct: float | None = None
    bar_count: int | None = None


class ErrorHealth(_CamelModel):
    """Errors seen recently, summarised."""

    # ok | warn | error
    status: str
    summary: str
    window_hours: int
    total_count: int
    group_count: int
    # The loudest few, so the health payload alone can show something useful.
    top: list[ErrorGroupItem]


class LogHealth(_CamelModel):
    """Is the audit trail itself working?"""

    enabled: bool
    file_path: str | None = None
    db_active: bool
    recorded_count: int
    db_written_count: int
    # Entries dropped because the database queue was full — should stay 0.
    dropped_count: int


class SystemHealthResponse(_CamelModel):
    """Response payload for ``GET /api/admin/health``.

    One read that answers "is this thing working?": did the refresh run, is
    the data current, what has been failing, and is the log recording.
    """

    as_of: str
    as_of_local: str
    # Worst of the sections below: ok | warn | error.
    status: str
    version: str
    uptime_seconds: float
    # False when the admin endpoints are reachable by anyone (no admin token
    # configured) — the UI shows a warning, because this screen carries
    # tracebacks and caller IP addresses.
    protected: bool
    ingest: IngestHealth
    data: DataHealth
    errors: ErrorHealth
    log: LogHealth
