"""Persist user-added stock listings."""

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().as_sql or not sa.inspect(op.get_bind()).has_table("custom_companies"):
        op.create_table(
            "custom_companies",
            sa.Column("ticker", sa.String(20), primary_key=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("custom_companies")
