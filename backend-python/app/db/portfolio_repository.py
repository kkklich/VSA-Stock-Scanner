"""Account-scoped, versioned portfolio persistence and batched stored quote lookup."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.models import DailyQuoteRow, PortfolioRow, UserRow
from app.services.portfolio import PortfolioError, holdings


def response(row):
    return {
        "id": row.id,
        "name": row.name,
        "broker": row.broker,
        "costMethod": row.cost_method,
        "transactions": row.transactions,
        "version": row.version,
        "createdAt": row.created_at,
    }


class PortfolioRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def list(self, owner):
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(PortfolioRow)
                        .where(
                            PortfolioRow.user_id == owner,
                        )
                        .order_by(PortfolioRow.created_at, PortfolioRow.id)
                    )
                )
                .scalars()
                .all()
            )
            return [response(row) for row in rows]

    async def quotes(self, tickers):
        if not tickers:
            return {}
        async with self._session_factory() as session:
            latest = (
                select(
                    DailyQuoteRow.ticker,
                    func.max(DailyQuoteRow.date).label("date"),
                )
                .where(DailyQuoteRow.ticker.in_(tickers))
                .group_by(DailyQuoteRow.ticker)
                .subquery()
            )
            rows = (
                await session.execute(
                    select(
                        DailyQuoteRow.ticker,
                        DailyQuoteRow.date,
                        DailyQuoteRow.close,
                    ).join(
                        latest,
                        (DailyQuoteRow.ticker == latest.c.ticker)
                        & (DailyQuoteRow.date == latest.c.date),
                    )
                )
            ).all()
            return {row.ticker: {"price": row.close, "date": row.date} for row in rows}

    async def change(
        self,
        owner,
        operation,
        *,
        portfolio_id=None,
        payload=None,
        version=None,
        transaction_id=None,
    ):
        async with self._session_factory() as session:
            async with session.begin():
                # Shared lock across account writes handles creation limits and retry races.
                await session.execute(
                    select(UserRow.id)
                    .where(
                        UserRow.id == owner,
                    )
                    .with_for_update()
                )
                key = str(payload.id) if operation == "create" else portfolio_id
                row = (
                    await session.execute(
                        select(PortfolioRow)
                        .where(
                            PortfolioRow.user_id == owner,
                            PortfolioRow.id == key,
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if operation == "create":
                    if row:
                        if (
                            row.name != payload.name
                            or row.broker != payload.broker
                            or row.cost_method != payload.cost_method
                        ):
                            raise PortfolioError("conflict")
                        return response(row)
                    occupied = (
                        await session.execute(
                            select(PortfolioRow.id).where(
                                PortfolioRow.id == key,
                            )
                        )
                    ).scalar_one_or_none()
                    if occupied:
                        raise PortfolioError("conflict")
                    count = (
                        await session.execute(
                            select(func.count())
                            .select_from(
                                PortfolioRow,
                            )
                            .where(PortfolioRow.user_id == owner)
                        )
                    ).scalar_one()
                    if count >= 20:
                        raise PortfolioError("portfolio_limit")
                    row = PortfolioRow(
                        id=key,
                        user_id=owner,
                        name=payload.name,
                        broker=payload.broker,
                        cost_method=payload.cost_method,
                        transactions=[],
                        version=1,
                        created_at=datetime.now(UTC),
                    )
                    session.add(row)
                    return response(row)
                if row is None:
                    raise PortfolioError("not_found", 404)
                if operation == "add":
                    trade = payload.model_dump(mode="json", exclude={"version"})
                    existing = next((t for t in row.transactions if t["id"] == trade["id"]), None)
                    if existing:
                        if existing != trade:
                            raise PortfolioError("conflict")
                        return response(row)
                if row.version != (payload.version if payload else version):
                    raise PortfolioError("conflict")
                if operation == "update":
                    row.name, row.broker = payload.name, payload.broker
                    row.cost_method = payload.cost_method
                elif operation == "add":
                    if len(row.transactions) >= 1000:
                        raise PortfolioError("transaction_limit")
                    trades = [*row.transactions, trade]
                    holdings(trades)  # Validate the entire dated ledger, including backdated sales.
                    row.transactions = trades
                elif operation == "remove":
                    trades = [t for t in row.transactions if t["id"] != transaction_id]
                    if len(trades) == len(row.transactions):
                        raise PortfolioError("not_found", 404)
                    holdings(trades)
                    row.transactions = trades
                elif operation == "delete":
                    await session.delete(row)
                    return {"ok": True}
                row.version += 1
                return response(row)
