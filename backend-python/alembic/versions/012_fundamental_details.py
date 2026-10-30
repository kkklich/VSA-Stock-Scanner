"""Observed inputs for the sector-aware fundamental assessment."""

import sqlalchemy as sa

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_fundamentals", sa.Column("fundamental_details", sa.JSON()))


def downgrade() -> None:
    op.drop_column("company_fundamentals", "fundamental_details")
