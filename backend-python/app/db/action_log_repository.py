"""Persistence for the action log (audit trail).

Kept separate from ``QuoteRepository`` on purpose: that protocol is about
market data, and every implementation of it (including the in-memory fake the
tests use) would have to grow log methods it has no business owning. The log
has its own small repository over the same session factory.

Writes arrive in batches from the log's background worker
(``app/services/action_log.py``), never on a request's own path.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ActionLogRow

if TYPE_CHECKING:  # pragma: no cover — import cycle only matters for typing
    from app.services.action_log import ActionLogEntry


class ActionLogRepository:
    """Reads and writes ``action_logs`` rows."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def insert_many(self, entries: list[ActionLogEntry]) -> None:
        """Append a batch of entries. Plain INSERTs — log rows are never updated."""
        if not entries:
            return
        rows = [
            {
                "started_at": e.started_at,
                "request_id": e.request_id,
                "kind": e.kind,
                "action": e.action[:200],
                "outcome": e.outcome,
                "duration_ms": e.duration_ms,
                "method": e.method,
                "path": e.path[:500] if e.path else None,
                "query": e.query,
                "status_code": e.status_code,
                "response_bytes": e.response_bytes,
                "client_ip": e.client_ip,
                "user_agent": e.user_agent[:300] if e.user_agent else None,
                "detail": e.detail,
            }
            for e in entries
        ]
        async with self._session_factory() as session:
            await session.execute(ActionLogRow.__table__.insert(), rows)
            await session.commit()

    async def query(
        self,
        *,
        kind: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ActionLogRow], int]:
        """Return one page of rows (newest first) and the total match count."""
        conditions = []
        if kind:
            conditions.append(ActionLogRow.kind == kind)
        if action:
            conditions.append(ActionLogRow.action.ilike(f"%{action}%"))
        if outcome:
            conditions.append(ActionLogRow.outcome == outcome)
        if since is not None:
            conditions.append(ActionLogRow.started_at >= since)
        if until is not None:
            conditions.append(ActionLogRow.started_at <= until)

        async with self._session_factory() as session:
            count_stmt = select(func.count()).select_from(ActionLogRow)
            page_stmt = select(ActionLogRow)
            for condition in conditions:
                count_stmt = count_stmt.where(condition)
                page_stmt = page_stmt.where(condition)
            total = int((await session.execute(count_stmt)).scalar_one())
            page_stmt = (
                page_stmt.order_by(ActionLogRow.started_at.desc(), ActionLogRow.id.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = list((await session.execute(page_stmt)).scalars().all())
        return rows, total

    async def prune(self, older_than: datetime) -> int:
        """Delete rows that started before ``older_than``; return how many."""
        async with self._session_factory() as session:
            result = await session.execute(
                delete(ActionLogRow).where(ActionLogRow.started_at < older_than)
            )
            await session.commit()
            return int(result.rowcount or 0)
