"""Private named watchlists for registered accounts."""

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_watchlist_name"),
    )
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])


def downgrade() -> None:
    op.drop_table("watchlists")
