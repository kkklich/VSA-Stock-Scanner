"""System health — "is this thing working?", answered from what was recorded.

The screen behind ``GET /api/admin/health`` exists to answer one question the
app could not answer before: **did last night's data refresh actually run?**
The nightly job is accepted, runs for minutes and reports to nobody; before the
action log it left no trace at all, and a run that quietly fetched nothing
looked exactly like a run that worked.

Three readings make up the answer:

* **Ingest** — the last ``job.refresh`` / ``job.ingest`` entries from the
  action log, measured against each scheduled nightly run (18:00 Warsaw for
  the GPW and Europe, 17:15 New York for the US). "Stale" means the run came
  due and nothing happened; "failed" means it ran and blew up.
* **Data** — what is actually in the database: the newest stored session, how
  many tracked companies have it, how far the history reaches. A refresh can
  report success and still leave the data a week old if the provider served
  nothing.
* **Errors** — what has been failing lately, from the error tracker.

Everything here is pure computation over values the caller has already
fetched, so it can be tested without a database, an HTTP client or a clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db.health_repository import MarketStoredStats, StoredDataStats
from app.models import DataHealth, ErrorHealth, IngestHealth, MarketDataHealth
from app.services.action_log import (
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
)

_WARSAW = ZoneInfo("Europe/Warsaw")

# How long after the scheduled time a run may be missing before the screen
# calls it stale. The job itself takes minutes (it fetches ~290 tickers), and
# APScheduler will still run a missed trigger up to an hour late, so anything
# under this is "not finished yet", not "did not happen".
_LATE_GRACE = timedelta(minutes=90)

# How old the newest stored session may be before the data counts as stale,
# counted in WEEKDAYS rather than calendar days.
#
# Calendar days cannot express this: the GPW is shut all weekend, so a Monday
# check against Friday's bar is already three days old with nothing wrong. Any
# tolerance wide enough for that is also wide enough to be wrong — a Friday
# and the following Monday are both public holidays several times a year on
# the GPW (1 and 3 May, the Corpus Christi bridge), which leaves Thursday as
# the newest session and makes it five calendar days old by Tuesday. That is a
# perfectly healthy database, and the old four-day rule called it stale and
# turned the whole screen amber.
#
# Counting weekdays makes both cases read correctly: the Monday check is one
# weekday and the double-holiday Tuesday check is three. Four is the tolerance
# because the GPW's longest genuine break is the Christmas cluster (24, 25 and
# 26 December all closed), which leaves the 23rd as the newest session and
# makes it four weekdays old by the 29th. An ingest that has genuinely stopped
# still crosses the line inside the same week.
_MAX_SESSION_AGE_WEEKDAYS = 4
# Monday–Friday; Saturday is 5.
_WEEKEND_START = 5

# Below this share of tracked companies carrying the newest session, the last
# ingest clearly only half-worked.
_MIN_COVERAGE = 0.90

# Status values, worst last — used to fold the sections into one overall read.
_ORDER = {"ok": 0, "warn": 1, "error": 2}


@dataclass(slots=True)
class JobRecord:
    """One recorded background job, normalised from either log source."""

    action: str
    outcome: str
    started_at: datetime
    duration_ms: float | None = None
    detail: dict[str, Any] | None = None


def worst(*statuses: str) -> str:
    """The most severe of several section statuses."""
    return max(statuses, key=lambda s: _ORDER.get(s, 0))


def _local(value: datetime | None) -> str | None:
    return value.astimezone(_WARSAW).isoformat() if value else None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _hours_between(later: datetime, earlier: datetime) -> float:
    return round((later - earlier).total_seconds() / 3600.0, 2)


def weekdays_between(earlier: date, later: date) -> int:
    """How many Mon–Fri days fall after ``earlier``, up to and including ``later``.

    The unit the freshness check is measured in — a weekend costs nothing, so
    Friday's bar read on Monday is one weekday old, not three. Public holidays
    are not known here, which is why the tolerance above allows a few.
    """
    if later <= earlier:
        return 0
    return _weekdays_through(later) - _weekdays_through(earlier)


def _weekdays_through(day: date) -> int:
    """Weekdays on the calendar from the start of the era through ``day``.

    Only differences between two of these are meaningful. Day ordinal 1 is a
    Monday, so each whole block of seven ordinals contributes five weekdays and
    the remainder contributes at most five more.
    """
    weeks, remainder = divmod(day.toordinal(), 7)
    return weeks * 5 + min(remainder, _WEEKEND_START)


def last_scheduled_run(
    now: datetime, hour: int, minute: int, timezone: str = "Europe/Warsaw"
) -> datetime:
    """The most recent moment a nightly job was due, at or before ``now``.

    Computed in the schedule's own zone (Europe/Warsaw, or America/New_York for
    the US run) so it stays correct across daylight-saving changes rather than
    drifting by an hour twice a year.
    """
    local = now.astimezone(ZoneInfo(timezone))
    due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due > local:
        due -= timedelta(days=1)
    return due


def evaluate_ingest(
    jobs: list[JobRecord],
    *,
    now: datetime,
    running: bool,
    scheduler_active: bool,
    next_run_at: datetime | None,
    hour: int,
    minute: int,
    last_error: str | None = None,
    timezone: str = "Europe/Warsaw",
    run_id: str | None = None,
    markets: Sequence[str] = (),
) -> IngestHealth:
    """Did the refresh run, and did it work?

    ``jobs`` is the recorded history, newest first. The refresh pipeline writes
    ``job.refresh`` (the whole run) and ``job.ingest`` (the download step
    inside it), so the outcome comes from the former and the counters — how
    many tickers were actually fetched — from the latter.
    """
    refreshes = [j for j in jobs if j.action == "job.refresh"]
    ingests = [j for j in jobs if j.action == "job.ingest"]
    # "started" entries say a run began, not how it ended; only a run that
    # reported an outcome can be judged.
    finished = [j for j in refreshes if j.outcome in (OUTCOME_FINISHED, OUTCOME_FAILED)]
    last_run = finished[0] if finished else None
    last_success = next((j for j in finished if j.outcome == OUTCOME_FINISHED), None)
    last_ingest = next(
        (j for j in ingests if j.outcome in (OUTCOME_FINISHED, OUTCOME_FAILED)), None
    )

    expected = last_scheduled_run(now, hour, minute, timezone)
    schedule = f"{hour:02d}:{minute:02d} {timezone}"
    ran_since_expected = (
        last_success.started_at >= expected if last_success is not None else False
    )

    detail = last_run.detail or {} if last_run else {}
    ingest_detail = last_ingest.detail or {} if last_ingest else {}

    if running:
        status = "running"
        summary = "A data refresh is running right now."
    elif last_run is None:
        status = "never"
        summary = (
            "No data refresh has been recorded yet. "
            f"The nightly job runs at {schedule}."
            if scheduler_active
            else "No data refresh has been recorded, and no nightly schedule is "
            "running (the app has no database configured)."
        )
    elif last_run.outcome == OUTCOME_FAILED:
        status = "failed"
        summary = (
            "The last refresh failed "
            f"{_hours_between(now, last_run.started_at):.1f} h ago: "
            f"{detail.get('error') or last_error or 'no error text recorded'}."
        )
    elif not ran_since_expected and now >= expected + _LATE_GRACE:
        status = "stale"
        summary = (
            "No refresh since the "
            f"{expected.strftime('%H:%M')} run came due on "
            f"{expected.strftime('%Y-%m-%d')} — the last successful one was "
            f"{_hours_between(now, last_success.started_at):.1f} h ago."
            if last_success is not None
            else "No successful refresh has been recorded since the last "
            "scheduled run came due."
        )
    else:
        status = "ok"
        age = _hours_between(now, last_success.started_at) if last_success else None
        fetched = ingest_detail.get("fetched")
        summary = (
            f"Last refresh finished {age:.1f} h ago"
            + (f", {fetched} tickers fetched" if fetched is not None else "")
            + "."
            if age is not None
            else "The last refresh finished."
        )

    return IngestHealth(
        status=status,
        summary=summary,
        running=running,
        last_run_at=_iso(last_run.started_at) if last_run else None,
        last_run_local=_local(last_run.started_at) if last_run else None,
        last_outcome=last_run.outcome if last_run else None,
        last_trigger=detail.get("trigger"),
        duration_ms=(
            round(last_run.duration_ms, 1)
            if last_run and last_run.duration_ms is not None
            else None
        ),
        age_hours=(
            _hours_between(now, last_run.started_at) if last_run is not None else None
        ),
        last_success_at=_iso(last_success.started_at) if last_success else None,
        last_success_local=_local(last_success.started_at) if last_success else None,
        last_error=detail.get("error") or last_error,
        stocks_ranked=detail.get("stocksRanked"),
        fetched=ingest_detail.get("fetched"),
        skipped=ingest_detail.get("skipped"),
        failed=ingest_detail.get("failed"),
        bars_written=ingest_detail.get("barsWritten"),
        expected_at=_iso(expected),
        expected_local=expected.isoformat(),
        ran_since_expected=ran_since_expected,
        next_run_at=_iso(next_run_at),
        next_run_local=_local(next_run_at),
        scheduler_active=scheduler_active,
        schedule=schedule,
        run_id=run_id,
        markets=list(markets),
    )


def job_covers(job: JobRecord, market_ids: Sequence[str], *, legacy: bool) -> bool:
    """Did this recorded refresh/ingest include any of ``market_ids``?

    Entries written before runs were split by market carry no ``markets``;
    those were GPW-only runs, so they count for the run that covers the GPW
    (``legacy``) and for no other.
    """
    covered = (job.detail or {}).get("markets")
    if covered is None:
        return legacy
    return any(m in covered for m in market_ids)


_INGEST_SEVERITY = {"ok": 0, "running": 1, "never": 2, "stale": 3, "failed": 4}


def combine_ingest(runs: Sequence[IngestHealth]) -> IngestHealth:
    """One reading for several nightly runs: the worst, carrying all of them."""
    if len(runs) == 1:
        return runs[0]
    worst_run = max(runs, key=lambda r: _INGEST_SEVERITY.get(r.status, 2))
    summary = " ".join(
        f"{(r.run_id or 'run').upper()}: {r.summary}" for r in runs
    )
    return worst_run.model_copy(
        update={
            "summary": summary,
            "markets": [m for r in runs for m in r.markets],
            "schedule": "; ".join(r.schedule for r in runs),
            "runs": list(runs),
        }
    )


def evaluate_data(
    stats: StoredDataStats | None,
    *,
    tickers_tracked: int,
    db_enabled: bool,
    today: date,
    read_failed: bool = False,
    refresh_running: bool = False,
) -> DataHealth:
    """How fresh and how complete the stored market data is.

    Deliberately independent of what the jobs *said*: a refresh can report
    success and still leave the database a week behind if the provider served
    nothing. This reads the data itself.

    ``refresh_running`` is the one thing it does take from the job side: while
    an ingest is working through the universe, only part of it has the newest
    session yet. That is the run in progress, not a fault, and calling it
    "behind" every night at 18:00 would teach the reader to ignore the word.
    """
    if not db_enabled:
        return DataHealth(
            status="disabled",
            summary=(
                "No database is configured, so nothing is stored — every screen "
                "is computed live and the app keeps no history."
            ),
            db_enabled=False,
            tickers_tracked=tickers_tracked,
        )
    if read_failed or stats is None:
        return DataHealth(
            status="error",
            summary="The database could not be read to check the stored data.",
            db_enabled=True,
            tickers_tracked=tickers_tracked,
        )
    if stats.latest_bar_date is None or stats.tickers_with_data == 0:
        return DataHealth(
            status="empty",
            summary="The database holds no price bars yet — run a refresh.",
            db_enabled=True,
            tickers_tracked=tickers_tracked,
            tickers_with_data=0,
            bar_count=stats.bar_count,
        )

    age_days = (today - stats.latest_bar_date).days
    market_rows = [
        _market_data(m, today=today, refresh_running=refresh_running)
        for m in stats.markets
    ]
    if len(market_rows) > 1:
        return _multi_market_data(
            stats,
            market_rows,
            tickers_tracked=tickers_tracked,
            age_days=age_days,
        )

    # The verdict is taken on weekdays; `age_days` stays the plain calendar
    # number the screen shows, which is what a reader counts on a calendar.
    age_weekdays = weekdays_between(stats.latest_bar_date, today)
    coverage = (
        stats.tickers_current / tickers_tracked if tickers_tracked else None
    )

    if age_weekdays > _MAX_SESSION_AGE_WEEKDAYS:
        status = "stale"
        summary = (
            f"The newest stored session is {stats.latest_bar_date} — "
            f"{age_days} days old."
        )
    elif coverage is not None and coverage < _MIN_COVERAGE:
        if refresh_running:
            status = "updating"
            summary = (
                f"A refresh is in progress — {stats.tickers_current} of "
                f"{tickers_tracked} companies updated to {stats.latest_bar_date} "
                "so far."
            )
        else:
            status = "stale"
            summary = (
                f"Only {stats.tickers_current} of {tickers_tracked} tracked "
                f"companies have data for {stats.latest_bar_date}."
            )
    else:
        status = "ok"
        summary = (
            f"{stats.tickers_current} of {tickers_tracked} companies are current "
            f"as of {stats.latest_bar_date}."
        )

    return DataHealth(
        status=status,
        summary=summary,
        db_enabled=True,
        latest_bar_date=stats.latest_bar_date.isoformat(),
        earliest_bar_date=(
            stats.earliest_bar_date.isoformat() if stats.earliest_bar_date else None
        ),
        latest_snapshot_date=(
            stats.latest_snapshot_date.isoformat()
            if stats.latest_snapshot_date
            else None
        ),
        session_age_days=age_days,
        tickers_tracked=tickers_tracked,
        tickers_with_data=stats.tickers_with_data,
        tickers_current=stats.tickers_current,
        tickers_behind=stats.tickers_behind,
        coverage_pct=round(coverage * 100.0, 1) if coverage is not None else None,
        bar_count=stats.bar_count,
        markets=market_rows,
    )


_DATA_SEVERITY = {"ok": 0, "updating": 1, "empty": 2, "stale": 3}


def _market_data(
    stats: MarketStoredStats, *, today: date, refresh_running: bool
) -> MarketDataHealth:
    """The same freshness rules as the whole-database verdict, for one market."""
    newest = stats.latest_bar_date
    coverage = (
        stats.tickers_current / stats.tickers_tracked if stats.tickers_tracked else None
    )
    if newest is None:
        status = "empty"
    elif weekdays_between(newest, today) > _MAX_SESSION_AGE_WEEKDAYS:
        status = "stale"
    elif coverage is not None and coverage < _MIN_COVERAGE:
        status = "updating" if refresh_running else "stale"
    else:
        status = "ok"
    return MarketDataHealth(
        market=stats.market,
        status=status,
        latest_bar_date=newest.isoformat() if newest else None,
        session_age_days=(today - newest).days if newest else None,
        tickers_tracked=stats.tickers_tracked,
        tickers_with_data=stats.tickers_with_data,
        tickers_current=stats.tickers_current,
        coverage_pct=round(coverage * 100.0, 1) if coverage is not None else None,
    )


def _multi_market_data(
    stats: StoredDataStats,
    markets: list[MarketDataHealth],
    *,
    tickers_tracked: int,
    age_days: int,
) -> DataHealth:
    """The whole-database verdict when several markets are served."""
    worst = max(markets, key=lambda m: _DATA_SEVERITY.get(m.status, 3))
    status = worst.status
    if status == "ok":
        summary = (
            f"{stats.tickers_current} of {tickers_tracked} companies are current "
            f"on {len(markets)} markets."
        )
    else:
        problems = [m for m in markets if m.status != "ok"]
        summary = " ".join(
            f"{m.market.upper()}: "
            + (
                "no stored data yet."
                if m.status == "empty"
                else f"{m.tickers_current} of {m.tickers_tracked} companies have "
                f"data for {m.latest_bar_date}"
                + (" (a refresh is in progress)." if m.status == "updating" else ".")
            )
            for m in problems
        )
    coverage = stats.tickers_current / tickers_tracked if tickers_tracked else None
    return DataHealth(
        status=status,
        summary=summary,
        db_enabled=True,
        latest_bar_date=stats.latest_bar_date.isoformat() if stats.latest_bar_date else None,
        earliest_bar_date=(
            stats.earliest_bar_date.isoformat() if stats.earliest_bar_date else None
        ),
        latest_snapshot_date=(
            stats.latest_snapshot_date.isoformat() if stats.latest_snapshot_date else None
        ),
        session_age_days=age_days,
        tickers_tracked=tickers_tracked,
        tickers_with_data=stats.tickers_with_data,
        tickers_current=stats.tickers_current,
        tickers_behind=stats.tickers_behind,
        coverage_pct=round(coverage * 100.0, 1) if coverage is not None else None,
        bar_count=stats.bar_count,
        markets=markets,
    )


def evaluate_errors(
    *,
    total_count: int,
    group_count: int,
    window_hours: int,
    top: list[Any],
) -> ErrorHealth:
    """Summarise recent failures.

    Errors never make the overall status red on their own: the app handles a
    dead ticker or a provider hiccup by design, and a screen that shouts
    "ERROR" at three skipped symbols trains its reader to ignore it. What they
    do is raise a warning, so something visibly changed.
    """
    if total_count == 0:
        status = "ok"
        summary = f"No errors recorded in the last {window_hours} h."
    else:
        status = "warn"
        noun = "problem" if group_count == 1 else "distinct problems"
        summary = (
            f"{total_count} error{'s' if total_count != 1 else ''} in the last "
            f"{window_hours} h, from {group_count} {noun}."
        )
    return ErrorHealth(
        status=status,
        summary=summary,
        window_hours=window_hours,
        total_count=total_count,
        group_count=group_count,
        top=top,
    )


def overall_status(ingest: IngestHealth, data: DataHealth, errors: ErrorHealth) -> str:
    """Fold the sections into the one word at the top of the screen."""
    ingest_status = {
        "ok": "ok",
        "running": "ok",
        "stale": "warn",
        "never": "warn",
        "failed": "error",
    }.get(ingest.status, "warn")
    data_status = {
        "ok": "ok",
        "disabled": "ok",
        # Partial coverage while the ingest is still running is the run, not a
        # fault; the ingest section is where a run in progress is reported.
        "updating": "ok",
        "stale": "warn",
        "empty": "warn",
        "error": "error",
    }.get(data.status, "warn")
    return worst(ingest_status, data_status, errors.status)
