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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.repository import QuoteRepository
from app.models import GpwCompany
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
_INCREMENTAL_DAYS = 5
# Max concurrent stooq requests (mirrors ranking_service).
_MAX_CONCURRENT = 4


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

    async def run(self, full: bool = False) -> None:
        """Fetch and persist data for every tracked ticker.

        Args:
            full:  When ``True``, requests up to ``_FULL_HISTORY_DAYS`` days
                   (used on first run to bootstrap the DB).  When ``False``
                   (the normal nightly run), only the last few days are
                   refreshed — faster and lighter on stooq.pl.
        """
        if self._running.locked():
            logger.warning("Ingest already running — skipping duplicate trigger.")
            return
        async with self._running:
            await self._do_run(full=full)

    async def _do_run(self, full: bool = False) -> None:
        """Internal: actual ingest body, called under ``_running`` lock."""
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

        async def ingest_one(company: GpwCompany) -> None:
            async with semaphore:
                try:
                    quotes = await self._stooq.get_daily_history(
                        company.ticker, from_date=from_date
                    )
                except StooqAccessError as exc:
                    logger.warning("Ingest skipped for %s: %s", company.ticker, exc)
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ingest error for %s: %s", company.ticker, exc)
                    return

            if quotes:
                await self._repo.upsert_quotes(company.ticker, quotes)
                logger.debug("Persisted %d bars for %s.", len(quotes), company.ticker)

        await asyncio.gather(*(ingest_one(c) for c in self._companies))

        # Keep company metadata in sync with the seed file.
        try:
            await self._repo.upsert_companies(self._companies)
        except Exception:
            logger.exception("Failed to sync company metadata to DB; continuing.")

        # Fetch and persist financial fundamentals + quarterly reports.
        # Only done on full (bootstrap) ingests or once per week (Monday) to
        # avoid hammering Yahoo Finance every day.
        run_fundamentals = full or today.weekday() == 0  # Monday = 0
        if run_fundamentals:
            logger.info("Fetching financial fundamentals for %d companies.", len(self._companies))
            await self._ingest_fundamentals(semaphore)

        # Flush in-memory caches so the next API call reads the freshly persisted data.
        self._history_cache.clear()
        self._ranking_cache.clear()

        logger.info("Ingest complete. In-memory caches cleared.")

    async def _ingest_fundamentals(self, semaphore: asyncio.Semaphore) -> None:
        """Fetch financial metrics and quarterly reports for all companies."""

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

        await asyncio.gather(*(fetch_one(c) for c in self._companies))

    async def needs_bootstrap(self) -> bool:
        """Return True if fewer than 90% of tracked companies have today's data."""
        if not self._companies:
            return False
        checks = await asyncio.gather(
            *(self._repo.has_today_data(c.ticker) for c in self._companies)
        )
        return sum(checks) < len(self._companies) * 0.9


def build_scheduler(
    ingest_service: IngestService,
    hour: int = 18,
    minute: int = 0,
) -> AsyncIOScheduler:
    """Create (but don't start) the nightly ingestion scheduler.

    The scheduler fires a *daily, incremental* ingest. The bootstrap (full)
    ingest is handled separately in the app lifespan.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        ingest_service.run,
        trigger=CronTrigger(
            hour=hour,
            minute=minute,
            timezone="Europe/Warsaw",
        ),
        id="daily_ingest",
        name="GPW daily EOD ingestion",
        replace_existing=True,
        # If the server was down at trigger time, run the missed job within 1 h.
        misfire_grace_time=3_600,
    )
    return scheduler
