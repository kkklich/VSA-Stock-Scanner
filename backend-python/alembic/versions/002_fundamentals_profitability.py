"""Add profitability ratios to company_fundamentals.

Adds ``return_on_equity`` and ``return_on_assets`` (fractions, e.g. 0.184 =
18.4%) feeding the stock-detail "Returns & income" card.

These are new COLUMNS on an existing table. The app's startup ``create_all``
only creates missing *tables* and never alters existing ones, so this
migration must be applied explicitly:

    cd backend-python && .venv/Scripts/python -m alembic upgrade head

Until it runs, the app still works — the ORM simply cannot read/write the two
new columns, so the API reports ``returnOnEquity``/``returnOnAssets`` as null.

Revision ID: 002
Revises: 001
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_fundamentals",
        sa.Column("return_on_equity", sa.Float(), nullable=True),
    )
    op.add_column(
        "company_fundamentals",
        sa.Column("return_on_assets", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_fundamentals", "return_on_assets")
    op.drop_column("company_fundamentals", "return_on_equity")
