"""Persistence helpers for observed financial data and long-term rankings."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime

from pydantic import BaseModel
from sqlalchemy import func, insert, literal, select, union_all

from app.db.models import (
    CompanyCashflowRow,
    CompanyFundamentalsRow,
    CompanyQuarterlyRow,
    FinancialObservationRow,
    LongTermSnapshotRow,
)
from app.models import FinancialMetrics


def financial_payload(value: BaseModel) -> dict:
    """Complete JSON, retaining null fields and mapping non-finite numbers to null.

    Pydantic's JSON serialiser handles NaN/Infinity from upstream data; a plain
    Python model_dump would leave invalid JSON numbers rejected by PostgreSQL.
    """
    return json.loads(value.model_dump_json(by_alias=True))


def utc_timestamp(value: datetime) -> datetime:
    """Normalise an aware timestamp; reject ambiguous caller-supplied times."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware acquisition timestamp is required.")
    return value.astimezone(UTC)


def stored_utc(value: datetime) -> datetime:
    # PostgreSQL returns aware timestamps; SQLite test databases drop the zone.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def metrics_from_row(row: CompanyFundamentalsRow) -> FinancialMetrics:
    values = {name: getattr(row, name) for name in FinancialMetrics.model_fields}
    values["updated_at"] = stored_utc(row.updated_at).isoformat()
    return FinancialMetrics(**values)


def snapshot_values(item: dict, recorded_at: datetime, model_version: str) -> dict:
    """Keep the complete item, including nulls and inputs, as an independent value."""
    session_date = item["asOf"]
    if isinstance(session_date, str):
        session_date = date.fromisoformat(session_date)
    return {
        "ticker": item["ticker"].lower(),
        "market": item["market"],
        "session_date": session_date,
        "recorded_at": utc_timestamp(recorded_at),
        "model_version": model_version,
        "score": item.get("score"),
        "quality": item.get("qualityScore"),
        "value": item.get("valueScore"),
        "momentum": item.get("momentumScore"),
        "payload": deepcopy(item),
    }


class PostgresLongTermRepository:
    """Methods shared by the production quote repository via its session factory."""

    async def get_long_term_inputs(self, tickers: list[str]) -> dict[str, dict]:
        if not tickers:
            return {}
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(CompanyFundamentalsRow).where(
                        CompanyFundamentalsRow.ticker.in_([t.lower() for t in tickers])
                    )
                )
            ).scalars().all()
            latest = (
                select(func.max(FinancialObservationRow.id))
                .where(
                    FinancialObservationRow.ticker.in_([t.lower() for t in tickers]),
                    FinancialObservationRow.kind.in_(("quarterly", "cashflow")),
                )
                .group_by(FinancialObservationRow.ticker, FinancialObservationRow.kind)
            )
            statements = (await session.execute(
                select(FinancialObservationRow).where(FinancialObservationRow.id.in_(latest))
            )).scalars().all()
        output = {
            row.ticker: {
                "metrics": metrics_from_row(row),
                "observed_at": stored_utc(row.updated_at),
            }
            for row in rows
        }
        for row in statements:
            if row.ticker in output:
                output[row.ticker].setdefault("statements", {})[row.kind] = {
                    "payload": deepcopy(row.payload), "observed_at": stored_utc(row.observed_at),
                }
        return output

    async def append_long_term_snapshots(
        self, items: list[dict], recorded_at: datetime, model_version: str
    ) -> None:
        if not items:
            return
        rows = [snapshot_values(item, recorded_at, model_version) for item in items]
        async with self._sf() as session, session.begin():
            await session.execute(insert(LongTermSnapshotRow), rows)

    async def get_long_term_history(self, ticker: str, limit: int = 100) -> list[dict]:
        if limit <= 0:
            return []
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(LongTermSnapshotRow)
                    .where(LongTermSnapshotRow.ticker == ticker.lower())
                    .order_by(LongTermSnapshotRow.recorded_at.desc(), LongTermSnapshotRow.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
        return [
            {
                **deepcopy(row.payload),
                "recordedAt": stored_utc(row.recorded_at).isoformat(),
                "modelVersion": row.model_version,
            }
            for row in rows
        ]

    async def get_financial_history(self, ticker: str, limit: int = 50) -> list[dict]:
        if limit <= 0:
            return []
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(FinancialObservationRow)
                    .where(FinancialObservationRow.ticker == ticker.lower())
                    .order_by(
                        FinancialObservationRow.observed_at.desc(),
                        FinancialObservationRow.id.desc(),
                    )
                    .limit(limit)
                )
            ).scalars().all()
        return [
            {
                "observedAt": stored_utc(row.observed_at).isoformat(),
                "kind": row.kind,
                "source": row.source,
                "payload": deepcopy(row.payload),
            }
            for row in rows
        ]

    async def get_missing_financial_observation_tickers(self, tickers: list[str]) -> set[str]:
        """Tickers lacking archives for metrics or for statements already stored.

        Source-unavailable statements need no first-fill retry on every refresh;
        the regular financial ingest still retries them on its usual schedule.
        Read only distinct keys, never the growing archive's JSON payloads.
        """
        wanted = {ticker.lower() for ticker in tickers}
        if not wanted:
            return set()
        observed = select(
            FinancialObservationRow.ticker, FinancialObservationRow.kind, literal(True)
        ).where(
            FinancialObservationRow.ticker.in_(wanted),
            FinancialObservationRow.kind.in_(("fundamentals", "quarterly", "cashflow")),
        ).distinct()
        quarterly = select(
            CompanyQuarterlyRow.ticker, literal("quarterly"), literal(False)
        ).where(CompanyQuarterlyRow.ticker.in_(wanted)).distinct()
        cashflow = select(
            CompanyCashflowRow.ticker, literal("cashflow"), literal(False)
        ).where(CompanyCashflowRow.ticker.in_(wanted)).distinct()
        async with self._sf() as session:
            rows = (await session.execute(union_all(observed, quarterly, cashflow))).all()
        required = {ticker: {"fundamentals"} for ticker in wanted}
        available = {ticker: set() for ticker in wanted}
        for ticker, kind, archived in rows:
            (available if archived else required)[ticker].add(kind)
        return {ticker for ticker in wanted if not required[ticker] <= available[ticker]}

    async def has_long_term_snapshots(self, market: str | None = None) -> bool:
        query = select(LongTermSnapshotRow.id).limit(1)
        if market is not None:
            query = query.where(LongTermSnapshotRow.market == market)
        async with self._sf() as session:
            return (await session.execute(query)).scalar_one_or_none() is not None

    async def has_financial_observations(self) -> bool:
        async with self._sf() as session:
            return (
                await session.execute(select(FinancialObservationRow.id).limit(1))
            ).scalar_one_or_none() is not None
