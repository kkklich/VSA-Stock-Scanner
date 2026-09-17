"""Add the reporting currency to company_fundamentals.

Adds ``financial_currency`` (Yahoo ``financialCurrency``): the currency a
company's revenue, net income and EPS are stated in. Not always the currency
its shares trade in — HSBC trades in pence on the London exchange and reports
in US dollars — so the stock page can no longer assume złoty once markets
other than the GPW are tracked (see agent/MULTI-MARKET-PLAN.md).

The app adds the column itself on startup (``_ADDED_COLUMNS`` in app/main.py);
this revision is the equivalent for deployments that manage schema with
Alembic:

    cd backend-python && .venv/Scripts/python -m alembic upgrade head

Revision ID: 005
Revises: 004
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_fundamentals",
        sa.Column("financial_currency", sa.String(8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_fundamentals", "financial_currency")
