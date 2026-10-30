"""Owner-scoped operations, serialized per account to preserve concurrent edits."""

from uuid import uuid4

from sqlalchemy import select

from app.db.models import UserRow, WatchlistRow


class WatchlistError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status


class WatchlistRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def change(
        self, user_id: int, operation: str, *, list_id: str | None = None,
        name: str = "Favorites", tickers: list[str] | None = None,
    ) -> list[dict]:
        async with self._session_factory() as session:
            async with session.begin():
                # Locks work across workers/devices, including creation of the first list.
                await session.execute(
                    select(UserRow.id).where(UserRow.id == user_id).with_for_update()
                )
                rows = list((await session.execute(
                    select(WatchlistRow).where(WatchlistRow.user_id == user_id)
                    .order_by(WatchlistRow.name, WatchlistRow.id)
                )).scalars())
                row = next((r for r in rows if r.id == list_id), None)
                if operation in {"rename", "delete", "add", "remove"} and row is None:
                    raise WatchlistError("not_found", 404)
                if operation == "create" or (operation == "bootstrap" and not rows):
                    if len(rows) >= 20:
                        raise WatchlistError("list_limit")
                    if any(r.name.casefold() == name.casefold() for r in rows):
                        raise WatchlistError("duplicate_name")
                    row = WatchlistRow(id=str(uuid4()), user_id=user_id, name=name, tickers=[])
                    session.add(row)
                    rows.append(row)
                elif operation == "rename":
                    if any(r.id != row.id and r.name.casefold() == name.casefold() for r in rows):
                        raise WatchlistError("duplicate_name")
                    row.name = name
                elif operation == "delete":
                    if len(rows) == 1:
                        raise WatchlistError("last_list")
                    await session.delete(row)
                    rows.remove(row)
                elif operation == "add":
                    merged = sorted(set(row.tickers) | set(tickers or []))
                    if len(merged) > 500:
                        raise WatchlistError("ticker_limit")
                    row.tickers = merged
                elif operation == "remove":
                    row.tickers = sorted(set(row.tickers) - set(tickers or []))
                return [{"id": r.id, "name": r.name, "tickers": r.tickers} for r in rows]
