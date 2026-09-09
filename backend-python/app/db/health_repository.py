"""Persistence reads for the system-health screen.

Kept separate from ``QuoteRepository`` for the same reason
``ActionLogRepository`` is: that protocol is about market data for the
analysis endpoints, and every implementation of it (including the in-memory
fake the tests use) would have to grow operational queries it has no business
owning.

These are *diagnostic* questions — "how far does the stored data actually
reach, and for how many companies?" — asked by ``GET /api/admin/health`` when
the owner wants to know whether last night's ingest really landed. They are
whole-table aggregates, so they are asked once per health check, never per
request on a hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import DailyQuoteRow, RatingSnapshotRow


@dataclass(slots=True)
class StoredDataStats:
    """What the database actually holds, as one health check sees it."""

    # The newest bar date anywhere in the table — "the last session we have".
    latest_bar_date: date | None
    # The oldest bar date — how far the history reaches back.
    earliest_bar_date: date | None
    # Distinct tickers with at least one stored bar.
    tickers_with_data: int
    # Tickers whose own newest bar IS the newest bar in the table (i.e. they
    # were updated by the last ingest) and those lagging behind it.
    tickers_current: int
    tickers_behind: int
    # Total stored bars — a single number that should never go down.
    bar_count: int
    # Newest stored rating snapshot, so a refresh that ingested bars but failed
    # to write ratings is distinguishable from one that did neither.
    latest_snapshot_date: date | None


class DataHealthRepository:
    """Whole-table reads that describe the state of the stored data."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def latest_bar_dates(self) -> dict[str, date]:
        """Newest stored bar per ticker (~290 rows, one GROUP BY)."""
        stmt = select(DailyQuoteRow.ticker, func.max(DailyQuoteRow.date)).group_by(
            DailyQuoteRow.ticker
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return {ticker: last for ticker, last in rows if last is not None}

    async def stats(self) -> StoredDataStats:
        """Everything the health screen needs about stored data, in three reads."""
        per_ticker = await self.latest_bar_dates()
        latest = max(per_ticker.values()) if per_ticker else None
        current = sum(1 for d in per_ticker.values() if d == latest) if latest else 0

        async with self._session_factory() as session:
            earliest = (
                await session.execute(select(func.min(DailyQuoteRow.date)))
            ).scalar_one_or_none()
            bar_count = int(
                (
                    await session.execute(select(func.count()).select_from(DailyQuoteRow))
                ).scalar_one()
            )
            latest_snapshot = (
                await session.execute(select(func.max(RatingSnapshotRow.date)))
            ).scalar_one_or_none()

        return StoredDataStats(
            latest_bar_date=latest,
            earliest_bar_date=earliest,
            tickers_with_data=len(per_ticker),
            tickers_current=current,
            tickers_behind=len(per_ticker) - current,
            bar_count=bar_count,
            latest_snapshot_date=latest_snapshot,
        )
