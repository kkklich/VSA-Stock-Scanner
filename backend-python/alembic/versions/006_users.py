"""Add the ``users`` table — optional visitor accounts.

Sign-in is optional on this site: every page can still be read without an
account. A row holds the address, the bcrypt hash of the password (never the
password), the display name, the role and ``token_version``, which is bumped on
a password change so every login token issued before it stops verifying.

A whole NEW table, so the app creates it itself on startup via
``Base.metadata.create_all`` and the owner never has to run this by hand. This
revision is the equivalent for deployments that manage schema with Alembic:

    cd backend-python && .venv/Scripts/python -m alembic upgrade head

Revision ID: 006
Revises: 005
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )


def downgrade() -> None:
    op.drop_table("users")
