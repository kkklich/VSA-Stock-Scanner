"""Tests for error tracking and the system-health read.

Two features, one purpose: making the app able to answer "did last night's job
run, and what has been failing?" without anyone watching a terminal.

  * ``app/services/error_tracker.py`` — every ERROR-level log line becomes a
    grouped, counted error, mirrored into the action log.
  * ``app/services/system_health.py`` — the ingest / data / errors verdicts
    behind ``GET /api/admin/health``.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.health_repository import StoredDataStats
from app.dependencies import action_log, error_tracker
from app.main import app
from app.services.action_log import (
    KIND_ERROR,
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_STARTED,
    ActionLogService,
)
from app.services.error_tracker import (
    ErrorTracker,
    ErrorTrackingHandler,
    fingerprint_of,
)
from app.services.system_health import (
    JobRecord,
    evaluate_data,
    evaluate_errors,
    evaluate_ingest,
    last_scheduled_run,
    overall_status,
    worst,
)

_WARSAW_NOON = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)  # 12:00 Europe/Warsaw


@pytest.fixture(autouse=True)
def _clean_state():
    """Each test starts with an empty error table and log buffer."""
    error_tracker.clear()
    action_log._recent.clear()
    yield
    error_tracker.clear()
    action_log._recent.clear()


def _boom(message: str = "kaboom") -> ValueError:
    """A raised-and-caught exception, so it carries a real traceback."""
    try:
        raise ValueError(message)
    except ValueError as exc:
        return exc


# ── Grouping ──────────────────────────────────────────────────────────────────


class TestErrorGrouping:
    def test_same_fault_twice_is_one_group_counted_twice(self) -> None:
        tracker = ErrorTracker()
        tracker.record_message("Ingest error for KGH", template="Ingest error for %s")
        tracker.record_message("Ingest error for PKN", template="Ingest error for %s")

        groups = tracker.groups()
        assert len(groups) == 1
        assert groups[0].count == 2
        # The group is named by the fault; the latest victim is kept separately.
        assert groups[0].message == "Ingest error for %s"
        assert groups[0].last_message == "Ingest error for PKN"

    def test_numbers_in_a_message_do_not_split_a_group(self) -> None:
        """"Timed out after 30s" and "after 45s" are one problem, not two."""
        assert fingerprint_of("TimeoutError", "a.py:1", "gave up after 30s") == (
            fingerprint_of("TimeoutError", "a.py:1", "gave up after 45s")
        )

    def test_different_faults_are_different_groups(self) -> None:
        tracker = ErrorTracker()
        tracker.record_message("disk full", template="disk full")
        tracker.record_message("database gone", template="database gone")
        assert len(tracker.groups()) == 2

    def test_exception_records_type_traceback_and_app_frame(self) -> None:
        tracker = ErrorTracker()
        group = tracker.record_exception(_boom())
        assert group is not None
        assert group.error_type == "ValueError"
        assert "ValueError: kaboom" in (group.traceback or "")
        # The frame points at this test file, reached through the app root.
        assert group.where is not None

    def test_one_exception_is_counted_once_however_often_it_is_seen(self) -> None:
        """The middleware records it, then the server logs it. That is one failure."""
        tracker = ErrorTracker()
        exc = _boom()
        tracker.record_exception(exc, source="api")
        tracker.record_exception(exc, source="uvicorn.error")
        assert sum(g.count for g in tracker.groups()) == 1

    def test_group_table_is_bounded(self) -> None:
        # Distinct *words*, not distinct numbers: numbered variants of one
        # message are deliberately the same group (see the test above).
        names = "abcdefghij"
        tracker = ErrorTracker(max_groups=3)
        for name in names:
            tracker.record_message(f"fault {name}", template=f"fault-{name}")
        assert len(tracker.groups()) == 3
        # Total occurrences are still counted, even for evicted groups.
        assert tracker.total_count == len(names)

    def test_disabled_tracker_records_nothing(self) -> None:
        tracker = ErrorTracker(enabled=False)
        assert tracker.record_message("nope") is None
        assert tracker.groups() == []

    def test_count_since_ignores_older_groups(self) -> None:
        tracker = ErrorTracker()
        tracker.record_message("recent", template="recent")
        assert tracker.count_since(datetime.now(tz=UTC) - timedelta(hours=1)) == 1
        assert tracker.count_since(datetime.now(tz=UTC) + timedelta(hours=1)) == 0


# ── The logging bridge ────────────────────────────────────────────────────────


class TestErrorTrackingHandler:
    def _attached(self, tracker: ErrorTracker) -> logging.Logger:
        logger = logging.getLogger("app.tests.bridge")
        logger.handlers = [ErrorTrackingHandler(tracker)]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        return logger

    def test_logger_error_becomes_a_tracked_group(self) -> None:
        tracker = ErrorTracker()
        logger = self._attached(tracker)
        logger.error("Ingest error for %s: %s", "kgh", "timeout")

        groups = tracker.groups()
        assert len(groups) == 1
        assert groups[0].last_message == "Ingest error for kgh: timeout"
        assert groups[0].source == "app.tests.bridge"

    def test_many_tickers_failing_is_one_group(self) -> None:
        """The reason grouping exists: 290 failures are one problem, not 290."""
        tracker = ErrorTracker()
        logger = self._attached(tracker)
        for ticker in ("kgh", "pkn", "ccc", "peo"):
            logger.error("Ingest error for %s: %s", ticker, "timeout")

        assert len(tracker.groups()) == 1
        assert tracker.groups()[0].count == 4

    def test_logger_exception_keeps_the_traceback(self) -> None:
        tracker = ErrorTracker()
        logger = self._attached(tracker)
        try:
            raise RuntimeError("refresh exploded")
        except RuntimeError:
            logger.exception("Data refresh failed.")

        group = tracker.groups()[0]
        assert group.error_type == "RuntimeError"
        assert "refresh exploded" in (group.traceback or "")

    def test_warnings_are_not_errors(self) -> None:
        tracker = ErrorTracker()
        logger = self._attached(tracker)
        logger.warning("Ingest skipped for %s: dead symbol", "woj")
        assert tracker.groups() == []


# ── Mirroring into the action log ─────────────────────────────────────────────


class TestErrorsReachTheActionLog:
    def test_first_occurrence_is_written_as_an_error_entry(self) -> None:
        log = ActionLogService(to_file=False)
        tracker = ErrorTracker(action_log=log)
        tracker.record_exception(_boom("written down"))

        entries = log.recent()
        assert len(entries) == 1
        assert entries[0].kind == KIND_ERROR
        assert entries[0].action == "error.ValueError"
        assert entries[0].detail["occurrences"] == 1
        assert entries[0].detail["fingerprint"] == tracker.groups()[0].fingerprint

    def test_a_burst_is_throttled_but_still_counted(self) -> None:
        """One row instead of 290 — carrying how many hits it stands for."""
        log = ActionLogService(to_file=False)
        tracker = ErrorTracker(action_log=log, throttle_seconds=3600)
        for ticker in range(50):
            tracker.record_message(
                f"Ingest error for {ticker}", template="Ingest error for %s"
            )

        assert len(log.recent()) == 1
        assert tracker.groups()[0].count == 50
        # The 49 suppressed hits are carried on the next entry that is written.
        assert tracker.groups()[0].pending == 49

    def test_next_written_entry_carries_the_suppressed_hits(self) -> None:
        log = ActionLogService(to_file=False)
        tracker = ErrorTracker(action_log=log, throttle_seconds=0)
        tracker.record_message("a", template="tpl")
        tracker.record_message("b", template="tpl")
        assert [e.detail["occurrences"] for e in log.recent()] == [1, 1]

    def test_a_broken_action_log_never_breaks_the_caller(self) -> None:
        class Exploding:
            def record(self, entry):
                raise RuntimeError("log is on fire")

        tracker = ErrorTracker(action_log=Exploding())
        assert tracker.record_message("still counted") is not None
        assert tracker.groups()[0].count == 1


# ── Ingest health ─────────────────────────────────────────────────────────────


def _refresh(outcome: str, when: datetime, **detail) -> JobRecord:
    return JobRecord(
        action="job.refresh",
        outcome=outcome,
        started_at=when,
        duration_ms=1234.5,
        detail={"trigger": "nightly", **detail},
    )


def _ingest(when: datetime, **detail) -> JobRecord:
    return JobRecord(
        action="job.ingest",
        outcome=OUTCOME_FINISHED,
        started_at=when,
        duration_ms=999.0,
        detail={"fetched": 288, "skipped": 2, "failed": 0, "barsWritten": 1440, **detail},
    )


def _evaluate(jobs, *, now=_WARSAW_NOON, running=False, scheduler_active=True):
    return evaluate_ingest(
        jobs,
        now=now,
        running=running,
        scheduler_active=scheduler_active,
        next_run_at=None,
        hour=18,
        minute=0,
    )


class TestLastScheduledRun:
    def test_before_the_hour_the_due_run_was_yesterday(self) -> None:
        # 12:00 Warsaw — the 18:00 job last came due the previous evening.
        due = last_scheduled_run(_WARSAW_NOON, 18, 0)
        assert (due.hour, due.minute) == (18, 0)
        assert due.date() == date(2026, 9, 7)

    def test_after_the_hour_the_due_run_is_today(self) -> None:
        evening = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)  # 21:00 Warsaw
        assert last_scheduled_run(evening, 18, 0).date() == date(2026, 9, 8)


class TestIngestHealth:
    def test_a_refresh_last_night_is_ok(self) -> None:
        last_night = datetime(2026, 9, 7, 16, 5, tzinfo=UTC)  # 18:05 Warsaw
        health = _evaluate([_refresh(OUTCOME_FINISHED, last_night), _ingest(last_night)])
        assert health.status == "ok"
        assert health.ran_since_expected is True
        assert health.fetched == 288
        assert health.bars_written == 1440

    def test_a_missed_night_is_stale(self) -> None:
        """The whole point of the screen: nothing ran when it was due."""
        two_days_ago = datetime(2026, 9, 5, 16, 5, tzinfo=UTC)
        health = _evaluate([_refresh(OUTCOME_FINISHED, two_days_ago)])
        assert health.status == "stale"
        assert health.ran_since_expected is False

    def test_a_run_that_blew_up_is_failed_with_its_error(self) -> None:
        last_night = datetime(2026, 9, 7, 16, 5, tzinfo=UTC)
        health = _evaluate(
            [_refresh(OUTCOME_FAILED, last_night, error="ConnectionError: yahoo")]
        )
        assert health.status == "failed"
        assert "yahoo" in health.summary

    def test_a_started_entry_alone_is_not_an_outcome(self) -> None:
        """A run that began and never reported back must not read as success."""
        long_ago = datetime(2026, 9, 1, 16, 5, tzinfo=UTC)
        health = _evaluate([_refresh(OUTCOME_STARTED, long_ago)])
        assert health.status == "never"

    def test_nothing_recorded_at_all(self) -> None:
        assert _evaluate([]).status == "never"

    def test_a_run_in_progress_is_not_a_failure(self) -> None:
        assert _evaluate([], running=True).status == "running"

    def test_a_missed_run_within_the_grace_window_is_not_stale_yet(self) -> None:
        # 18:30 Warsaw, half an hour after the job came due: still running late,
        # not yet missing.
        just_after = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
        health = _evaluate(
            [_refresh(OUTCOME_FINISHED, datetime(2026, 9, 7, 16, 5, tzinfo=UTC))],
            now=just_after,
        )
        assert health.status == "ok"

    def test_no_scheduler_is_reported_rather_than_blamed(self) -> None:
        health = _evaluate([], scheduler_active=False)
        assert health.scheduler_active is False
        assert "no nightly schedule" in health.summary


# ── Data health ───────────────────────────────────────────────────────────────


def _stats(latest: date, current: int = 288, **kwargs) -> StoredDataStats:
    return StoredDataStats(
        latest_bar_date=latest,
        earliest_bar_date=kwargs.get("earliest", date(2024, 1, 2)),
        tickers_with_data=kwargs.get("with_data", 288),
        tickers_current=current,
        tickers_behind=kwargs.get("with_data", 288) - current,
        bar_count=kwargs.get("bars", 120_000),
        latest_snapshot_date=kwargs.get("snapshot", latest),
    )


class TestDataHealth:
    def test_fresh_full_coverage_is_ok(self) -> None:
        health = evaluate_data(
            _stats(date(2026, 9, 8)),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
        )
        assert health.status == "ok"
        assert health.coverage_pct == 100.0
        assert health.session_age_days == 0

    def test_a_weekend_does_not_make_data_stale(self) -> None:
        """Monday morning, newest bar is Friday. Normal, not a fault."""
        health = evaluate_data(
            _stats(date(2026, 9, 4)),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 7),
        )
        assert health.status == "ok"

    def test_a_week_old_session_is_stale(self) -> None:
        health = evaluate_data(
            _stats(date(2026, 9, 1)),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
        )
        assert health.status == "stale"

    def test_half_the_universe_missing_is_stale(self) -> None:
        """A refresh can report success and still leave most tickers behind."""
        health = evaluate_data(
            _stats(date(2026, 9, 8), current=140),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
        )
        assert health.status == "stale"
        assert health.tickers_behind == 148

    def test_partial_coverage_during_a_run_is_the_run_not_a_fault(self) -> None:
        """Every night at 18:00 the ingest is mid-universe. That is not "behind"."""
        health = evaluate_data(
            _stats(date(2026, 9, 8), current=57),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
            refresh_running=True,
        )
        assert health.status == "updating"
        assert health.tickers_current == 57

    def test_no_database_is_a_mode_not_a_fault(self) -> None:
        health = evaluate_data(
            None, tickers_tracked=288, db_enabled=False, today=date(2026, 9, 8)
        )
        assert health.status == "disabled"

    def test_a_failed_read_is_an_error_not_an_empty_screen(self) -> None:
        health = evaluate_data(
            None,
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
            read_failed=True,
        )
        assert health.status == "error"

    def test_an_empty_database_says_so(self) -> None:
        health = evaluate_data(
            StoredDataStats(None, None, 0, 0, 0, 0, None),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
        )
        assert health.status == "empty"


# ── Folding it together ───────────────────────────────────────────────────────


class TestOverallStatus:
    def test_worst_wins(self) -> None:
        assert worst("ok", "warn", "error") == "error"
        assert worst("ok", "ok") == "ok"

    def test_errors_alone_only_warn(self) -> None:
        """Three skipped symbols must not paint the whole screen red."""
        ingest = _evaluate(
            [_refresh(OUTCOME_FINISHED, datetime(2026, 9, 7, 16, 5, tzinfo=UTC))]
        )
        data = evaluate_data(
            _stats(date(2026, 9, 8)),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
        )
        errors = evaluate_errors(
            total_count=3, group_count=1, window_hours=24, top=[]
        )
        assert overall_status(ingest, data, errors) == "warn"

    def test_a_failed_refresh_is_an_error(self) -> None:
        ingest = _evaluate(
            [
                _refresh(
                    OUTCOME_FAILED, datetime(2026, 9, 7, 16, 5, tzinfo=UTC), error="x"
                )
            ]
        )
        data = evaluate_data(
            _stats(date(2026, 9, 8)),
            tickers_tracked=288,
            db_enabled=True,
            today=date(2026, 9, 8),
        )
        errors = evaluate_errors(total_count=0, group_count=0, window_hours=24, top=[])
        assert overall_status(ingest, data, errors) == "error"


# ── The endpoints ─────────────────────────────────────────────────────────────


class TestAdminEndpoints:
    def test_health_answers_without_a_database(self) -> None:
        with TestClient(app) as client:
            body = client.get("/api/admin/health").json()

        assert body["status"] in {"ok", "warn", "error"}
        assert body["data"]["dbEnabled"] is False
        assert body["ingest"]["schedule"].endswith("Europe/Warsaw")
        assert body["log"]["enabled"] is True

    def test_health_reports_that_the_admin_api_is_open(self) -> None:
        """The screen shows tracebacks and caller IPs; say when it is unguarded."""
        with TestClient(app) as client:
            assert client.get("/api/admin/health").json()["protected"] is False

    def test_errors_endpoint_lists_grouped_failures(self) -> None:
        error_tracker.record_message(
            "Ingest error for kgh", template="Ingest error for %s", source="app.jobs"
        )
        error_tracker.record_message(
            "Ingest error for pkn", template="Ingest error for %s", source="app.jobs"
        )
        with TestClient(app) as client:
            body = client.get("/api/admin/errors").json()

        assert body["groupCount"] == 1
        assert body["totalCount"] == 2
        assert body["items"][0]["count"] == 2
        assert body["items"][0]["message"] == "Ingest error for %s"

    def test_a_throttled_burst_is_counted_in_full(self) -> None:
        """The count must be 290, not the one hit the log happened to write."""
        for ticker in range(290):
            error_tracker.record_message(
                f"Ingest error for {ticker}", template="Ingest error for %s"
            )
        with TestClient(app) as client:
            body = client.get("/api/admin/errors").json()

        assert body["items"][0]["count"] == 290

    def test_errors_show_up_in_the_health_read(self) -> None:
        error_tracker.record_exception(_boom("visible in health"))
        with TestClient(app) as client:
            body = client.get("/api/admin/health").json()

        assert body["errors"]["totalCount"] == 1
        assert body["errors"]["top"][0]["errorType"] == "ValueError"
        assert body["status"] == "warn"

    def test_a_failing_endpoint_is_recorded_as_an_error(self) -> None:
        """The path that matters most: an API call that blew up, with its route."""

        @app.get("/api/admin/_boom_for_test")
        async def _boom_endpoint() -> dict[str, str]:
            raise RuntimeError("endpoint exploded")

        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/api/admin/_boom_for_test")

        groups = error_tracker.groups()
        assert any(g.error_type == "RuntimeError" for g in groups)
        recorded = next(g for g in groups if g.error_type == "RuntimeError")
        assert recorded.context["path"] == "/api/admin/_boom_for_test"

    def test_the_admin_token_gates_every_admin_endpoint(self) -> None:
        settings.admin_token = "s3cret"
        try:
            with TestClient(app) as client:
                assert client.get("/api/admin/health").status_code == 401
                assert client.get("/api/admin/errors").status_code == 401
                assert client.get("/api/admin/logs").status_code == 401

                ok = client.get(
                    "/api/admin/health", headers={"X-Admin-Token": "s3cret"}
                )
                assert ok.status_code == 200
                assert ok.json()["protected"] is True

                assert (
                    client.get(
                        "/api/admin/health", headers={"X-Admin-Token": "wrong"}
                    ).status_code
                    == 401
                )
        finally:
            settings.admin_token = ""
