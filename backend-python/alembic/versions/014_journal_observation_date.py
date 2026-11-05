"""Separate the observation date from the journal's creation timestamp."""

import sqlalchemy as sa

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("journal_entries", sa.Column("observation_date", sa.Date(), nullable=True))
    entries = sa.table(
        "journal_entries",
        sa.column("observation_date", sa.Date()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    created = entries.c.created_at
    if op.get_bind().dialect.name == "postgresql":
        created = sa.func.timezone("UTC", created)
    op.execute(entries.update().values(observation_date=sa.func.date(created)))
    with op.batch_alter_table("journal_entries") as batch:
        batch.alter_column("observation_date", existing_type=sa.Date(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("journal_entries") as batch:
        batch.drop_column("observation_date")
