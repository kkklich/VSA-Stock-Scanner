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

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import DailyQuoteRow, RatingSnapshotRow


@dataclass(slots=True)
class MarketStoredStats:
    """What the database holds for one market's tracked tickers."""

    market: str
    # The newest bar any of the market's tracked tickers has.
    latest_bar_date: date | None
    tickers_tracked: int
    tickers_with_data: int
    # Tickers carrying that newest bar.
    tickers_current: int


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
    # Per market, when the caller said which tickers belong where.
    markets: list[MarketStoredStats] = field(default_factory=list)


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

    async def stats(self, tracked: Mapping[str, str] | None = None) -> StoredDataStats:
        """Everything the health screen needs about stored data, in three reads.

        ``tracked`` maps each tracked ticker to its market id. With it, the
        counts cover tracked tickers only and "current" is judged within each
        market — markets close hours apart, so one global "newest bar" would
        call every US stock behind between the European and the US runs.
        """
        per_ticker = await self.latest_bar_dates()
        markets: list[MarketStoredStats] = []
        if tracked is None:
            latest = max(per_ticker.values()) if per_ticker else None
            current = sum(1 for d in per_ticker.values() if d == latest) if latest else 0
            with_data = len(per_ticker)
        else:
            by_market: dict[str, list[date]] = {}
            sizes: dict[str, int] = {}
            for ticker, market_id in tracked.items():
                sizes[market_id] = sizes.get(market_id, 0) + 1
                newest = per_ticker.get(ticker)
                if newest is not None:
                    by_market.setdefault(market_id, []).append(newest)
            for market_id, size in sizes.items():
                dates = by_market.get(market_id, [])
                newest = max(dates) if dates else None
                markets.append(
                    MarketStoredStats(
                        market=market_id,
                        latest_bar_date=newest,
                        tickers_tracked=size,
                        tickers_with_data=len(dates),
                        tickers_current=sum(1 for d in dates if d == newest),
                    )
                )
            latest = max((m.latest_bar_date for m in markets if m.latest_bar_date), default=None)
            current = sum(m.tickers_current for m in markets)
            with_data = sum(m.tickers_with_data for m in markets)

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
            tickers_with_data=with_data,
            tickers_current=current,
            tickers_behind=with_data - current,
            bar_count=bar_count,
            latest_snapshot_date=latest_snapshot,
            markets=markets,
        )
