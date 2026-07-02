"""Alembic environment.

Uses the *synchronous* (psycopg2) database URL from app/config.py so that
standard Alembic migrate commands work without any async boilerplate.
The production async engine (asyncpg) is used only at runtime.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import ORM models so Alembic can diff against the current DB schema.
from app.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401 — registers all ORM models on Base.metadata

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return settings.database_url_sync


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the DB."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
