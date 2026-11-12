"""Link one portfolio per owner to an XTB account."""

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

_INDEX = "uq_portfolios_user_broker_account_id"


def upgrade() -> None:
    # Startup may already have installed the column on an app-managed database.
    if op.get_context().as_sql or not any(
        column["name"] == "broker_account_id"
        for column in sa.inspect(op.get_bind()).get_columns("portfolios")
    ):
        op.add_column("portfolios", sa.Column("broker_account_id", sa.String(32), nullable=True))
    op.create_index(
        _INDEX, "portfolios", ["user_id", "broker_account_id"], unique=True, if_not_exists=True
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="portfolios")
    op.drop_column("portfolios", "broker_account_id")
