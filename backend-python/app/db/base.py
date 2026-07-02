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
        pool_size=5,
        max_overflow=10,
        connect_args=connect_args,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
