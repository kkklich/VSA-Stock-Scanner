"""StockPilot API application entry point.

Run locally with:
    uvicorn app.main:app --reload --port 5111

Lifespan sequence
-----------------
1. Open shared stooq HTTP client.
2. (If DATABASE_URL is set) Create async DB engine, conditionally create tables,
   build repo.
3. Bootstrap: if fewer than 90% of tickers have today's data in DB, trigger a
   full ingest in the background (non-blocking — first API call may still hit
   stooq.pl while ingest runs).
4. Start nightly APScheduler job (18:00 Warsaw time).
5. Yield (app is live).
6. Shutdown: stop scheduler, dispose DB engine, close HTTP client.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.config import settings
from app.db.repository import QuoteRepository
from app.dependencies import (
    create_http_client,
    get_quote_repository,
    gpw_company_service,
    history_cache,
    ranking_cache,
    set_http_client,
    set_quote_repository,
)
from app.routers import stocks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── 1. HTTP client ────────────────────────────────────────────────────────
    client = create_http_client()
    set_http_client(client)

    scheduler = None
    engine: AsyncEngine | None = None

    try:
        # ── 2. Database (optional) ────────────────────────────────────────────
        if settings.db_enabled:
            from sqlalchemy import text

            from app.db.base import Base, build_engine, build_session_factory
            from app.db.repository import PostgresQuoteRepository
            from app.jobs.daily_ingest import IngestService, build_scheduler
            from app.services.yahoo_finance_client import YahooFinanceClient

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
            else:
                # Only create tables if this is a brand-new empty database (dev
                # convenience). In production, run: alembic upgrade head
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name = 'daily_quotes'"
                        )
                    )
                    table_exists = result.scalar() > 0

                if not table_exists:
                    logger.info(
                        "No tables found — running create_all for initial setup (dev mode)."
                    )
                    async with engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                else:
                    logger.info(
                        "Tables already exist — skipping create_all. "
                        "Run 'alembic upgrade head' for schema changes."
                    )

                repo = PostgresQuoteRepository(session_factory)
                set_quote_repository(repo)

                companies = gpw_company_service.get_companies()
                stooq = YahooFinanceClient()

                ingest_svc = IngestService(
                    companies=companies,
                    stooq=stooq,
                    repo=repo,
                    history_cache=history_cache,
                    ranking_cache=ranking_cache,
                )

                # ── 3. Bootstrap ingest ───────────────────────────────────────
                if await ingest_svc.needs_bootstrap():
                    logger.info("DB has no data for today — starting bootstrap ingest.")
                    task = asyncio.create_task(
                        ingest_svc.run(full=True), name="bootstrap_ingest"
                    )
                    task.add_done_callback(
                        lambda t: logger.error("Bootstrap ingest failed: %s", t.exception())
                        if not t.cancelled() and t.exception()
                        else None
                    )
                else:
                    logger.info("DB bootstrap not needed — today's data already present.")

                # ── 4. Nightly scheduler ──────────────────────────────────────
                scheduler = build_scheduler(
                    ingest_svc,
                    hour=settings.ingest_hour,
                    minute=settings.ingest_minute,
                )
                scheduler.start()
                logger.info(
                    "Scheduler started — next ingest at %02d:%02d Europe/Warsaw.",
                    settings.ingest_hour,
                    settings.ingest_minute,
                )
        else:
            logger.info(
                "STOCKPILOT_DATABASE_URL not set — running without DB persistence. "
                "Set it in .env to enable daily caching."
            )

        yield

    finally:
        # ── 6. Graceful shutdown ──────────────────────────────────────────────
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        if engine is not None:
            await engine.dispose()
        set_http_client(None)
        set_quote_repository(None)
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
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)

app.include_router(stocks.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health(
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = None,
) -> dict[str, str]:
    db_status = "disabled"
    if repo is not None:
        try:
            await repo.has_today_data("kgh")
            db_status = "ok"
        except Exception:
            logger.exception("Health check DB probe failed.")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "degraded", "db": "unreachable"},
            )
    return {"status": "ok", "version": __version__, "db": db_status}
