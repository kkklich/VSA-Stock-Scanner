"""SQLAlchemy async engine + session factory.

The engine and session factory are created once during the application lifespan
and injected via ``app/dependencies.py``. This module only provides the factory
functions — it does not hold any global state itself, making it easy to test and
to swap the underlying database.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ── Connection-pool budget ───────────────────────────────────────────────────
# These two numbers are the hard ceiling on how many PostgreSQL connections
# this process can hold open. Anything that fans out over the whole ~290-company
# universe has to be sized against them, or the 291st concurrent read waits for
# a connection until SQLAlchemy's pool timeout fires and the ticker is dropped
# from the scan — which reads, on the dashboard, as a thin market rather than a
# broken one. Keep them here so the scans can import the budget instead of
# guessing at it.
POOL_SIZE = 5
MAX_OVERFLOW = 10
MAX_DB_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW  # 15

# How many database reads a full-universe scan may have in flight at once.
# Deliberately below MAX_DB_CONNECTIONS: the scan is never the only thing
# asking for a connection (the rating-snapshot writer, the health probe and any
# other request being served share the same pool), so it takes two thirds and
# leaves the rest. Waiting on this semaphore is cheap; waiting on an exhausted
# pool ends in a timeout and lost data.
DB_SCAN_CONCURRENCY = max(1, MAX_DB_CONNECTIONS * 2 // 3)  # 10


def build_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given URL.

    Pool settings are intentionally conservative for a single-instance API;
    tune ``pool_size`` / ``max_overflow`` for horizontal scale-out.

    ``ssl=False`` is passed to asyncpg via ``connect_args`` so that local
    development databases (e.g. Scoop-installed PostgreSQL without TLS
    certificates) don't time out during the SSL-upgrade handshake.
    Production deployments that need SSL should instead embed the ssl
    parameters in the DATABASE_URL query string (``?ssl=require``), which
    takes precedence over these defaults.
    """
    connect_args: dict = {}
    # Only inject the ssl=False default when no ssl parameter is already
    # present in the URL, so production URLs with ?ssl=require are respected.
    if "ssl=" not in database_url:
        connect_args["ssl"] = False

    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        connect_args=connect_args,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
