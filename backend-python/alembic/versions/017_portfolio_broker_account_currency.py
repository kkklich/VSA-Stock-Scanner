"""Record the currency of an XTB broker account independently of its holdings."""

import sqlalchemy as sa

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().as_sql or not any(
        column["name"] == "broker_account_currency"
        for column in sa.inspect(op.get_bind()).get_columns("portfolios")
    ):
        op.add_column("portfolios", sa.Column("broker_account_currency", sa.String(3)))


def downgrade() -> None:
    op.drop_column("portfolios", "broker_account_currency")
