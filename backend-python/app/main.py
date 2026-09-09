"""StockPilot API application entry point.

Run locally with:
    uvicorn app.main:app --reload --port 5111

Lifespan sequence
-----------------
0. Open the action log's rotating file (the audit trail of every API call and
   background job - see app/services/action_log.py).
1. Open shared stooq HTTP client.
2. (If DATABASE_URL is set) Create async DB engine, conditionally create tables,
   build repo, and start the action log's database writer.
3. Bootstrap: if fewer than 90% of tickers have today's data in DB, trigger a
   full ingest in the background (non-blocking — first API call may still hit
   stooq.pl while ingest runs).
4. Start nightly APScheduler job (18:00 Warsaw time).
5. Yield (app is live).
6. Shutdown: stop scheduler, flush and stop the action log, dispose DB engine,
   close HTTP client.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.config import settings
from app.db.repository import QuoteRepository
from app.dependencies import (
    action_log,
    create_http_client,
    error_tracker,
    get_quote_repository,
    gpw_company_service,
    history_cache,
    ranking_cache,
    set_action_log_repository,
    set_data_health_repository,
    set_http_client,
    set_quote_repository,
    set_refresh_service,
    set_scheduler,
)
from app.routers import admin, stocks
from app.services.action_log import (
    OUTCOME_FINISHED,
    OUTCOME_STARTED,
    ActionLogMiddleware,
)
from app.services.error_tracker import ErrorTrackingHandler
from app.services.refresh_service import RefreshService
from app.services.yahoo_finance_client import YahooFinanceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# yfinance logs its own ERROR line for every symbol Yahoo cannot serve
# ("possibly delisted; no price data found"). Every call into it is already
# wrapped by YahooFinanceClient, which raises StooqAccessError, and each caller
# logs the skip itself with the ticker and the reason — so the library's line
# is a duplicate. Left at ERROR it also misreports the situation: a GPW listing
# that was renamed or withdrawn is an expected fact about the market, not a
# fault in this app, and a scan that handled it correctly should not print a
# screen of errors. Silence the library and keep our own message.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Columns added to an ALREADY-EXISTING table by a later version of the app.
# `create_all` can only create whole missing tables, so these are applied on
# startup with ADD COLUMN IF NOT EXISTS (idempotent — a no-op once present).
# Keep each entry in sync with the ORM model and its Alembic revision.
#   (table, column, SQL type)
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # 2026-07-21, alembic 002 — profitability ratios for the returns card.
    ("company_fundamentals", "return_on_equity", "DOUBLE PRECISION"),
    ("company_fundamentals", "return_on_assets", "DOUBLE PRECISION"),
)

# These identifiers are interpolated into a raw ALTER TABLE statement (there is
# no bind-parameter form for DDL identifiers), so they must never come from
# anything but the trusted constant above. This guard enforces that invariant:
# a plain SQL identifier for the table/column and an allow-listed column type.
# It makes the DDL injection-proof by construction even if a future edit is
# careless about where a value originates.
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_COLUMN_TYPES = frozenset(
    {"DOUBLE PRECISION", "INTEGER", "BIGINT", "TEXT", "BOOLEAN", "NUMERIC", "DATE"}
)


def _validate_ddl_column(table: str, column: str, coltype: str) -> None:
    """Reject anything that is not a bare identifier / allow-listed type."""
    if not _SQL_IDENTIFIER_RE.match(table):
        raise ValueError(f"Unsafe table identifier for DDL: {table!r}")
    if not _SQL_IDENTIFIER_RE.match(column):
        raise ValueError(f"Unsafe column identifier for DDL: {column!r}")
    if coltype.upper() not in _ALLOWED_COLUMN_TYPES:
        raise ValueError(f"Column type not on the DDL allow-list: {coltype!r}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── 0. Action log ───────────────────────────────────────────────
    # Opened before anything else, so the startup itself is on the record.
    action_log.open_file()
    # Error tracking rides on the logging the app already does: this handler
    # turns every ERROR-level line, from anywhere in the code, into a grouped
    # and counted error readable at GET /api/admin/errors. Attached to the root
    # logger, so no call site has to know it exists.
    error_handler = ErrorTrackingHandler(error_tracker)
    logging.getLogger().addHandler(error_handler)
    action_log.log_job(
        "job.startup",
        OUTCOME_STARTED,
        detail={"version": __version__, "dbConfigured": settings.db_enabled},
    )

    # ── 1. HTTP client ────────────────────────────────────────────────────────
    client = create_http_client()
    set_http_client(client)

    scheduler = None
    engine: AsyncEngine | None = None

    try:
        # ── 2. Database (optional) ────────────────────────────────────────────
        if settings.db_enabled:
            from sqlalchemy import text

            from app.db.action_log_repository import ActionLogRepository
            from app.db.base import Base, build_engine, build_session_factory
            from app.db.health_repository import DataHealthRepository
            from app.db.repository import PostgresQuoteRepository
            from app.jobs.daily_ingest import IngestService, build_scheduler

            engine = build_engine(settings.database_url)
            session_factory = build_session_factory(engine)

            # Retry connecting — PostgreSQL may still be starting up.
            _DB_RETRIES = 5
            _DB_RETRY_DELAY = 3.0
            db_connected = False
            for attempt in range(1, _DB_RETRIES + 1):
                try:
                    async with engine.connect() as _probe:
                        await _probe.execute(text("SELECT 1"))
                    db_connected = True
                    break
                except Exception as exc:
                    if attempt < _DB_RETRIES:
                        logger.warning(
                            "DB connection attempt %d/%d failed (%s). "
                            "Retrying in %.0fs…",
                            attempt, _DB_RETRIES, exc, _DB_RETRY_DELAY,
                        )
                        await asyncio.sleep(_DB_RETRY_DELAY)
                    else:
                        logger.error(
                            "Could not connect to PostgreSQL after %d attempts (%s). "
                            "Running without DB — data will not be persisted.",
                            _DB_RETRIES, exc,
                        )

            if not db_connected:
                await engine.dispose()
                engine = None
                # Degrade gracefully: without this fallback the Refresh button
                # and /api/stocks/refresh/status would stay broken ("service
                # not initialised") until the backend is restarted with the
                # database reachable.
                set_refresh_service(
                    RefreshService(
                        companies=gpw_company_service.get_companies(),
                        stooq=YahooFinanceClient(),
                        history_cache=history_cache,
                        ranking_cache=ranking_cache,
                        action_log=action_log,
                    )
                )
            else:
                # create_all is idempotent: it only creates tables that are
                # missing and never alters existing ones. Running it on every
                # startup means tables added in newer versions (e.g.
                # company_fundamentals) appear automatically on an older DB.
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    # create_all cannot add a column to a table that already
                    # exists, so columns introduced by a later version are
                    # added here explicitly. ADD COLUMN IF NOT EXISTS is
                    # idempotent, so this is a no-op on an up-to-date DB and
                    # the owner never has to run a migration by hand. The
                    # equivalent Alembic revisions are kept in alembic/
                    # versions/ for deployments that manage schema properly.
                    for table, column, coltype in _ADDED_COLUMNS:
                        _validate_ddl_column(table, column, coltype)
                        await conn.execute(
                            text(
                                f"ALTER TABLE {table} "
                                f"ADD COLUMN IF NOT EXISTS {column} {coltype}"
                            )
                        )
                logger.info("Database schema verified (missing tables created).")

                repo = PostgresQuoteRepository(session_factory)
                set_quote_repository(repo)

                # Mirror the action log into the action_logs table as well as
                # the file, and start its periodic retention prune.
                log_repo = ActionLogRepository(session_factory)
                set_action_log_repository(log_repo)
                # Whole-table reads for GET /api/admin/health: how fresh the
                # stored data actually is, independent of what the jobs said.
                set_data_health_repository(DataHealthRepository(session_factory))
                if settings.action_log_to_db:
                    await action_log.start_db_writer(
                        log_repo, settings.action_log_retention_days
                    )

                companies = gpw_company_service.get_companies()
                stooq = YahooFinanceClient()

                ingest_svc = IngestService(
                    companies=companies,
                    stooq=stooq,
                    repo=repo,
                    history_cache=history_cache,
                    ranking_cache=ranking_cache,
                )

                # Full pipeline: ingest → ranking → rating snapshots. Used by
                # the bootstrap, the nightly job and the manual Refresh button.
                refresh_svc = RefreshService(
                    companies=companies,
                    stooq=stooq,
                    history_cache=history_cache,
                    ranking_cache=ranking_cache,
                    repo=repo,
                    ingest=ingest_svc,
                    action_log=action_log,
                )
                set_refresh_service(refresh_svc)

                # ── 3. Bootstrap refresh ──────────────────────────────────────
                if await ingest_svc.needs_bootstrap():
                    logger.info("DB has no data for today — starting bootstrap refresh.")
                    refresh_svc.start(full=True, trigger="bootstrap")
                else:
                    logger.info("DB bootstrap not needed — today's data already present.")

                # ── 4. Nightly scheduler ──────────────────────────────────────
                scheduler = build_scheduler(
                    refresh_svc,
                    hour=settings.ingest_hour,
                    minute=settings.ingest_minute,
                )
                scheduler.start()
                # Exposed so the health endpoint can report the next run time
                # from the scheduler itself rather than from the setting that
                # was meant to configure it.
                set_scheduler(scheduler)
                logger.info(
                    "Scheduler started — next refresh at %02d:%02d Europe/Warsaw.",
                    settings.ingest_hour,
                    settings.ingest_minute,
                )
        else:
            logger.info(
                "STOCKPILOT_DATABASE_URL not set — running without DB persistence. "
                "Set it in .env to enable daily caching."
            )
            # Refresh still works without a DB: it clears the caches and
            # recomputes the ranking from a fresh Yahoo fetch. Rating history
            # is not persisted in this mode.
            set_refresh_service(
                RefreshService(
                    companies=gpw_company_service.get_companies(),
                    stooq=YahooFinanceClient(),
                    history_cache=history_cache,
                    ranking_cache=ranking_cache,
                    action_log=action_log,
                )
            )

        action_log.log_job(
            "job.startup",
            OUTCOME_FINISHED,
            detail={"dbActive": action_log.db_active},
        )
        yield

    finally:
        # ── 6. Graceful shutdown ──────────────────────────────────────────────
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        set_scheduler(None)
        action_log.log_job("job.shutdown", OUTCOME_FINISHED)
        # Flush the queued rows BEFORE the engine goes away, or the tail of the
        # log would be dropped exactly when a shutdown is worth explaining.
        await action_log.stop_db_writer()
        action_log.close_file()
        logging.getLogger().removeHandler(error_handler)
        set_action_log_repository(None)
        set_data_health_repository(None)
        if engine is not None:
            await engine.dispose()
        set_http_client(None)
        set_quote_repository(None)
        set_refresh_service(None)
        await client.aclose()


app = FastAPI(
    title="StockPilot API",
    version=__version__,
    summary="VSA stock scanner for the Warsaw Stock Exchange (GPW).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    # POST is needed only by /api/stocks/refresh (the manual Refresh button).
    allow_methods=["GET", "POST"],
    # X-Admin-Token is the optional shared secret for /api/admin/*; the browser
    # may only send it if CORS says so.
    allow_headers=["Content-Type", "X-Admin-Token"],
    # Let the browser read the pagination total the ranking endpoint sets and
    # the id that ties a response to its action-log entry.
    expose_headers=["X-Total-Count", "X-Request-Id"],
)

# Added AFTER CORSMiddleware, which means it runs INSIDE it: browser preflight
# OPTIONS calls are answered by CORS and never reach the log, where they would
# double every recorded action without saying anything about what the app did.
app.add_middleware(
    ActionLogMiddleware, service=action_log, error_tracker=error_tracker
)

app.include_router(stocks.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health(
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = None,
) -> dict[str, str]:
    db_status = "disabled"
    if repo is not None:
        try:
            await repo.has_today_data("kgh")
            db_status = "ok"
        except Exception as exc:
            logger.exception("Health check DB probe failed.")
            # `from exc` keeps the database error attached to the 503, so the
            # traceback says WHY the probe failed rather than just that it did.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "degraded", "db": "unreachable"},
            ) from exc
    return {"status": "ok", "version": __version__, "db": db_status}
