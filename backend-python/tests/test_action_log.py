"""Tests for the action log (audit trail) — app/services/action_log.py.

Covers the three things the feature promises: every API call is recorded, the
record is *saved* (to a rotating file that survives a restart), and background
jobs report their own outcome rather than hiding behind a 202.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import action_log
from app.jobs.daily_ingest import IngestStats
from app.main import app
from app.services.action_log import (
    OUTCOME_CLIENT_ERROR,
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_OK,
    OUTCOME_SERVER_ERROR,
    OUTCOME_STARTED,
    ActionLogEntry,
    ActionLogService,
    outcome_for_status,
    sanitize_query,
)
from app.services.refresh_service import ingest_outcome


@pytest.fixture(autouse=True)
def _clear_log():
    """Each test starts from an empty in-memory buffer."""
    action_log._recent.clear()
    yield
    action_log._recent.clear()


# ── Sanitising ────────────────────────────────────────────────────────────────


class TestSanitizeQuery:
    def test_empty_query_is_none(self) -> None:
        assert sanitize_query("") is None

    def test_ordinary_params_are_kept(self) -> None:
        assert sanitize_query("page=2&sortBy=currentRating") == (
            "page=2&sortBy=currentRating"
        )

    def test_settings_blob_is_hashed_not_stored(self) -> None:
        """The VSA settings payload is a whole configuration — store a fingerprint."""
        blob = json.dumps({"signals": {"spring": {"enabled": True, "volMult": 2.0}}})
        result = sanitize_query(f"settings={blob}&page=1")
        assert "spring" not in result
        assert "settings=sha256:" in result
        assert "page=1" in result

    def test_same_settings_hash_to_the_same_fingerprint(self) -> None:
        first = sanitize_query("settings=abc")
        second = sanitize_query("settings=abc")
        assert first == second != sanitize_query("settings=abd")

    def test_credential_looking_params_are_masked(self) -> None:
        result = sanitize_query("token=supersecret&password=hunter2&q=kgh")
        assert "supersecret" not in result
        assert "hunter2" not in result
        assert "token=***" in result
        assert "password=***" in result
        assert "q=kgh" in result

    def test_long_values_are_truncated(self) -> None:
        result = sanitize_query("q=" + "x" * 500)
        assert len(result) < 200


class TestOutcomeForStatus:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (200, OUTCOME_OK),
            (202, OUTCOME_OK),
            (304, OUTCOME_OK),
            (400, OUTCOME_CLIENT_ERROR),
            (404, OUTCOME_CLIENT_ERROR),
            (500, OUTCOME_SERVER_ERROR),
            (503, OUTCOME_SERVER_ERROR),
        ],
    )
    def test_maps_status_to_outcome(self, status: int, expected: str) -> None:
        assert outcome_for_status(status) == expected


# ── The file: logs must SURVIVE a restart ─────────────────────────────────────


class TestFileWriting:
    def test_entry_is_written_as_one_json_line(self, tmp_path: Path) -> None:
        service = ActionLogService(directory=tmp_path)
        service.open_file()
        service.record(
            ActionLogEntry(action="/api/stocks/ranking", method="GET", status_code=200)
        )
        service.close_file()

        path = tmp_path / "actions.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["action"] == "/api/stocks/ranking"
        assert row["method"] == "GET"
        assert row["status"] == 200
        assert row["outcome"] == OUTCOME_OK
        # Both clocks are on the line: UTC to sort by, Warsaw to read by.
        assert row["ts"].endswith("+00:00")
        assert row["tsLocal"] != row["ts"]

    def test_file_survives_the_service_being_recreated(self, tmp_path: Path) -> None:
        """A restart must not lose what was already recorded."""
        first = ActionLogService(directory=tmp_path)
        first.open_file()
        first.record(ActionLogEntry(action="before-restart"))
        first.close_file()

        second = ActionLogService(directory=tmp_path)
        second.open_file()
        second.record(ActionLogEntry(action="after-restart"))
        second.close_file()

        lines = (tmp_path / "actions.jsonl").read_text(encoding="utf-8").splitlines()
        actions = [json.loads(line)["action"] for line in lines if line.strip()]
        assert actions == ["before-restart", "after-restart"]

    def test_rotation_caps_the_file_size(self, tmp_path: Path) -> None:
        service = ActionLogService(
            directory=tmp_path, file_max_bytes=1024, file_backups=2
        )
        service.open_file()
        for i in range(200):
            service.record(ActionLogEntry(action=f"/api/stocks/{i}", path="x" * 100))
        service.close_file()

        assert (tmp_path / "actions.jsonl").exists()
        assert (tmp_path / "actions.jsonl.1").exists()
        # backupCount=2 — never a third old file, so the disk cost is bounded.
        assert not (tmp_path / "actions.jsonl.3").exists()

    def test_disabled_service_records_nothing(self, tmp_path: Path) -> None:
        service = ActionLogService(enabled=False, directory=tmp_path)
        service.open_file()
        service.record(ActionLogEntry(action="ignored"))
        assert not (tmp_path / "actions.jsonl").exists()
        assert service.recent() == []

    def test_unwritable_directory_does_not_raise(self, tmp_path: Path) -> None:
        """A broken log must degrade the audit trail, not the application."""
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        service = ActionLogService(directory=blocker)
        service.open_file()  # must not raise
        assert service.file_path is None
        service.record(ActionLogEntry(action="still recorded in memory"))
        assert len(service.recent()) == 1


# ── The in-memory buffer / filtering ─────────────────────────────────────────


class TestRecentBuffer:
    def test_newest_first_and_bounded(self) -> None:
        service = ActionLogService(to_file=False, memory_entries=3)
        for i in range(5):
            service.record(ActionLogEntry(action=f"a{i}"))
        assert [e.action for e in service.recent()] == ["a4", "a3", "a2"]

    def test_filters_by_kind_action_and_outcome(self) -> None:
        service = ActionLogService(to_file=False)
        service.record(ActionLogEntry(action="/api/stocks/ranking"))
        service.record(ActionLogEntry(action="/api/stocks/heatmap", outcome="failed"))
        service.log_job("job.refresh", OUTCOME_FINISHED)

        assert len(service.recent(kind="job")) == 1
        assert len(service.recent(kind="request")) == 2
        assert len(service.recent(action="ranking")) == 1
        assert len(service.recent(action="RANKING")) == 1  # case-insensitive
        assert len(service.recent(outcome="failed")) == 1

    def test_filters_by_time_window(self) -> None:
        service = ActionLogService(to_file=False)
        old = ActionLogEntry(
            action="old", started_at=datetime.now(tz=UTC) - timedelta(hours=48)
        )
        service.record(old)
        service.record(ActionLogEntry(action="new"))
        since = datetime.now(tz=UTC) - timedelta(hours=24)
        assert [e.action for e in service.recent(since=since)] == ["new"]


# ── The middleware: every API action is recorded ─────────────────────────────


class TestRequestLogging:
    def test_successful_call_is_recorded_with_route_template(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/stocks")
        assert response.status_code == 200

        entries = action_log.recent(action="/api/stocks")
        assert entries, "the call should have produced an action-log entry"
        entry = entries[0]
        assert entry.kind == "request"
        assert entry.method == "GET"
        assert entry.outcome == OUTCOME_OK
        assert entry.status_code == 200
        assert entry.duration_ms is not None and entry.duration_ms >= 0

    def test_response_carries_the_request_id_of_its_log_entry(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/stocks")
        request_id = response.headers.get("X-Request-Id")
        assert request_id
        assert any(e.request_id == request_id for e in action_log.recent())

    def test_query_string_is_recorded_sanitised(self) -> None:
        with TestClient(app) as client:
            client.get("/api/stocks/ranking?page=1&pageSize=1&settings=%7B%22a%22%3A1%7D")
        entry = action_log.recent(action="/api/stocks/ranking")[0]
        assert "page=1" in entry.query
        assert "settings=sha256:" in entry.query
        assert '{"a"' not in entry.query

    def test_client_error_is_recorded_as_such(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/stocks/ranking?page=0")
        assert response.status_code == 422
        entry = action_log.recent(action="/api/stocks/ranking")[0]
        assert entry.outcome == OUTCOME_CLIENT_ERROR
        assert entry.status_code == 422

    def test_health_probe_is_not_recorded(self) -> None:
        """The Docker healthcheck polls /health every 30s — pure noise."""
        with TestClient(app) as client:
            client.get("/health")
        assert action_log.recent(action="/health") == []

    def test_cors_preflight_is_not_recorded(self) -> None:
        """A preflight is the browser asking permission, not an action.

        This middleware is added last in main.py, which makes it the OUTERMOST
        layer — the OPTIONS call reaches it before CORS answers it, so the skip
        has to be explicit. Without it every browser call is logged twice.
        """
        with TestClient(app) as client:
            preflight = client.options(
                "/api/stocks/methods",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert preflight.status_code == 200
            assert action_log.recent(action="/api/stocks/methods") == []

            # The real call that follows it IS recorded.
            client.get(
                "/api/stocks/methods", headers={"Origin": "http://localhost:5173"}
            )

        entries = action_log.recent(action="/api/stocks/methods")
        assert len(entries) == 1
        assert entries[0].method == "GET"

    def test_route_template_groups_calls_for_different_tickers(self) -> None:
        with TestClient(app) as client:
            client.get("/api/stocks/kgh/volume")
            client.get("/api/stocks/pko/volume")
        entries = action_log.recent(action="/api/stocks/{ticker}/volume")
        assert len(entries) == 2
        # The concrete paths are still there, one level down.
        assert {e.path for e in entries} == {
            "/api/stocks/kgh/volume",
            "/api/stocks/pko/volume",
        }


# ── Jobs report their own outcome ─────────────────────────────────────────────


class TestJobLogging:
    def test_log_job_records_kind_job_with_detail(self) -> None:
        service = ActionLogService(to_file=False)
        service.log_job(
            "job.ingest",
            OUTCOME_FINISHED,
            duration_ms=1234.5,
            detail={"fetched": 280, "failed": 3},
        )
        entry = service.recent()[0]
        assert entry.kind == "job"
        assert entry.action == "job.ingest"
        assert entry.outcome == OUTCOME_FINISHED
        assert entry.detail == {"fetched": 280, "failed": 3}

    @pytest.mark.asyncio
    async def test_refresh_records_started_and_finished(self) -> None:
        from app.services.cache import TTLCache
        from app.services.refresh_service import RefreshService

        service = ActionLogService(to_file=False)
        refresh = RefreshService(
            companies=[],
            stooq=None,
            history_cache=TTLCache(),
            ranking_cache=TTLCache(),
            action_log=service,
        )
        await refresh.run(trigger="nightly")

        outcomes = [e.outcome for e in service.recent(action="job.refresh")]
        # Newest first: finished, then started.
        assert outcomes == [OUTCOME_FINISHED, OUTCOME_STARTED]
        finished = service.recent(action="job.refresh")[0]
        assert finished.detail["trigger"] == "nightly"
        assert finished.duration_ms is not None

    @pytest.mark.asyncio
    async def test_refresh_job_inherits_the_request_id_that_started_it(self) -> None:
        """The button press and the work it sets off share one id."""
        from app.services.cache import TTLCache
        from app.services.refresh_service import RefreshService

        service = ActionLogService(to_file=False)
        refresh = RefreshService(
            companies=[],
            stooq=None,
            history_cache=TTLCache(),
            ranking_cache=TTLCache(),
            action_log=service,
        )
        await refresh.run(trigger="manual", request_id="abc123def456")

        entries = service.recent(action="job.refresh")
        assert entries
        assert all(e.request_id == "abc123def456" for e in entries)

    def test_manual_refresh_endpoint_ties_the_job_to_the_call(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/stocks/refresh")
        # 503 when no refresh service is wired up in this test app — the point
        # is only that the endpoint hands its request id down when it does.
        if response.status_code != 503:
            request_id = response.headers["X-Request-Id"]
            jobs = action_log.recent(action="job.refresh")
            assert jobs and jobs[0].request_id == request_id

    @pytest.mark.asyncio
    async def test_failing_refresh_is_recorded_as_failed_with_the_error(self) -> None:
        """A background job accepted with 202 must still report how it ended."""
        from app.services.cache import TTLCache
        from app.services.refresh_service import RefreshService

        service = ActionLogService(to_file=False)
        refresh = RefreshService(
            companies=[],
            stooq=None,
            history_cache=TTLCache(),
            ranking_cache=TTLCache(),
            action_log=service,
        )

        async def boom(full: bool) -> None:
            raise RuntimeError("Yahoo unreachable")

        refresh._do_run = boom  # type: ignore[assignment]
        await refresh.run(trigger="manual")

        failed = service.recent(action="job.refresh")[0]
        assert failed.outcome == OUTCOME_FAILED
        assert "Yahoo unreachable" in failed.detail["error"]
        # The status endpoint keeps agreeing with the log.
        assert refresh.status().last_error == "Yahoo unreachable"


class TestIngestOutcome:
    """When the download step is reported as FAILED rather than finished.

    The verdict has to survive an ordinary night. GET /api/admin/logs/summary
    is the screen meant to surface a genuinely broken run, and marking the whole
    ingest failed because one ticker in 288 hiccuped would light it up most
    nights — which teaches its only reader to ignore it.
    """

    @staticmethod
    def _stats(**kwargs) -> IngestStats:
        base = {"companies": 288, "fetched": 288, "skipped": 0, "failed": 0}
        return IngestStats(**{**base, **kwargs})

    def test_a_clean_run_is_finished(self) -> None:
        assert ingest_outcome(self._stats()) == OUTCOME_FINISHED

    def test_one_flaky_ticker_out_of_288_is_still_finished(self) -> None:
        stats = self._stats(fetched=287, failed=1)
        assert ingest_outcome(stats) == OUTCOME_FINISHED
        # Nothing is hidden — the counters ride in the entry either way.
        assert stats.as_detail()["failed"] == 1

    def test_a_handful_of_dead_symbols_is_still_finished(self) -> None:
        """Renamed/withdrawn listings are skipped, not failed, by design."""
        assert ingest_outcome(self._stats(fetched=283, skipped=5)) == OUTCOME_FINISHED

    def test_a_tenth_of_the_universe_failing_is_a_failure(self) -> None:
        assert ingest_outcome(self._stats(fetched=238, failed=50)) == OUTCOME_FAILED

    def test_fetching_nothing_at_all_is_a_failure(self) -> None:
        """Dead network, wrong symbol list, unreachable database."""
        assert ingest_outcome(self._stats(fetched=0, skipped=288)) == OUTCOME_FAILED

    def test_an_empty_universe_is_not_a_failure(self) -> None:
        assert (
            ingest_outcome(IngestStats(companies=0, fetched=0)) == OUTCOME_FINISHED
        )

    @pytest.mark.asyncio
    async def test_the_ingest_entry_carries_the_softer_verdict(self) -> None:
        """End to end: a run with one casualty logs `finished`, with counters."""
        from app.services.cache import TTLCache
        from app.services.refresh_service import RefreshService

        class _OneBadTicker:
            async def run(self, full: bool = False) -> IngestStats:
                return IngestStats(companies=288, fetched=287, failed=1)

        service = ActionLogService(to_file=False)
        refresh = RefreshService(
            companies=[],
            stooq=None,
            history_cache=TTLCache(),
            ranking_cache=TTLCache(),
            ingest=_OneBadTicker(),  # type: ignore[arg-type]
            action_log=service,
        )
        await refresh.run(trigger="nightly")

        entry = service.recent(action="job.ingest")[0]
        assert entry.outcome == OUTCOME_FINISHED
        assert entry.detail["failed"] == 1
        assert entry.detail["fetched"] == 287


# ── Reading it back: GET /api/admin/logs ─────────────────────────────────────


class TestAdminLogEndpoints:
    def test_logs_endpoint_returns_recent_actions(self) -> None:
        with TestClient(app) as client:
            client.get("/api/stocks")
            response = client.get("/api/admin/logs")
        assert response.status_code == 200
        body = response.json()
        # No DATABASE_URL in the test suite, so the buffer is the source.
        assert body["source"] == "memory"
        assert body["totalCount"] >= 1
        assert any(item["action"] == "/api/stocks" for item in body["items"])
        assert response.headers["X-Total-Count"] == str(body["totalCount"])

    def test_logs_endpoint_filters_by_action_and_kind(self) -> None:
        with TestClient(app) as client:
            client.get("/api/stocks")
            action_log.log_job("job.refresh", OUTCOME_FINISHED)
            jobs = client.get("/api/admin/logs?kind=job").json()
            requests = client.get("/api/admin/logs?action=/api/stocks").json()
        assert all(item["kind"] == "job" for item in jobs["items"])
        assert any(item["action"] == "job.refresh" for item in jobs["items"])
        assert all("/api/stocks" in item["action"] for item in requests["items"])

    def test_logs_endpoint_paginates(self) -> None:
        # Filtered to the company-list calls: reading the log is itself a
        # recorded action, so an unfiltered page 2 would be shifted by the
        # page-1 request that had just been logged.
        with TestClient(app) as client:
            for _ in range(5):
                client.get("/api/stocks")
            page1 = client.get("/api/admin/logs?action=/api/stocks&pageSize=2").json()
            page2 = client.get(
                "/api/admin/logs?action=/api/stocks&pageSize=2&page=2"
            ).json()
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        ids1 = {i["requestId"] for i in page1["items"]}
        ids2 = {i["requestId"] for i in page2["items"]}
        assert not (ids1 & ids2)

    def test_summary_reports_where_logs_are_saved_and_last_job_outcomes(self) -> None:
        with TestClient(app) as client:
            client.get("/api/stocks")
            action_log.log_job("job.ingest", OUTCOME_FAILED, detail={"error": "boom"})
            body = client.get("/api/admin/logs/summary").json()

        assert body["enabled"] is True
        assert body["source"] == "memory"
        assert body["totalInWindow"] >= 1
        assert body["byOutcome"]
        last = {job["action"]: job for job in body["lastJobs"]}
        assert last["job.ingest"]["outcome"] == OUTCOME_FAILED
        assert last["job.ingest"]["detail"]["error"] == "boom"

    def test_summary_window_excludes_older_entries(self) -> None:
        stale = ActionLogEntry(
            action="job.ancient",
            kind="job",
            started_at=datetime.now(tz=UTC) - timedelta(days=5),
        )
        action_log.record(stale)
        with TestClient(app) as client:
            body = client.get("/api/admin/logs/summary?hours=1").json()
        assert "job.ancient" not in {job["action"] for job in body["lastJobs"]}


# ── The database writer ───────────────────────────────────────────────────────


class _FakeLogRepo:
    """Stands in for ActionLogRepository — records what it was asked to write."""

    def __init__(self, fail: bool = False) -> None:
        self.batches: list[list[ActionLogEntry]] = []
        self.pruned_before: datetime | None = None
        self.fail = fail

    async def insert_many(self, entries: list[ActionLogEntry]) -> None:
        if self.fail:
            raise RuntimeError("database down")
        self.batches.append(list(entries))

    async def prune(self, older_than: datetime) -> int:
        self.pruned_before = older_than
        return 0


class TestDatabaseWriter:
    @pytest.mark.asyncio
    async def test_entries_are_batched_into_the_database(self) -> None:
        service = ActionLogService(to_file=False)
        repo = _FakeLogRepo()
        await service.start_db_writer(repo, retention_days=30)
        for i in range(5):
            service.record(ActionLogEntry(action=f"/api/x/{i}"))
        await asyncio.sleep(0.05)
        await service.stop_db_writer()

        written = [e.action for batch in repo.batches for e in batch]
        assert sorted(written) == [f"/api/x/{i}" for i in range(5)]
        assert service.db_written_count == 5

    @pytest.mark.asyncio
    async def test_stop_flushes_what_is_still_queued(self) -> None:
        """A shutdown is exactly when the tail of the log matters."""
        service = ActionLogService(to_file=False)
        repo = _FakeLogRepo()
        await service.start_db_writer(repo, retention_days=0)
        service.record(ActionLogEntry(action="/api/last-gasp"))
        await service.stop_db_writer()
        assert any(
            e.action == "/api/last-gasp" for batch in repo.batches for e in batch
        )

    @pytest.mark.asyncio
    async def test_database_failure_does_not_break_recording(self) -> None:
        service = ActionLogService(to_file=False)
        await service.start_db_writer(_FakeLogRepo(fail=True), retention_days=0)
        service.record(ActionLogEntry(action="/api/stocks"))
        await asyncio.sleep(0.05)
        await service.stop_db_writer()
        # The in-memory record is intact even though the DB write failed.
        assert len(service.recent()) == 1

    @pytest.mark.asyncio
    async def test_full_queue_drops_instead_of_blocking(self) -> None:
        """The API must stay fast even if the log's writer stalls."""
        from app.services import action_log as module

        service = ActionLogService(to_file=False)
        service._queue = asyncio.Queue(maxsize=2)
        for i in range(10):
            service.record(ActionLogEntry(action=f"/api/x/{i}"))
        assert service.dropped_count == 8
        assert service.recorded_count == 10
        assert module._QUEUE_MAX > 0  # the real bound is generous

    @pytest.mark.asyncio
    async def test_recording_from_a_worker_thread_reaches_the_database(self) -> None:
        """record() is reachable off the event loop and must survive it.

        The error tracker sits on the ROOT logger, so a ``logger.error()`` from
        a worker thread — the market-data client runs yfinance in threads —
        lands here while the drain worker is parked in ``await queue.get()``.
        ``asyncio.Queue.put_nowait`` would complete that waiter's Future
        directly from the wrong thread; the entry has to be handed to the loop
        instead. Nothing may be dropped or lost on the way.
        """
        service = ActionLogService(to_file=False)
        repo = _FakeLogRepo()
        await service.start_db_writer(repo, retention_days=0)

        done = threading.Event()

        def worker() -> None:
            for i in range(20):
                service.record(ActionLogEntry(action=f"/api/thread/{i}"))
            done.set()

        thread = threading.Thread(target=worker, name="off-loop-recorder")
        thread.start()
        while not done.is_set():
            # Yield to the loop so it can run the handed-over callbacks.
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        await service.stop_db_writer()
        thread.join(timeout=5)

        written = {e.action for batch in repo.batches for e in batch}
        assert written == {f"/api/thread/{i}" for i in range(20)}
        assert service.dropped_count == 0
        # The in-process buffer took them all too.
        assert len(service.recent()) == 20

    @pytest.mark.asyncio
    async def test_retention_prune_uses_the_configured_window(self) -> None:
        service = ActionLogService(to_file=False)
        repo = _FakeLogRepo()
        await service.start_db_writer(repo, retention_days=7)
        service.record(ActionLogEntry(action="/api/x"))
        await asyncio.sleep(0.05)
        await service.stop_db_writer()

        assert repo.pruned_before is not None
        age = datetime.now(tz=UTC) - repo.pruned_before
        assert timedelta(days=6, hours=23) < age < timedelta(days=7, hours=1)
