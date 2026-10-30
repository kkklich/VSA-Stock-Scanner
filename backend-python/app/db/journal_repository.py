"""Journal evidence is insert-only; updates only change outcome and review."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.models import JournalEntryRow, UserRow
from app.models.journal import CreateEntry, ReviewEntry


class JournalError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status


def response(row, *, full=True):
    result = {
        "id": row.id, "ticker": row.ticker, "note": row.note,
        "confirmation": row.confirmation, "invalidation": row.invalidation,
        "status": row.status, "review": row.review, "version": row.version,
        "createdAt": row.created_at, "updatedAt": row.updated_at,
    }
    if full:
        result["snapshot"] = row.snapshot
    return result


class JournalRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def list(self, owner: int, ticker: str | None, offset: int, limit: int):
        async with self._session_factory() as session:
            condition = [JournalEntryRow.user_id == owner]
            if ticker:
                condition.append(JournalEntryRow.ticker == ticker.upper())
            total = (await session.execute(
                select(func.count()).select_from(JournalEntryRow).where(*condition)
            )).scalar_one()
            # Do not fetch chart blobs when rendering the diary index.
            fields = [getattr(JournalEntryRow, key) for key in (
                "id", "ticker", "note", "confirmation", "invalidation", "status", "review",
                "version", "created_at", "updated_at",
            )]
            rows = (await session.execute(
                select(*fields).where(*condition)
                .order_by(JournalEntryRow.created_at.desc(), JournalEntryRow.id)
                .offset(offset).limit(limit)
            )).all()
            return {"items": [response(row, full=False) for row in rows], "total": total}

    async def get(self, owner: int, entry_id: str):
        async with self._session_factory() as session:
            row = (await session.execute(select(JournalEntryRow).where(
                JournalEntryRow.user_id == owner, JournalEntryRow.id == entry_id,
            ))).scalar_one_or_none()
            if row is None:
                raise JournalError("not_found", 404)
            return response(row)

    async def create(self, owner: int, payload: CreateEntry):
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(select(UserRow.id).where(
                    UserRow.id == owner,
                ).with_for_update())
                existing = (await session.execute(select(JournalEntryRow).where(
                    JournalEntryRow.id == str(payload.id),
                ))).scalar_one_or_none()
                if existing:
                    if existing.user_id != owner:
                        raise JournalError("conflict")
                    # A repeated request after an uncertain network result returns its original.
                    return response(existing)
                count = (await session.execute(select(func.count()).select_from(
                    JournalEntryRow,
                ).where(JournalEntryRow.user_id == owner))).scalar_one()
                if count >= 500:
                    raise JournalError("entry_limit")
                now = datetime.now(UTC)
                row = JournalEntryRow(
                    id=str(payload.id), user_id=owner, ticker=payload.ticker,
                    note=payload.note, confirmation=payload.confirmation,
                    invalidation=payload.invalidation,
                    snapshot=payload.snapshot.model_dump(mode="json", by_alias=True),
                    status="observing", review="", version=1, created_at=now, updated_at=now,
                )
                session.add(row)
                return response(row)

    async def review(self, owner: int, entry_id: str, payload: ReviewEntry):
        async with self._session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(JournalEntryRow).where(
                    JournalEntryRow.user_id == owner, JournalEntryRow.id == entry_id,
                ).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise JournalError("not_found", 404)
                if row.version != payload.version:
                    raise JournalError("conflict")
                row.status, row.review = payload.status, payload.review
                row.version += 1
                row.updated_at = datetime.now(UTC)
                return response(row)

    async def delete(self, owner: int, entry_id: str, version: int):
        async with self._session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(JournalEntryRow).where(
                    JournalEntryRow.user_id == owner, JournalEntryRow.id == entry_id,
                ).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise JournalError("not_found", 404)
                if row.version != version:
                    raise JournalError("conflict")
                await session.delete(row)
                return {"ok": True}
