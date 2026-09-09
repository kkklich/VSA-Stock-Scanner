"""Add action_logs — the audit trail of every API call and background job.

One row per recorded action: when it started, what it was (route template or
job name), how it ended, how long it took. Written by
``app/services/action_log.py`` in batches off the request path, and read back
by ``GET /api/admin/logs``. Rows older than
``STOCKPILOT_ACTION_LOG_RETENTION_DAYS`` (30 by default) are deleted by the
log's own periodic prune, so the table cannot grow without bound.

This is a new TABLE, so the app's startup ``create_all`` already creates it —
no manual step is needed for the local setup. The migration exists for managed
deployments that apply schema changes with Alembic:

    cd backend-python && .venv/Scripts/python -m alembic upgrade head

Revision ID: 004
Revises: 003
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.BigInteger(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Two indexes only: this table is written on every request, so each one is
    # a cost paid thousands of times a day. started_at carries the default
    # ordering and the retention prune; action carries the natural grouping.
    op.create_index("ix_action_logs_started_at", "action_logs", ["started_at"])
    op.create_index("ix_action_logs_action", "action_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_action_logs_action", table_name="action_logs")
    op.drop_index("ix_action_logs_started_at", table_name="action_logs")
    op.drop_table("action_logs")
