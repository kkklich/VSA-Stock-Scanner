"""StockPilot API application entry point.

Run locally with:
    uvicorn app.main:app --reload --port 5111

Lifespan sequence
-----------------
0. Open the action log's rotating file (the audit trail of every API call and
   background job - see app/services/action_log.py).
1. Open shared stooq HTTP client.
2. (If DATABASE_URL is set) Initialize DB services in the background, retrying
   failures with capped backoff. Readiness stays 503 until repository and
   scheduler are installed; no-DB mode is only used when explicitly configured.
3. Start-up check, per served market: a market with (almost) no stored data
   gets the full ~400-day download, one whose newest finished session is
   missing gets the ordinary top-up — in the background, so the app is live
   meanwhile.
4. Start the nightly APScheduler jobs: 18:00 Warsaw time for the GPW and the
   European markets, 17:15 New York time for the US (when served) — plus the
   hourly live prices for whichever market is trading (and one download right
   away when a market is open at start-up).
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
    get_scheduler,
    gpw_company_service,
    history_cache,
    ranking_cache,
    set_action_log_repository,
    set_data_health_repository,
    set_http_client,
    set_live_prices,
    set_quote_repository,
    set_refresh_service,
    set_scheduler,
    set_user_repository,
    yahoo_client,
)
from app.markets import enabled_markets, refresh_runs
from app.routers import admin, auth, long_term, stocks
from app.services.action_log import (
    OUTCOME_FINISHED,
    OUTCOME_STARTED,
    ActionLogMiddleware,
)
from app.services.error_tracker import ErrorTrackingHandler
from app.services.live_prices import LivePriceService
from app.services.refresh_service import RefreshService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DB_RETRY_DELAY = 3.0
_DB_MAX_RETRY_DELAY = 30.0
_DB_INIT_TIMEOUT = 60.0
_HEALTH_DB_TIMEOUT = 5.0

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
    # 2026-09-17, alembic 005 — reporting currency, for the non-GPW markets.
    ("company_fundamentals", "financial_currency", "VARCHAR(8)"),
    # 2026-09-26, alembic 008 — report calendar, for the volume-surge flag.
    ("company_fundamentals", "last_report_date", "DATE"),
    ("company_fundamentals", "next_report_date", "DATE"),
)

# These identifiers are interpolated into a raw ALTER TABLE statement (there is
# no bind-parameter form for DDL identifiers), so they must never come from
# anything but the trusted constant above. This guard enforces that invariant:
# a plain SQL identifier for the table/column and an allow-listed column type.
# It makes the DDL injection-proof by construction even if a future edit is
# careless about where a value originates.
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_COLUMN_TYPES = frozenset(
    {
        "DOUBLE PRECISION",
        "INTEGER",
        "BIGINT",
        "TEXT",
        "BOOLEAN",
        "NUMERIC",
        "DATE",
        "VARCHAR(8)",
    }
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
    served = [m.id for m in enabled_markets()]
    action_log.log_job(
        "job.startup",
        OUTCOME_STARTED,
        detail={
            "version": __version__,
            "dbConfigured": settings.db_enabled,
            "markets": served,
        },
    )
    # Said once at startup, where a typo in STOCKPILOT_MARKETS is also reported.
    logger.info("Markets served: %s.", ", ".join(served))

    # ── 1. HTTP client ────────────────────────────────────────────────────────
    client = create_http_client()
    set_http_client(client)

    scheduler = None
    engine: AsyncEngine | None = None
    database_startup: asyncio.Task | None = None
    startup_jobs: list[asyncio.Task] = []

    try:
        # ── 2. Database (optional) ────────────────────────────────────────────
        if settings.db_enabled:
            from sqlalchemy import text

            from app.db.action_log_repository import ActionLogRepository
            from app.db.base import Base, build_engine, build_session_factory
            from app.db.health_repository import DataHealthRepository
            from app.db.repository import PostgresQuoteRepository
            from app.db.user_repository import UserRepository
            from app.jobs.daily_ingest import IngestService, build_scheduler

            engine = build_engine(settings.database_url)
            session_factory = build_session_factory(engine)

            async def initialize_database() -> None:
                nonlocal scheduler
                # Retry the entire preparation, including schema and bootstrap
                # queries. Publish dependencies only after all of it succeeds.
                async with engine.connect() as probe:
                    await probe.execute(text("SELECT 1"))
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

                # Optional visitor accounts (app/routers/auth.py). Only
                # available with a database: without one there is nowhere to
                # keep them, and /api/auth/* says so instead of pretending.
                user_repo = UserRepository(session_factory)

                # Mirror the action log into the action_logs table as well as
                # the file, and start its periodic retention prune.
                log_repo = ActionLogRepository(session_factory)
                # Whole-table reads for GET /api/admin/health: how fresh the
                # stored data actually is, independent of what the jobs said.
                health_repo = DataHealthRepository(session_factory)

                # Every company on every served market; each run picks its own.
                companies = gpw_company_service.enabled_companies()
                # The process-wide market-data client (app/dependencies.py) —
                # the same object every endpoint reads through.
                stooq = yahoo_client

                ingest_svc = IngestService(
                    companies=companies,
                    stooq=stooq,
                    repo=repo,
                    history_cache=history_cache,
                    ranking_cache=ranking_cache,
                )

                # Today's prices while an exchange is open, downloaded hourly
                # and shown beside the finished-session analysis (never fed
                # into it). Kept in memory; see app/services/live_prices.py.
                live_svc: LivePriceService | None = None
                if settings.live_prices_enabled:
                    live_svc = LivePriceService(
                        companies=companies, client=stooq, action_log=action_log
                    )

                # Full pipeline: ingest → ranking → rating snapshots (→ live
                # prices for any market trading). Used by the bootstrap, the
                # nightly job and the manual Refresh button.
                refresh_svc = RefreshService(
                    companies=companies,
                    stooq=stooq,
                    history_cache=history_cache,
                    ranking_cache=ranking_cache,
                    repo=repo,
                    ingest=ingest_svc,
                    action_log=action_log,
                    live=live_svc,
                )

                # ── 3. Start-up download ──────────────────────────────────────
                plan = await ingest_svc.bootstrap_plan()
                observation_markets = await ingest_svc.observation_bootstrap_markets()
                startup_markets = [m.id for m in enabled_markets()
                                   if m.id in plan.markets or m.id in observation_markets]
                if observation_markets:
                    logger.info(
                        "Start-up: initializing observation history for %s.",
                        ", ".join(observation_markets),
                    )
                if startup_markets:
                    logger.info(
                        "Start-up data check: full download for %s; top-up for %s.",
                        ", ".join(plan.full) or "no market",
                        ", ".join(plan.catch_up) or "no market",
                    )
                else:
                    logger.info("Start-up data check: every served market is current.")
                # A restart during a session would otherwise show no live prices
                # until the next full hour. The bootstrap refresh planned above
                # ends with the live step for its own markets, so only the
                # others are downloaded here.
                covered = set(startup_markets)
                live_due = (
                    [m for m in live_svc.due_markets() if m not in covered]
                    if live_svc is not None
                    else []
                )
                if live_svc is not None and live_due:
                    logger.info(
                        "Start-up: %s trading now — downloading live prices.",
                        ", ".join(live_due),
                    )

                # ── 4. Nightly scheduler ──────────────────────────────────────
                runs = refresh_runs()
                scheduler = build_scheduler(
                    refresh_svc,
                    runs=runs,
                    live=live_svc,
                    live_interval_minutes=settings.live_prices_interval_minutes,
                )
                if settings.action_log_to_db:
                    await action_log.start_db_writer(
                        log_repo, settings.action_log_retention_days
                    )
                scheduler.start()
                # No await between publication and starting the jobs: requests
                # see either a pending runtime or the fully wired runtime.
                history_cache.clear()
                ranking_cache.clear()
                set_quote_repository(repo)
                set_user_repository(user_repo)
                set_action_log_repository(log_repo)
                set_data_health_repository(health_repo)
                set_live_prices(live_svc)
                set_refresh_service(refresh_svc)
                # Exposed so the health endpoint can report the next run time
                # from the scheduler itself rather than from the setting that
                # was meant to configure it.
                set_scheduler(scheduler)
                logger.info(
                    "Scheduler started — nightly runs: %s; live prices: %s.",
                    "; ".join(
                        f"{run.schedule} ({', '.join(run.market_ids)})" for run in runs
                    ),
                    (
                        f"every {settings.live_prices_interval_minutes} min while "
                        "a market is trading"
                        if live_svc is not None
                        else "off"
                    ),
                )
                if startup_markets:
                    startup_jobs.append(asyncio.create_task(refresh_svc.run(
                        trigger="bootstrap", markets=startup_markets,
                        full_markets=plan.full,
                    ), name="startup_refresh"))
                if live_svc is not None and live_due:
                    startup_jobs.append(asyncio.create_task(live_svc.run(
                        markets=live_due, trigger="startup",
                    ), name="startup_live_prices"))
                action_log.log_job(
                    "job.database_startup", OUTCOME_FINISHED,
                    detail={"repositoryReady": True, "schedulerActive": True},
                )

            async def initialize_with_retry() -> None:
                delay = _DB_RETRY_DELAY
                while True:
                    try:
                        async with asyncio.timeout(_DB_INIT_TIMEOUT):
                            await initialize_database()
                        return
                    except Exception:
                        # Also roll back partial activation (e.g. scheduler
                        # startup failure), before another attempt can begin.
                        for task in startup_jobs:
                            task.cancel()
                        if startup_jobs:
                            await asyncio.gather(*startup_jobs, return_exceptions=True)
                            startup_jobs.clear()
                        if scheduler is not None and scheduler.running:
                            scheduler.shutdown(wait=False)
                        set_scheduler(None)
                        set_quote_repository(None)
                        set_user_repository(None)
                        set_action_log_repository(None)
                        set_data_health_repository(None)
                        set_live_prices(None)
                        set_refresh_service(None)
                        await action_log.stop_db_writer()
                        logger.exception(
                            "Database initialization failed; API is not ready. "
                            "Retrying in %.0fs.", delay,
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, _DB_MAX_RETRY_DELAY)

            database_startup = asyncio.create_task(
                initialize_with_retry(), name="database_startup"
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
                    companies=gpw_company_service.enabled_companies(),
                    stooq=yahoo_client,
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
        # Stop recovery before disposing the engine so it cannot publish new
        # services after teardown. Cancel startup downloads before closing I/O.
        if database_startup is not None:
            database_startup.cancel()
            await asyncio.gather(database_startup, return_exceptions=True)
        for task in startup_jobs:
            task.cancel()
        if startup_jobs:
            await asyncio.gather(*startup_jobs, return_exceptions=True)
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        set_scheduler(None)
        set_live_prices(None)
        action_log.log_job("job.shutdown", OUTCOME_FINISHED)
        # Flush the queued rows BEFORE the engine goes away, or the tail of the
        # log would be dropped exactly when a shutdown is worth explaining.
        await action_log.stop_db_writer()
        action_log.close_file()
        logging.getLogger().removeHandler(error_handler)
        set_action_log_repository(None)
        set_data_health_repository(None)
        set_user_repository(None)
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
    allow_credentials=True,
    # POST is needed only by /api/stocks/refresh (the manual Refresh button).
    allow_methods=["GET", "POST"],
    # X-Admin-Token is the optional shared secret for /api/admin/*; the browser
    # may only send it if CORS says so.
    # Authorization carries the signed-in visitor's bearer token.
    allow_headers=["Content-Type", "X-Admin-Token", "Authorization"],
    # Let the browser read the pagination total the ranking endpoint sets and
    # the id that ties a response to its action-log entry.
    expose_headers=["X-Total-Count", "X-Request-Id"],
)

# Starlette inserts each new middleware at the FRONT of the stack, so the one
# added last is the OUTERMOST: this wraps CORSMiddleware rather than sitting
# inside it, and browser preflight OPTIONS calls do reach it. The middleware
# skips them itself (see ActionLogMiddleware.dispatch) — a preflight is the
# browser asking permission, and recording it would double every logged action
# without saying anything about what the app did.
app.add_middleware(
    ActionLogMiddleware, service=action_log, error_tracker=error_tracker
)

app.include_router(stocks.router)
app.include_router(long_term.router)
app.include_router(admin.router)
app.include_router(auth.router)


@app.get("/health", tags=["meta"], summary="Readiness probe")
async def health(
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = None,
) -> dict[str, str]:
    db_status = "disabled"
    if settings.db_enabled:
        scheduler = get_scheduler()
        if repo is None or scheduler is None or not scheduler.running:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "degraded", "db": "initializing"},
            )
    if repo is not None:
        try:
            async with asyncio.timeout(_HEALTH_DB_TIMEOUT):
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
