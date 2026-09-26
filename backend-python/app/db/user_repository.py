"""Persistence for user accounts (the ``users`` table).

Its own small repository over the shared session factory, for the same reason
the action log has one: ``QuoteRepository`` is about market data, and every
implementation of it — including the in-memory fake the tests use — would
otherwise have to grow account methods it has no business owning.

Accounts exist only when a database is configured. With no
``STOCKPILOT_DATABASE_URL`` the app still runs (stateless, reading market data
live) and the sign-in endpoints answer 503 rather than pretending to register
someone into nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import UserRow


class EmailAlreadyRegistered(Exception):
    """Raised when an address already has an account."""


class UserRepository:
    """Reads and writes ``users`` rows."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        role: str = "user",
    ) -> UserRow:
        """Insert a new account. ``email`` must already be normalised.

        The UNIQUE constraint on ``email`` is what actually decides the race
        between two simultaneous registrations of the same address — checking
        first and inserting second would let both through. The pre-check in the
        router is only there to give a friendly message in the common case.
        """
        row = UserRow(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            is_active=True,
            email_verified=False,
            token_version=1,
            created_at=datetime.now(tz=UTC),
            last_login_at=None,
        )
        async with self._session_factory() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise EmailAlreadyRegistered(email) from exc
            await session.refresh(row)
            return row

    async def get_by_email(self, email: str) -> UserRow | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserRow).where(UserRow.email == email)
            )
            return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> UserRow | None:
        async with self._session_factory() as session:
            result = await session.execute(select(UserRow).where(UserRow.id == user_id))
            return result.scalar_one_or_none()

    async def touch_last_login(self, user_id: int) -> None:
        """Record a successful sign-in. Never fails a login on its own."""
        async with self._session_factory() as session:
            await session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(last_login_at=datetime.now(tz=UTC))
            )
            await session.commit()

    async def set_password(self, user_id: int, password_hash: str) -> None:
        """Store a new password hash and invalidate every existing token.

        Bumping ``token_version`` is the whole point: after a password change
        the tokens handed out before it stop verifying, so a session someone
        else was holding dies with the old password.
        """
        async with self._session_factory() as session:
            await session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(
                    password_hash=password_hash,
                    token_version=UserRow.token_version + 1,
                )
            )
            await session.commit()

    async def count(self) -> int:
        async with self._session_factory() as session:
            result = await session.execute(select(func.count()).select_from(UserRow))
            return int(result.scalar_one())
