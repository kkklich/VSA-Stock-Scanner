"""Data-refresh pipeline: Yahoo ingest → VSA ranking → daily rating snapshots.

``RefreshService`` is the single entry point for refreshing the application's
data. It runs in exactly two situations:

  * the nightly APScheduler job (18:00 Europe/Warsaw, after the GPW close), and
  * the user pressing the **Refresh** button in the UI
    (``POST /api/stocks/refresh``).

Outside these two triggers no Yahoo Finance calls are made for data that is
already in the database — the API serves everything from PostgreSQL and the
in-process caches.

One full run:

  1. Ingest fresh EOD bars from Yahoo Finance into PostgreSQL
     (skipped when the app runs without a database — caches are just cleared
     so the ranking recomputes from a fresh live fetch).
  2. Recompute the full VSA ranking with the DEFAULT engine settings and warm
     the ranking cache, so the first page load after a refresh is instant.
  3. Persist one rating snapshot per (ticker, day) to ``rating_snapshots``.
     Every run also (re)writes the ratings for the whole loaded history
     window, so the "rating over time" chart is populated immediately after
     the very first refresh instead of growing one point per day.

The service also tracks its own status (idle/running, last refresh time,
last error) for the ``GET /api/stocks/refresh/status`` endpoint, and records
every run in the **action log** (``app/services/action_log.py``) as
``job.refresh`` / ``job.ingest`` entries — started, finished or failed, with
what the run actually did. A background job is accepted with a 202 long before
it succeeds or fails, so its HTTP status says nothing about the outcome; those
entries are what make a nightly run that quietly fetched nothing visible.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.analysis.statistics import median_volume_pln
from app.analysis.vsa import compute_rating, detect_signals, verdict_from_signals
from app.config import settings
from app.db.repository import QuoteRepository
from app.jobs.daily_ingest import IngestService
from app.models import (
    GpwCompany,
    RatingPoint,
    RefreshStatusResponse,
    StockRankingItem,
    StooqDailyQuote,
)
from app.services.action_log import (
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_SKIPPED,
    OUTCOME_STARTED,
    ActionLogService,
)
from app.services.cache import TTLCache
from app.services.ranking_service import CONTEXT_HISTORY_DAYS, compute_ranking
from app.services.stooq_client import StooqClient
from app.services.yahoo_finance_client import YahooFinanceClient

logger = logging.getLogger(__name__)

_WARSAW = ZoneInfo("Europe/Warsaw")

# Mirror ranking_service: how far back the ranking (and thus the snapshot
# backfill) looks. Snapshots are written for every trading day in this window.
_HISTORY_DAYS = 120
# A stock needs this many bars before its historical ratings mean anything.
_MIN_BARS = 25
_MIN_MEDIAN_VOLUME_PLN = 100_000.0


class RefreshService:
    """Orchestrates a full data refresh and reports its status."""

    def __init__(
        self,
        companies: list[GpwCompany],
        stooq: StooqClient | YahooFinanceClient,
        history_cache: TTLCache,
        ranking_cache: TTLCache,
        repo: QuoteRepository | None = None,
        ingest: IngestService | None = None,
        action_log: ActionLogService | None = None,
    ) -> None:
        self._companies = companies
        self._stooq = stooq
        self._history_cache = history_cache
        self._ranking_cache = ranking_cache
        self._repo = repo
        self._ingest = ingest
        # Optional: the pipeline works without it, so tests and any other
        # caller can build a RefreshService without wiring up a log.
        self._action_log = action_log
        self._running = asyncio.Lock()
        # Id of the HTTP request that started the run in progress, if any.
        self._run_request_id: str | None = None
        self._task: asyncio.Task | None = None

        # Status, exposed via GET /api/stocks/refresh/status.
        self.last_started_at: datetime | None = None
        self.last_refresh_at: datetime | None = None
        self.last_error: str | None = None
        self.stocks_ranked: int | None = None
        # How many stocks got rating snapshots written on the last run — kept
        # so the run's log entry can report it.
        self.snapshots_written: int | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running.locked()

    def status(self) -> RefreshStatusResponse:
        """Current pipeline status for the /refresh endpoints."""
        return RefreshStatusResponse(
            state="running" if self.is_running else "idle",
            last_started_at=(
                self.last_started_at.isoformat() if self.last_started_at else None
            ),
            last_refresh_at=(
                self.last_refresh_at.isoformat() if self.last_refresh_at else None
            ),
            last_error=self.last_error,
            stocks_ranked=self.stocks_ranked,
            db_enabled=self._repo is not None,
        )

    def start(
        self,
        full: bool = False,
        trigger: str = "manual",
        request_id: str | None = None,
    ) -> bool:
        """Kick off a refresh in the background.

        ``trigger`` says who asked — ``manual`` (the Refresh button),
        ``bootstrap`` (an empty database on startup) or ``nightly`` (the 18:00
        scheduler). It is recorded, so the log can tell an owner-initiated run
        from an automatic one. ``request_id`` carries the id of the HTTP call
        that pressed the button, so the request entry and the job entries it
        set off share one id in the action log.

        Returns ``True`` if a new run was started, ``False`` when one is
        already in progress (the in-flight run is left alone).
        """
        if self.is_running:
            self._log_job(
                "job.refresh",
                OUTCOME_SKIPPED,
                detail={"trigger": trigger, "reason": "already running"},
                request_id=request_id,
            )
            return False
        self._task = asyncio.create_task(
            self.run(full=full, trigger=trigger, request_id=request_id),
            name="data_refresh",
        )
        return True

    async def run(
        self,
        full: bool = False,
        trigger: str = "nightly",
        request_id: str | None = None,
    ) -> None:
        """Execute the full pipeline; safe to call from the scheduler.

        The scheduler calls this directly, so ``nightly`` is the default
        trigger — ``start()`` passes its own.
        """
        if self._running.locked():
            logger.warning("Refresh already running — skipping duplicate trigger.")
            self._log_job(
                "job.refresh",
                OUTCOME_SKIPPED,
                detail={"trigger": trigger, "reason": "already running"},
                request_id=request_id,
            )
            return
        async with self._running:
            self.last_started_at = datetime.now(tz=UTC)
            self.last_error = None
            started = time.perf_counter()
            # Held for the duration of the run so the ingest step's own entry
            # carries the same id as the refresh that contains it.
            self._run_request_id = request_id
            self._log_job(
                "job.refresh",
                OUTCOME_STARTED,
                detail={"trigger": trigger, "full": full},
                request_id=request_id,
            )
            try:
                await self._do_run(full=full)
                self.last_refresh_at = datetime.now(tz=UTC)
                self._log_job(
                    "job.refresh",
                    OUTCOME_FINISHED,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    detail={
                        "trigger": trigger,
                        "full": full,
                        "stocksRanked": self.stocks_ranked,
                        "snapshotsWritten": self.snapshots_written,
                        "dbEnabled": self._repo is not None,
                    },
                    request_id=request_id,
                )
            except Exception as exc:  # noqa: BLE001 — background job must not crash the app
                self.last_error = str(exc)
                logger.exception("Data refresh failed.")
                self._log_job(
                    "job.refresh",
                    OUTCOME_FAILED,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    detail={
                        "trigger": trigger,
                        "full": full,
                        "error": f"{type(exc).__name__}: {exc}"[:500],
                    },
                    request_id=request_id,
                )

    def _log_job(
        self,
        action: str,
        outcome: str,
        *,
        duration_ms: float | None = None,
        detail: dict | None = None,
        request_id: str | None = None,
    ) -> None:
        """Record one pipeline event, if an action log was wired in.

        ``request_id`` defaults to the id of the run in progress, so a step
        logged from inside the pipeline (the ingest) is tied to the refresh
        that contains it and, in turn, to the button press that started it.
        """
        if self._action_log is None:
            return
        self._action_log.log_job(
            action,
            outcome,
            duration_ms=duration_ms,
            detail=detail,
            request_id=request_id or self._run_request_id,
        )

    # ── Pipeline body ─────────────────────────────────────────────────────────

    async def _do_run(self, full: bool) -> None:
        today = datetime.now(_WARSAW).date()

        # 1. Fresh bars from Yahoo Finance.
        if self._ingest is not None:
            # Persists to PostgreSQL and clears both caches when done.
            stats = await self._ingest.run(full=full)
            if stats is not None:
                self._log_job(
                    "job.ingest",
                    OUTCOME_FINISHED if stats.failed == 0 else OUTCOME_FAILED,
                    duration_ms=stats.duration_ms,
                    detail=stats.as_detail(),
                )
            else:
                self._log_job(
                    "job.ingest",
                    OUTCOME_SKIPPED,
                    detail={"reason": "already running"},
                )
        else:
            # No DB: just drop the caches so the ranking below live-fetches.
            self._history_cache.clear()
            self._ranking_cache.clear()

        # 2. Recompute the ranking with DEFAULT settings and pre-warm the cache
        #    (the same key the /ranking endpoint uses for the default config).
        ranking = await compute_ranking(
            companies=self._companies,
            stooq=self._stooq,
            history_cache=self._history_cache,
            history_cache_ttl=settings.history_cache_seconds,
            repo=self._repo,
            today=today,
        )
        self._ranking_cache.set("ranking:full", ranking, settings.history_cache_seconds)
        self.stocks_ranked = len(ranking)
        logger.info("Refresh: ranking recomputed (%d stocks).", len(ranking))

        # 3. Persist rating snapshots so the rating's evolution can be charted.
        if self._repo is not None:
            self.snapshots_written = await self._snapshot_ratings(ranking, today)
        else:
            self.snapshots_written = None
            logger.info("Refresh: no database configured — rating history not stored.")

    async def _snapshot_ratings(
        self, ranking: list[StockRankingItem], today: date
    ) -> int:
        assert self._repo is not None
        from_date = today - timedelta(days=_HISTORY_DAYS)
        context_from = today - timedelta(days=CONTEXT_HISTORY_DAYS)
        written = 0

        for item in ranking:
            ticker = item.ticker.lower()
            try:
                quotes = await self._load_quotes(ticker, from_date, context_from)
                points = build_rating_points(quotes)
                if points:
                    await self._repo.upsert_rating_snapshots(ticker, points)
                    written += 1
            except Exception:
                logger.exception("Failed to snapshot ratings for %s.", ticker)

        logger.info(
            "Refresh: rating snapshots stored for %d/%d ranked stocks.",
            written,
            len(ranking),
        )
        return written

    async def _load_quotes(
        self, ticker: str, from_date: date, context_from: date
    ) -> list[StooqDailyQuote]:
        """Reuse the history the ranking step just loaded (cache → DB).

        The ranking caches the longer 52-week-context window (keyed by
        ``context_from``); snapshots only need the bars from ``from_date``
        on, so the cached list is sliced back down to the snapshot window.
        """
        cache_key = f"history:{ticker}:{context_from}:None"
        quotes: list[StooqDailyQuote] | None = self._history_cache.get(cache_key)
        if quotes is not None:
            return [q for q in quotes if q.date >= from_date]
        if self._repo is not None:
            return await self._repo.get_quotes(ticker, from_date)
        return []


def build_rating_points(quotes: list[StooqDailyQuote]) -> list[RatingPoint]:
    """Compute one rating snapshot per trading day from an OHLCV series.

    Uses the DEFAULT VSA settings so stored history stays comparable across
    days. Signal detection has no lookahead and ``compute_rating`` ignores
    signals dated after the as-of day, so the value for a past day matches
    what the engine would have reported on that day.
    """
    if len(quotes) < _MIN_BARS:
        return []
    if median_volume_pln(quotes) < _MIN_MEDIAN_VOLUME_PLN:
        return []

    signals = detect_signals(quotes)
    points: list[RatingPoint] = []
    for q in quotes:
        day = q.date
        # Both the rating and the verdict are fed the SAME list of signals that
        # had already happened by ``day``. ``compute_rating`` also ignores
        # future-dated signals internally, so passing the full list would give
        # the same numbers today — but only by accident, and an accident that
        # would break the moment either function's decay changed. Making the
        # "no lookahead" rule explicit is what guarantees a stored snapshot is
        # what the engine really would have said on that day.
        past_signals = [s for s in signals if s.date <= day]
        verdict, _ = verdict_from_signals(past_signals, day)
        points.append(
            RatingPoint(
                date=day,
                rating=compute_rating(past_signals, day),
                verdict=verdict,
                close=float(q.close),
            )
        )
    return points
