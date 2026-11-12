"""Owner-scoped saved filters, merged by immutable client-generated ids."""

from __future__ import annotations

from datetime import UTC

from sqlalchemy import delete, select

from app.db.models import FilterPresetRow, UserRow
from app.models.filter_presets import ScreenFilters

MAX_PRESETS = 100


class FilterPresetError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


def _as_dict(row: FilterPresetRow) -> dict:
    # SQLite returns naive datetimes even for columns declared with timezone=True.
    created = row.created_at
    return {
        "id": row.id,
        "name": row.name,
        "filters": ScreenFilters.model_validate(row.filters).model_dump(),
        "createdAt": created.astimezone(UTC) if created.tzinfo else created.replace(tzinfo=UTC),
    }


async def _list(session, user_id: int) -> list[dict]:
    rows = await session.execute(
        select(FilterPresetRow).where(FilterPresetRow.user_id == user_id)
        .order_by(FilterPresetRow.created_at, FilterPresetRow.id)
    )
    return [_as_dict(row) for row in rows.scalars()]


async def _lock_owner(session, user_id: int) -> None:
    # Serialize mutations, including the first insert, across devices/workers.
    await session.execute(select(UserRow.id).where(UserRow.id == user_id).with_for_update())


class FilterPresetRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def list(self, user_id: int) -> list[dict]:
        async with self._session_factory() as session:
            return await _list(session, user_id)

    async def add(self, user_id: int, presets: list[dict]) -> list[dict]:
        async with self._session_factory() as session, session.begin():
            await _lock_owner(session, user_id)
            by_id = {p["id"]: p for p in await _list(session, user_id)}
            for preset in presets:
                existing = by_id.get(preset["id"])
                if existing is not None:
                    if existing != preset:
                        raise FilterPresetError("id_conflict")
                    continue
                if len(by_id) >= MAX_PRESETS:
                    raise FilterPresetError("preset_limit")
                session.add(FilterPresetRow(
                    user_id=user_id, id=preset["id"], name=preset["name"],
                    filters=preset["filters"], created_at=preset["createdAt"].astimezone(UTC),
                ))
                by_id[preset["id"]] = preset
            return await _list(session, user_id)

    async def delete(self, user_id: int, preset_id: str) -> list[dict]:
        async with self._session_factory() as session, session.begin():
            await _lock_owner(session, user_id)
            removed = await session.execute(delete(FilterPresetRow).where(
                FilterPresetRow.user_id == user_id, FilterPresetRow.id == preset_id,
            ))
            if not removed.rowcount:
                raise FilterPresetError("not_found", 404)
            return await _list(session, user_id)
