"""Daily market-data ingestion job.

``IngestService`` is the unit of work: given a stooq client, a repository, and
the two in-memory caches, it fetches OHLCV data for all tracked companies and
persists it. It is called:

  * On startup (if today's data is missing from the DB).
  * By the APScheduler ``AsyncIOScheduler`` every day at 18:00 Warsaw time
    (one hour after the GPW close at 17:05), when stooq.pl has published the
    final EOD bars.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.analysis.corporate_actions import detect_adjustment
from app.db.base import DB_SCAN_CONCURRENCY
from app.db.repository import QuoteRepository
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.stooq_client import StooqClient
from app.services.yahoo_finance_client import YahooFinanceClient

logger = logging.getLogger(__name__)

_WARSAW = ZoneInfo("Europe/Warsaw")

# How many historical days to request from stooq on a *full* (bootstrap) ingest.
_FULL_HISTORY_DAYS = 400
# On the routine daily ingest, fetch only the last few days to cover late
# corrections published by stooq after the initial EOD snapshot.
#
# The overlap this creates with data already stored is also what makes
# corporate actions detectable: a split or dividend restates the provider's
# whole history, so the re-fetched bars stop matching the stored ones. See
# app/analysis/corporate_actions.py.
_INCREMENTAL_DAYS = 5
# How far back to reach when a ticker's stored history ends *before* the normal
# incremental window — the app was offline for a few days, say. Fetching only
# the last five days would then leave a hole in the series AND, because nothing
# overlaps, no bars to compare, so an adjustment made during the outage would go
# unnoticed. Capped at the bootstrap window so a long-suspended listing cannot
# turn every night into a full history download.
_GAP_OVERLAP_DAYS = 5
# Max concurrent stooq requests (mirrors ranking_service).
_MAX_CONCURRENT = 4
# How many failing tickers a run reports by name in its log entry. The rest are
# only counted — a run where every symbol failed must not write a 290-name list
# into the audit trail.
_MAX_REPORTED_FAILURES = 20


@dataclass(slots=True)
class IngestStats:
    """What one ingest run actually did — the audit trail's raw material.

    Returned by :meth:`IngestService.run` so the caller (``RefreshService``)
    can record it. Without these numbers a nightly run that quietly fetched
    nothing looks exactly like one that worked: the job "completed" either way.
    """

    full: bool = False
    companies: int = 0
    # Tickers whose fetch returned at least one bar.
    fetched: int = 0
    # Tickers the data provider could not serve (renamed, withdrawn, dead
    # symbol) — expected in small numbers, alarming in large ones.
    skipped: int = 0
    # Tickers that failed for any other reason (network, parse, DB write).
    failed: int = 0
    bars_written: int = 0
    # Tickers whose stored history was rebuilt because the data provider had
    # restated it — a split, a dividend adjustment or a correction. Normally
    # zero; a name appearing here is the audit trail's record that this stock's
    # past prices changed today, which is worth being able to look up when a
    # rating moves for no visible reason.
    adjusted: int = 0
    adjusted_tickers: list[str] = field(default_factory=list)
    fundamentals_run: bool = False
    duration_ms: float = 0.0
    failures: list[str] = field(default_factory=list)

    def as_detail(self) -> dict:
        """The JSON-friendly form stored in an action-log entry."""
        return {
            "full": self.full,
            "companies": self.companies,
            "fetched": self.fetched,
            "skipped": self.skipped,
            "failed": self.failed,
            "barsWritten": self.bars_written,
            "adjusted": self.adjusted,
            "adjustedTickers": self.adjusted_tickers[:_MAX_REPORTED_FAILURES],
            "fundamentalsRun": self.fundamentals_run,
            "failures": self.failures[:_MAX_REPORTED_FAILURES],
        }


class IngestService:
    """Orchestrates stooq.pl → database ingestion for all tracked companies."""

    def __init__(
        self,
        companies: list[GpwCompany],
        stooq: StooqClient | YahooFinanceClient,
        repo: QuoteRepository,
        history_cache: TTLCache,
        ranking_cache: TTLCache,
    ) -> None:
        self._companies = companies
        self._stooq = stooq
        self._repo = repo
        self._history_cache = history_cache
        self._ranking_cache = ranking_cache
        self._running = asyncio.Lock()

    async def run(self, full: bool = False) -> IngestStats | None:
        """Fetch and persist data for every tracked ticker.

        Args:
            full:  When ``True``, requests up to ``_FULL_HISTORY_DAYS`` days
                   (used on first run to bootstrap the DB).  When ``False``
                   (the normal nightly run), only the last few days are
                   refreshed — faster and lighter on stooq.pl.

        Returns:
            What the run did (:class:`IngestStats`), or ``None`` when another
            run was already in progress and this trigger was dropped.
        """
        if self._running.locked():
            logger.warning("Ingest already running — skipping duplicate trigger.")
            return None
        async with self._running:
            return await self._do_run(full=full)

    async def _do_run(self, full: bool = False) -> IngestStats:
        """Internal: actual ingest body, called under ``_running`` lock."""
        started = time.perf_counter()
        stats = IngestStats(full=full, companies=len(self._companies))
        today = datetime.now(_WARSAW).date()
        days = _FULL_HISTORY_DAYS if full else _INCREMENTAL_DAYS
        from_date = today - timedelta(days=days)

        logger.info(
            "Starting %s ingest — %d companies from %s.",
            "FULL" if full else "incremental",
            len(self._companies),
            from_date,
        )

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
        # The persist step runs outside the fetch gate (a slow write must not
        # hold a Yahoo slot), so it needs a gate of its own: ~290 simultaneous
        # writes against a 15-connection pool would queue until they time out.
        # See DB_SCAN_CONCURRENCY in app/db/base.py for the sizing.
        db_semaphore = asyncio.Semaphore(DB_SCAN_CONCURRENCY)

        async def ingest_one(company: GpwCompany) -> None:
            ticker = company.ticker

            # What the database already holds for the window about to be
            # fetched. Two uses: it is the yardstick the fresh bars are checked
            # against (see _check_and_repair), and its absence says the stored
            # history stops short of the window.
            try:
                async with db_semaphore:
                    stored = await self._repo.get_quotes(ticker, from_date)
            except Exception as exc:  # noqa: BLE001
                # Reading is only needed for the corporate-action check; losing
                # it must not cost the night's data, so the ingest carries on
                # exactly as it did before this check existed.
                logger.warning("Could not read stored bars for %s: %s", ticker, exc)
                stored = []

            effective_from = from_date
            if not stored and not full:
                effective_from = await self._widen_for_gap(
                    ticker, from_date, today, db_semaphore
                )
                if effective_from != from_date:
                    try:
                        async with db_semaphore:
                            stored = await self._repo.get_quotes(ticker, effective_from)
                    except Exception:  # noqa: BLE001
                        logger.debug("Could not re-read stored bars for %s.", ticker)

            async with semaphore:
                try:
                    quotes = await self._stooq.get_daily_history(
                        ticker, from_date=effective_from
                    )
                except StooqAccessError as exc:
                    logger.warning("Ingest skipped for %s: %s", ticker, exc)
                    stats.skipped += 1
                    stats.failures.append(ticker)
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ingest error for %s: %s", ticker, exc)
                    stats.failed += 1
                    stats.failures.append(ticker)
                    return

                # Still inside the fetch gate: a repair is a second download
                # and must obey the same concurrency budget.
                quotes, repaired = await self._check_and_repair(
                    ticker, stored, quotes, stats
                )
                if quotes is None:
                    return

            if quotes:
                try:
                    async with db_semaphore:
                        await self._repo.upsert_quotes(ticker, quotes)
                        if repaired:
                            await self._resync_snapshots(ticker)
                except Exception as exc:  # noqa: BLE001
                    # A write that fails is a data loss the run must own up to:
                    # before this, the ticker simply went missing and the job
                    # still reported success.
                    logger.error("Ingest write failed for %s: %s", ticker, exc)
                    stats.failed += 1
                    stats.failures.append(ticker)
                    return
                stats.fetched += 1
                stats.bars_written += len(quotes)
                if repaired:
                    stats.adjusted += 1
                    stats.adjusted_tickers.append(ticker)
                logger.debug("Persisted %d bars for %s.", len(quotes), ticker)

        await asyncio.gather(*(ingest_one(c) for c in self._companies))

        # Keep company metadata in sync with the seed file.
        try:
            await self._repo.upsert_companies(self._companies)
        except Exception:
            logger.exception("Failed to sync company metadata to DB; continuing.")

        # Fetch and persist financial fundamentals + quarterly reports +
        # cash-flow (capex) data. Only done on full (bootstrap) ingests or once
        # per week (Monday) to avoid hammering Yahoo Finance every day — these
        # figures only change when a company publishes a report. The extra
        # backfill check makes a newly added fundamentals table fill itself on
        # the next refresh instead of waiting for the next Monday.
        run_fundamentals = (
            full or today.weekday() == 0 or await self._fundamentals_missing()
        )
        if run_fundamentals:
            logger.info("Fetching financial fundamentals for %d companies.", len(self._companies))
            await self._ingest_fundamentals(semaphore)
            stats.fundamentals_run = True

        # Flush in-memory caches so the next API call reads the freshly persisted data.
        self._history_cache.clear()
        self._ranking_cache.clear()

        stats.duration_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "Ingest complete: %d fetched, %d skipped, %d failed, %d bars. "
            "In-memory caches cleared.",
            stats.fetched,
            stats.skipped,
            stats.failed,
            stats.bars_written,
        )
        return stats

    # ── Corporate actions (splits, dividends) ─────────────────────────────────

    async def _widen_for_gap(
        self,
        ticker: str,
        from_date: date,
        today: date,
        db_semaphore: asyncio.Semaphore,
    ) -> date:
        """Reach further back when a ticker's stored history stops before the window.

        Returns the date the fetch should start from — ``from_date`` unchanged
        in the ordinary case (nothing stored at all, or the stored bars already
        reach into the window).
        """
        try:
            async with db_semaphore:
                span = await self._repo.get_quote_date_range(ticker)
        except Exception:  # noqa: BLE001
            logger.debug("Could not read the stored date range for %s.", ticker)
            return from_date

        # Nothing stored: this is a new ticker, and the normal window is right.
        # Stored bars newer than the window's start: they simply were not
        # returned above (a suspended listing with no recent sessions, say), and
        # widening would not add overlap.
        if span is None or span[1] >= from_date:
            return from_date

        widened = max(
            span[1] - timedelta(days=_GAP_OVERLAP_DAYS),
            today - timedelta(days=_FULL_HISTORY_DAYS),
        )
        if widened >= from_date:
            return from_date

        logger.info(
            "Stored history for %s ends %s, before the %s ingest window — "
            "fetching from %s to close the gap.",
            ticker,
            span[1],
            from_date,
            widened,
        )
        return widened

    async def _check_and_repair(
        self,
        ticker: str,
        stored: list[StooqDailyQuote],
        fetched: list[StooqDailyQuote],
        stats: IngestStats,
    ) -> tuple[list[StooqDailyQuote] | None, bool]:
        """Guard against writing new-scale bars into an old-scale history.

        A split or a dividend makes the provider restate everything it has ever
        served for that stock. Topping up such a series with the few fresh bars
        is what puts a phantom 90%-crash candle in the middle of it, so when the
        overlap disagrees the whole stored history is downloaded again instead.

        Returns ``(bars_to_write, repaired)``. ``bars_to_write`` is ``None``
        when the run must write nothing for this ticker: that happens only if
        the repair download fails, and leaving the history one day stale is far
        better than leaving it internally inconsistent.
        """
        check = detect_adjustment(stored, fetched)
        if not check.adjusted:
            return fetched, False

        logger.warning(
            "%s: the data provider restated this stock's history — %s. "
            "Re-downloading its stored history so the series stays on one scale.",
            ticker.upper(),
            check.reason,
        )

        try:
            span = await self._repo.get_quote_date_range(ticker)
        except Exception:  # noqa: BLE001
            span = None
        # Without a known first bar, re-fetch as much as a bootstrap would.
        repair_from = span[0] if span else (fetched[0].date - timedelta(days=1))

        try:
            repaired_bars = await self._stooq.get_daily_history(
                ticker, from_date=repair_from
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Could not re-download %s from %s after a corporate action (%s). "
                "Skipping tonight's write for this ticker; its stored history "
                "stays on one scale and the next run will retry.",
                ticker,
                repair_from,
                exc,
            )
            stats.failed += 1
            stats.failures.append(ticker)
            return None, False

        if not repaired_bars:
            logger.error(
                "Re-download of %s returned nothing; skipping tonight's write.",
                ticker,
            )
            stats.failed += 1
            stats.failures.append(ticker)
            return None, False

        logger.info(
            "Rebuilt %s: %d bars from %s onwards, all on the current scale.",
            ticker.upper(),
            len(repaired_bars),
            repaired_bars[0].date,
        )
        return repaired_bars, True

    async def _resync_snapshots(self, ticker: str) -> None:
        """Re-point the stored rating snapshots at the rebuilt bars.

        Runs inside the caller's write, right after the repaired bars land. The
        rating itself never needs fixing — VSA reads a bar against its
        neighbours, so it is blind to the scale they are all drawn on — but the
        closing price stored beside it for the chart is not.
        """
        try:
            updated = await self._repo.resync_rating_snapshot_closes(ticker)
        except Exception:  # noqa: BLE001
            # The bars are what matter; a stale price on the rating-history
            # chart is not worth failing the ticker's whole write for.
            logger.warning("Could not re-scale %s rating snapshots.", ticker)
            return
        if updated:
            logger.info(
                "Re-scaled %d stored rating snapshots for %s.", updated, ticker.upper()
            )

    async def _fundamentals_missing(self) -> bool:
        """True when no cash-flow data is stored yet (first run after upgrade).

        Cheap: an existence probe ("is there a single row?"), not a read of the
        whole table. Without it the capex screen would stay empty until the
        next Monday on an existing installation.
        """
        try:
            return not await self._repo.has_cashflow()
        except Exception:  # noqa: BLE001 — a probe must never abort the ingest
            logger.debug("Could not check stored cash-flow data; skipping backfill.")
            return False

    async def _ingest_fundamentals(self, semaphore: asyncio.Semaphore) -> None:
        """Fetch metrics, quarterly reports and cash flow for all companies."""

        async def fetch_one(company: GpwCompany) -> None:
            async with semaphore:
                try:
                    metrics = await self._stooq.get_fundamentals(company.ticker)
                    await self._repo.upsert_fundamentals(company.ticker, metrics)
                except Exception:
                    logger.debug(
                        "Could not update fundamentals for %s.", company.ticker
                    )

                try:
                    reports = await self._stooq.get_quarterly_reports(company.ticker)
                    if reports:
                        await self._repo.upsert_quarterly(company.ticker, reports)
                except Exception:
                    logger.debug(
                        "Could not update quarterly reports for %s.", company.ticker
                    )

                # Capital expenditure (the /capex screen). Older data sources
                # (StooqClient) have no cash-flow support at all, so the call
                # is optional rather than assumed.
                if not hasattr(self._stooq, "get_cashflow_periods"):
                    return
                try:
                    periods = await self._stooq.get_cashflow_periods(company.ticker)
                    if periods:
                        await self._repo.upsert_cashflow(company.ticker, periods)
                except Exception:
                    logger.debug(
                        "Could not update cash-flow data for %s.", company.ticker
                    )

        await asyncio.gather(*(fetch_one(c) for c in self._companies))

    async def needs_bootstrap(self) -> bool:
        """Return True if fewer than 90% of tracked companies have today's data.

        This runs during startup, before anything else has warmed up, and asks
        one question per tracked company. Firing all ~290 of them at once at a
        15-connection pool means most of them queue for a connection and the
        slowest ones time out — so the app's very first act would be to conclude
        (wrongly) that the database is empty and kick off a full bootstrap
        ingest. The probes are throttled to the same budget every other
        full-universe scan uses (DB_SCAN_CONCURRENCY, app/db/base.py); they are
        tiny queries, so the wall-clock cost of queueing them is negligible.
        """
        if not self._companies:
            return False

        db_semaphore = asyncio.Semaphore(DB_SCAN_CONCURRENCY)

        async def probe(ticker: str) -> bool:
            async with db_semaphore:
                return await self._repo.has_today_data(ticker)

        checks = await asyncio.gather(*(probe(c.ticker) for c in self._companies))
        return sum(checks) < len(self._companies) * 0.9


def build_scheduler(
    refresh_service,  # RefreshService (duck-typed to avoid a circular import)
    hour: int = 18,
    minute: int = 0,
) -> AsyncIOScheduler:
    """Create (but don't start) the nightly refresh scheduler.

    The scheduler fires the full *daily* refresh pipeline (incremental Yahoo
    ingest → ranking recompute → rating snapshots). The bootstrap (full)
    refresh is handled separately in the app lifespan.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        refresh_service.run,
        trigger=CronTrigger(
            hour=hour,
            minute=minute,
            timezone="Europe/Warsaw",
        ),
        id="daily_ingest",
        name="GPW daily data refresh (ingest + ranking + rating snapshots)",
        replace_existing=True,
        # If the server was down at trigger time, run the missed job within 1 h.
        misfire_grace_time=3_600,
    )
    return scheduler
