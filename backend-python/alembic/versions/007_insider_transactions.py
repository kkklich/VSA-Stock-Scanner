"""Add the ``insider_transactions`` table — reported manager/director trades.

Populated from Yahoo Finance (US/UK) and GPW ESPI reports under MAR art. 19 (Poland).
Drawn on the stock chart as its own switchable layer (green purchases below candle,
red sales above candle) and presented in an insider activity summary card.

Revision ID: 007
Revises: 006
Create Date: 2026-09-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insider_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=False),
        sa.Column("insider_name", sa.String(200), nullable=True),
        sa.Column("role", sa.String(200), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column(
            "is_open_market", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("price", sa.Numeric(14, 4), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("value", sa.Numeric(16, 2), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_insider_transactions_ticker",
        "insider_transactions",
        ["ticker"],
    )
    op.create_index(
        "ix_insider_transactions_publication_date",
        "insider_transactions",
        ["publication_date"],
    )
    op.create_index(
        "ix_insider_transactions_ticker_pubdate",
        "insider_transactions",
        ["ticker", "publication_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_insider_transactions_ticker_pubdate",
        table_name="insider_transactions",
    )
    op.drop_index(
        "ix_insider_transactions_publication_date",
        table_name="insider_transactions",
    )
    op.drop_index(
        "ix_insider_transactions_ticker",
        table_name="insider_transactions",
    )
    op.drop_table("insider_transactions")
