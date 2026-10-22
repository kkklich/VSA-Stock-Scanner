"""Append observed financial data and long-term ranking revisions.

Revision ID: 009
Revises: 008
Create Date: 2026-10-22

No backfill: historical period dates cannot establish when data was known.
"""

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_observations",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_financial_observation_history", "financial_observations",
        ["ticker", "observed_at", "id"],
    )
    op.create_index(
        "ix_financial_observation_kinds", "financial_observations", ["ticker", "kind"]
    )
    op.create_table(
        "long_term_snapshots",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("quality", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("momentum", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_long_term_snapshot_history", "long_term_snapshots", ["ticker", "recorded_at", "id"]
    )
    op.create_index("ix_long_term_snapshot_market", "long_term_snapshots", ["market"])


def downgrade() -> None:
    op.drop_table("long_term_snapshots")
    op.drop_table("financial_observations")
