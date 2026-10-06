"""Add the company report calendar to company_fundamentals.

Adds ``last_report_date`` and ``next_report_date``: Yahoo's report calendar
for the company (``earningsTimestamp*`` in the quote summary the weekly
fundamentals pass already downloads), as dates on the exchange's own
calendar. The volume-surge scanner marks a surge whose window holds a report
date, because earnings are the commonest cause of a multi-day volume surge
(roadmap #15b).

The app adds the columns itself on startup (``_ADDED_COLUMNS`` in
app/main.py); this revision is the equivalent for deployments that manage
schema with Alembic:

    cd backend-python && .venv/Scripts/python -m alembic upgrade head

Revision ID: 008
Revises: 007
Create Date: 2026-09-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_fundamentals",
        sa.Column("last_report_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "company_fundamentals",
        sa.Column("next_report_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_fundamentals", "next_report_date")
    op.drop_column("company_fundamentals", "last_report_date")
