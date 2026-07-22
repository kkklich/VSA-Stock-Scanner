"""Add company_cashflow — capital expenditure per reported period.

Feeds the ``/capex`` screen ("how much does each company invest in itself")
and the capex section of the stock-detail fundamentals card. One row per
(ticker, period end, period type); ``capex`` is stored as a POSITIVE amount of
money spent, and ``currency`` is the statement's reporting currency (NOT
always PLN — foreign dual-listings report in EUR/USD/CZK/HUF).

This is a new TABLE, so the app's startup ``create_all`` already creates it —
no manual step is needed for the local setup. The migration exists for managed
deployments that apply schema changes with Alembic:

    cd backend-python && .venv/Scripts/python -m alembic upgrade head

Revision ID: 003
Revises: 002
Create Date: 2026-07-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_cashflow",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("capex", sa.BigInteger(), nullable=True),
        sa.Column("operating_cash_flow", sa.BigInteger(), nullable=True),
        sa.Column("free_cash_flow", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "period_end", "period_type", name="uq_cashflow"),
    )
    op.create_index(
        "ix_company_cashflow_ticker", "company_cashflow", ["ticker"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_company_cashflow_ticker", table_name="company_cashflow")
    op.drop_table("company_cashflow")
