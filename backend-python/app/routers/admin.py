"""Admin endpoints — the app watching itself.

    GET /api/admin/logs          — recorded actions, filtered and paginated
    GET /api/admin/logs/summary  — is the log healthy, and did the jobs finish?
    GET /api/admin/errors        — what has been failing, grouped and counted
    GET /api/admin/health        — did the refresh run, is the data current?

Rows come from the ``action_logs`` table when a database is configured, and
otherwise from the in-process ring buffer, so the audit trail is readable in
both of the app's supported modes. ``source`` in the payload says which.

**Access.** These endpoints expose stack traces, file paths and caller IP
addresses. When ``STOCKPILOT_ADMIN_TOKEN`` is set they require a matching
``X-Admin-Token`` header; when it is not they are open, which is right for a
laptop and wrong for a public deployment — so the health payload reports
``protected: false`` and the UI says so out loud.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app import __version__
from app.config import settings
from app.db.action_log_repository import ActionLogRepository
from app.db.health_repository import DataHealthRepository, StoredDataStats
from app.db.models import ActionLogRow
from app.dependencies import (
    APP_STARTED_AT,
    get_action_log,
    get_action_log_repository,
    get_data_health_repository,
    get_error_tracker,
    get_gpw_company_service,
    get_refresh_service,
    get_scheduler,
)
from app.models import (
    ActionLogItem,
    ActionLogResponse,
    ActionLogSummaryResponse,
    ErrorGroupItem,
    ErrorListResponse,
    LogHealth,
    SystemHealthResponse,
)
from app.services.action_log import KIND_ERROR, KIND_JOB, ActionLogEntry, ActionLogService
from app.services.error_tracker import ErrorGroup, ErrorTracker
from app.services.gpw_company_service import GpwCompanyService
from app.services.system_health import (
    JobRecord,
    evaluate_data,
    evaluate_errors,
    evaluate_ingest,
    overall_status,
)

logger = logging.getLogger(__name__)


async def require_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Gate every admin endpoint behind the configured token, if there is one.

    No token configured means open access — the local default, where the API
    is only reachable from the same machine. Set ``STOCKPILOT_ADMIN_TOKEN`` in
    production: this router hands out tracebacks and visitor IP addresses.

    ``compare_digest`` rather than ``==`` so a wrong guess takes the same time
    as a right one, which is what stops the check from leaking the token one
    character at a time.
    """
    expected = settings.admin_token
    if not expected:
        return
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required.",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )


router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)

_WARSAW = ZoneInfo("Europe/Warsaw")

# Job entries are the operationally interesting ones; the summary lists the
# newest of each. Small on purpose — this is a status read, not a report.
_LAST_JOBS_MAX = 12


def _item_from_entry(entry: ActionLogEntry) -> ActionLogItem:
    return ActionLogItem(
        timestamp=entry.started_at.astimezone(UTC).isoformat(),
        timestamp_local=entry.started_at.astimezone(_WARSAW).isoformat(),
        request_id=entry.request_id,
        kind=entry.kind,
        action=entry.action,
        outcome=entry.outcome,
        duration_ms=(
            round(entry.duration_ms, 1) if entry.duration_ms is not None else None
        ),
        method=entry.method,
        path=entry.path,
        query=entry.query,
        status_code=entry.status_code,
        response_bytes=entry.response_bytes,
        client_ip=entry.client_ip,
        user_agent=entry.user_agent,
        detail=entry.detail,
    )


def _item_from_row(row: ActionLogRow) -> ActionLogItem:
    # Rows written before a timezone-aware driver would be naive; treat a naive
    # timestamp as UTC (which is what the writer always stores) rather than
    # letting astimezone() reinterpret it in the server's local zone.
    started = row.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return ActionLogItem(
        timestamp=started.astimezone(UTC).isoformat(),
        timestamp_local=started.astimezone(_WARSAW).isoformat(),
        request_id=row.request_id,
        kind=row.kind,
        action=row.action,
        outcome=row.outcome,
        duration_ms=(round(row.duration_ms, 1) if row.duration_ms is not None else None),
        method=row.method,
        path=row.path,
        query=row.query,
        status_code=row.status_code,
        response_bytes=row.response_bytes,
        client_ip=row.client_ip,
        user_agent=row.user_agent,
        detail=row.detail,
    )


@router.get(
    "/logs",
    response_model=ActionLogResponse,
    summary="Recorded API actions and background jobs",
)
async def get_action_logs(
    response: Response,
    log: Annotated[ActionLogService, Depends(get_action_log)],
    repo: Annotated[ActionLogRepository | None, Depends(get_action_log_repository)],
    kind: Annotated[str | None, Query(pattern="^(request|job|error)$")] = None,
    action: Annotated[str | None, Query(max_length=200)] = None,
    outcome: Annotated[str | None, Query(max_length=20)] = None,
    from_date: Annotated[datetime | None, Query(alias="fromDate")] = None,
    to_date: Annotated[datetime | None, Query(alias="toDate")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, alias="pageSize")] = 50,
) -> ActionLogResponse:
    """Return recorded actions, newest first.

    ``action`` is a case-insensitive substring match on the route template or
    job name (``stocks/ranking``, ``job.refresh``), so one screen's traffic can
    be pulled out without knowing the exact path.
    """
    since = _as_utc(from_date)
    until = _as_utc(to_date)
    offset = (page - 1) * page_size

    if repo is not None:
        try:
            rows, total = await repo.query(
                kind=kind,
                action=action,
                outcome=outcome,
                since=since,
                until=until,
                limit=page_size,
                offset=offset,
            )
            response.headers["X-Total-Count"] = str(total)
            return ActionLogResponse(
                source="database",
                total_count=total,
                page=page,
                page_size=page_size,
                items=[_item_from_row(r) for r in rows],
            )
        except Exception:  # noqa: BLE001 — fall back rather than 500 the admin page
            logger.exception("Reading action logs from the database failed.")

    entries = log.recent(
        kind=kind, action=action, outcome=outcome, since=since, until=until
    )
    total = len(entries)
    response.headers["X-Total-Count"] = str(total)
    return ActionLogResponse(
        source="memory",
        total_count=total,
        page=page,
        page_size=page_size,
        items=[_item_from_entry(e) for e in entries[offset : offset + page_size]],
    )


@router.get(
    "/logs/summary",
    response_model=ActionLogSummaryResponse,
    summary="Action-log health and the last outcome of every background job",
)
async def get_action_log_summary(
    log: Annotated[ActionLogService, Depends(get_action_log)],
    repo: Annotated[ActionLogRepository | None, Depends(get_action_log_repository)],
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> ActionLogSummaryResponse:
    """Where the log is written, how much it has recorded, and how jobs ended.

    The last-jobs list is the point of this endpoint: a nightly ingest that
    fails leaves a ``failed`` entry here, which is the difference between
    noticing the next morning and noticing when the data looks wrong weeks
    later.
    """
    since = datetime.now(tz=UTC) - timedelta(hours=hours)
    source = "memory"
    window: list[ActionLogItem] = []

    if repo is not None:
        try:
            rows, _total = await repo.query(since=since, limit=5000, offset=0)
            window = [_item_from_row(r) for r in rows]
            source = "database"
        except Exception:  # noqa: BLE001
            logger.exception("Reading the action-log summary from the database failed.")

    if source == "memory":
        window = [_item_from_entry(e) for e in log.recent(since=since)]

    by_action: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    last_jobs: dict[str, ActionLogItem] = {}
    for item in window:
        by_action[item.action] = by_action.get(item.action, 0) + 1
        by_outcome[item.outcome] = by_outcome.get(item.outcome, 0) + 1
        if item.kind == "job" and item.action not in last_jobs:
            # `window` is newest-first, so the first sighting is the latest run.
            last_jobs[item.action] = item

    return ActionLogSummaryResponse(
        as_of=datetime.now(tz=UTC).isoformat(),
        source=source,
        enabled=log.enabled,
        file_path=str(log.file_path) if log.file_path else None,
        db_active=log.db_active,
        retention_days=settings.action_log_retention_days,
        recorded_count=log.recorded_count,
        db_written_count=log.db_written_count,
        dropped_count=log.dropped_count,
        window_hours=hours,
        total_in_window=len(window),
        by_action=dict(sorted(by_action.items(), key=lambda kv: -kv[1])),
        by_outcome=by_outcome,
        last_jobs=list(last_jobs.values())[:_LAST_JOBS_MAX],
    )


def _as_utc(value: datetime | None) -> datetime | None:
    """Treat a date/time given without a zone as UTC.

    ``?fromDate=2026-09-08`` is the common case from a browser; without this it
    would compare a naive value against timezone-aware timestamps and raise.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ── Errors ────────────────────────────────────────────────────────────────────

# How far back the health check counts errors, and how many of the loudest
# groups it carries inline so the screen has something to show without a
# second request.
_ERROR_WINDOW_HOURS = 24
_TOP_ERRORS_IN_HEALTH = 3
# Stored error entries scanned when rebuilding groups from the database. Errors
# are rare by nature; this is a ceiling, not an expectation.
_MAX_ERROR_ROWS = 2000
# How far back the health check looks for job entries. Long enough that a
# server switched off over a long weekend still shows its last real run.
_JOB_LOOKBACK_DAYS = 14
_MAX_JOB_ROWS = 500


def _group_item(group: ErrorGroup) -> ErrorGroupItem:
    return ErrorGroupItem(
        fingerprint=group.fingerprint,
        error_type=group.error_type,
        message=group.message,
        last_message=group.last_message,
        where=group.where,
        source=group.source,
        count=group.count,
        first_seen=group.first_seen.astimezone(UTC).isoformat(),
        last_seen=group.last_seen.astimezone(UTC).isoformat(),
        last_seen_local=group.last_seen.astimezone(_WARSAW).isoformat(),
        traceback=group.traceback,
        context=group.context,
    )


def _groups_from_rows(rows: list[ActionLogRow]) -> list[ErrorGroupItem]:
    """Rebuild error groups from stored ``kind="error"`` entries.

    The rows arrive newest first, so the first sighting of a fingerprint is its
    most recent one. Each row carries an ``occurrences`` count — the log writes
    at most one row per group per minute — so summing those, rather than
    counting rows, is what keeps a throttled burst honest.
    """
    groups: dict[str, ErrorGroupItem] = {}
    counts: dict[str, int] = {}
    firsts: dict[str, datetime] = {}
    for row in rows:
        detail = row.detail or {}
        fingerprint = str(detail.get("fingerprint") or row.action)
        started = row.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        occurrences = detail.get("occurrences")
        counts[fingerprint] = counts.get(fingerprint, 0) + (
            int(occurrences) if isinstance(occurrences, int) and occurrences > 0 else 1
        )
        firsts[fingerprint] = min(firsts.get(fingerprint, started), started)
        if fingerprint in groups:
            continue
        groups[fingerprint] = ErrorGroupItem(
            fingerprint=fingerprint,
            error_type=str(detail.get("type") or row.action.removeprefix("error.")),
            message=str(detail.get("message") or ""),
            last_message=detail.get("lastMessage"),
            where=detail.get("where"),
            source=detail.get("source"),
            count=0,
            first_seen=started.isoformat(),
            last_seen=started.isoformat(),
            last_seen_local=started.astimezone(_WARSAW).isoformat(),
            traceback=detail.get("traceback"),
            context=detail.get("context"),
        )
    # Counts and first-seen are only complete once every row has been read.
    return [
        item.model_copy(
            update={
                "count": counts[fingerprint],
                "first_seen": firsts[fingerprint].astimezone(UTC).isoformat(),
            }
        )
        for fingerprint, item in groups.items()
    ]


async def _error_groups(
    tracker: ErrorTracker,
    repo: ActionLogRepository | None,
    *,
    since: datetime,
) -> tuple[list[ErrorGroupItem], str]:
    """Grouped errors in the window, from the database when there is one.

    The stored entries reach back past restarts, which the in-process table
    cannot. When the database holds nothing (no rows yet, mirroring switched
    off, or a failed read) the live table answers instead — an error screen
    that goes blank because persistence is misconfigured would be worse than
    one that admits it is only showing this process.
    """
    if repo is not None:
        try:
            rows, _total = await repo.query(
                kind=KIND_ERROR, since=since, limit=_MAX_ERROR_ROWS, offset=0
            )
            if rows:
                return _with_pending(_groups_from_rows(rows), tracker), "database"
        except Exception:  # noqa: BLE001 — fall back rather than 500 the screen
            logger.exception("Reading stored errors from the database failed.")
    return [_group_item(g) for g in tracker.groups(since=since)], "memory"


def _with_pending(
    items: list[ErrorGroupItem], tracker: ErrorTracker
) -> list[ErrorGroupItem]:
    """Add the hits the log has not written down yet.

    The mirror into the action log is throttled to one entry per group per
    minute, and the entry counts the hits it stands for — but the ones still
    waiting for the next entry are only in memory. Without adding them, a burst
    of 290 identical failures would be shown as the single hit that was written
    first, which is precisely the number the grouping exists to get right.
    """
    merged: list[ErrorGroupItem] = []
    for item in items:
        live = tracker.get(item.fingerprint)
        pending = live.pending if live is not None else 0
        merged.append(
            item.model_copy(update={"count": item.count + pending}) if pending else item
        )
    return merged


@router.get(
    "/errors",
    response_model=ErrorListResponse,
    summary="Recent errors, grouped by what went wrong",
)
async def get_errors(
    tracker: Annotated[ErrorTracker, Depends(get_error_tracker)],
    repo: Annotated[ActionLogRepository | None, Depends(get_action_log_repository)],
    hours: Annotated[int, Query(ge=1, le=720)] = _ERROR_WINDOW_HOURS,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ErrorListResponse:
    """Return distinct problems, most recently seen first.

    Grouped, not listed: an ingest where 290 tickers fail is one problem seen
    290 times, and 290 rows would bury that instead of showing it.
    """
    since = datetime.now(tz=UTC) - timedelta(hours=hours)
    items, source = await _error_groups(tracker, repo, since=since)
    items.sort(key=lambda i: i.last_seen, reverse=True)
    return ErrorListResponse(
        as_of=datetime.now(tz=UTC).isoformat(),
        source=source,
        window_hours=hours,
        total_count=sum(i.count for i in items),
        group_count=len(items),
        tracked_since=tracker.started_at.astimezone(UTC).isoformat(),
        items=items[:limit],
    )


# ── System health ─────────────────────────────────────────────────────────────


async def _job_records(
    log: ActionLogService,
    repo: ActionLogRepository | None,
    *,
    since: datetime,
) -> list[JobRecord]:
    """Recorded background jobs, newest first, from whichever source has them."""
    if repo is not None:
        try:
            rows, _total = await repo.query(
                kind=KIND_JOB, since=since, limit=_MAX_JOB_ROWS, offset=0
            )
            if rows:
                return [
                    JobRecord(
                        action=row.action,
                        outcome=row.outcome,
                        started_at=(
                            row.started_at
                            if row.started_at.tzinfo is not None
                            else row.started_at.replace(tzinfo=UTC)
                        ),
                        duration_ms=row.duration_ms,
                        detail=row.detail,
                    )
                    for row in rows
                ]
        except Exception:  # noqa: BLE001
            logger.exception("Reading job history from the database failed.")
    return [
        JobRecord(
            action=e.action,
            outcome=e.outcome,
            started_at=e.started_at,
            duration_ms=e.duration_ms,
            detail=e.detail,
        )
        for e in log.recent(kind=KIND_JOB, since=since)
    ]


def _next_scheduled_run(scheduler: Any | None) -> datetime | None:
    """When the nightly job will next fire, asked of the scheduler itself."""
    if scheduler is None:
        return None
    try:
        job = scheduler.get_job("daily_ingest")
        return getattr(job, "next_run_time", None) if job is not None else None
    except Exception:  # noqa: BLE001 — a status read must not fail on this
        logger.debug("Could not read the next scheduled run time.")
        return None


async def _stored_data_stats(
    repo: DataHealthRepository | None,
) -> tuple[StoredDataStats | None, bool]:
    """(stats, read_failed) — a failed read is reported, never silently empty."""
    if repo is None:
        return None, False
    try:
        return await repo.stats(), False
    except Exception:  # noqa: BLE001
        logger.exception("Reading stored-data statistics failed.")
        return None, True


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="Did the refresh run, is the data current, what is failing?",
)
async def get_system_health(
    log: Annotated[ActionLogService, Depends(get_action_log)],
    repo: Annotated[ActionLogRepository | None, Depends(get_action_log_repository)],
    tracker: Annotated[ErrorTracker, Depends(get_error_tracker)],
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    health_repo: Annotated[
        DataHealthRepository | None, Depends(get_data_health_repository)
    ] = None,
    refresh: Annotated[Any, Depends(get_refresh_service)] = None,
    scheduler: Annotated[Any, Depends(get_scheduler)] = None,
) -> SystemHealthResponse:
    """The operational read behind the System page.

    Answers, in one request, the question the app could not answer before it
    started keeping a record of itself: **did the nightly job run, and did it
    work?**
    """
    now = datetime.now(tz=UTC)
    jobs = await _job_records(log, repo, since=now - timedelta(days=_JOB_LOOKBACK_DAYS))
    stats, read_failed = await _stored_data_stats(health_repo)

    ingest = evaluate_ingest(
        jobs,
        now=now,
        running=bool(refresh is not None and refresh.is_running),
        # The scheduler only exists when a database is configured, so its
        # absence is a deployment mode, not a fault.
        scheduler_active=scheduler is not None and getattr(scheduler, "running", False),
        next_run_at=_next_scheduled_run(scheduler),
        hour=settings.ingest_hour,
        minute=settings.ingest_minute,
        last_error=getattr(refresh, "last_error", None),
    )
    data = evaluate_data(
        stats,
        tickers_tracked=len(companies.get_companies()),
        db_enabled=settings.db_enabled,
        today=datetime.now(_WARSAW).date(),
        read_failed=read_failed,
        refresh_running=ingest.running,
    )

    error_since = now - timedelta(hours=_ERROR_WINDOW_HOURS)
    error_items, _error_source = await _error_groups(tracker, repo, since=error_since)
    error_items.sort(key=lambda i: i.count, reverse=True)
    errors = evaluate_errors(
        total_count=sum(i.count for i in error_items),
        group_count=len(error_items),
        window_hours=_ERROR_WINDOW_HOURS,
        top=error_items[:_TOP_ERRORS_IN_HEALTH],
    )

    return SystemHealthResponse(
        as_of=now.isoformat(),
        as_of_local=now.astimezone(_WARSAW).isoformat(),
        status=overall_status(ingest, data, errors),
        version=__version__,
        uptime_seconds=round((now - APP_STARTED_AT).total_seconds(), 1),
        protected=bool(settings.admin_token),
        ingest=ingest,
        data=data,
        errors=errors,
        log=LogHealth(
            enabled=log.enabled,
            file_path=str(log.file_path) if log.file_path else None,
            db_active=log.db_active,
            recorded_count=log.recorded_count,
            db_written_count=log.db_written_count,
            dropped_count=log.dropped_count,
        ),
    )
