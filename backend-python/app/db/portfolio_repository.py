"""Account-scoped, versioned portfolio persistence and batched stored quote lookup."""

from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from app.db.models import DailyQuoteRow, PortfolioRow, UserRow
from app.services.portfolio import (
    PortfolioError,
    holdings,
    require_after_checkpoint,
    xtb_checkpoint,
)
from app.services.xtb_import import prepare_import
from app.services.xtb_reconciliation import reconciliation_view


def response(row, *, include_ledger=False):
    ledger = row.transactions
    checkpoint = xtb_checkpoint(ledger)
    data = {
        "id": row.id,
        "name": row.name,
        "broker": row.broker,
        "costMethod": row.cost_method,
        "transactions": [entry for entry in ledger if entry is not checkpoint],
        "reconciliation": reconciliation_view(checkpoint),
        "version": row.version,
        "createdAt": row.created_at,
    }
    if include_ledger:
        data["ledger"] = ledger
    return data


def wallet_identity(owner, report_digest, sheet):
    return str(uuid5(NAMESPACE_URL, f"xtb-wallet:{owner}:{report_digest}:{sheet}"))


def wallet_plan(wallet, row, owner, report_digest):
    checkpoint = xtb_checkpoint(row["ledger"]) if row else wallet.get("checkpoint")
    plan = prepare_import(
        wallet["parsed"],
        row["transactions"] if row else [],
        "fifo",
        checkpoint=checkpoint if row else None,
    )
    error = wallet["error"]
    if not error and not row and plan["errors"] and not plan["ready"]:
        error = "import_no_transactions"
    if not error and row and plan["ready"]:
        error = "import_preview_changed"
    if checkpoint:
        plan["ledger"].append(checkpoint)
    return {
        **plan,
        "id": wallet_identity(owner, report_digest, wallet["sheet"]),
        "name": row["name"] if row else wallet["name"],
        "sheet": wallet["sheet"],
        "version": row["version"] if row else None,
        "error": error,
        "reconciliation": reconciliation_view(checkpoint),
    }


class PortfolioRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get(self, owner, portfolio_id):
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PortfolioRow).where(
                        PortfolioRow.user_id == owner,
                        PortfolioRow.id == portfolio_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise PortfolioError("not_found", 404)
            return response(row, include_ledger=True)

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
            return [response(row, include_ledger=True) for row in rows]

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

    async def quote_history(
        self, tickers: set[str], start: date, end: date
    ) -> dict[str, list[dict]]:
        """Return in-window closes and one prior close per ticker for carrying prices forward."""
        if not tickers:
            return {}

        quote = DailyQuoteRow
        # PostgreSQL numeric can hold NaN, which compares greater than zero.
        usable = (quote.close > 0) & (quote.close - quote.close == 0)
        window = select(quote.ticker, quote.date, quote.close).where(
            quote.ticker.in_(tickers), quote.date.between(start, end), usable
        )
        prior_dates = (
            select(quote.ticker, func.max(quote.date).label("date"))
            .where(quote.ticker.in_(tickers), quote.date < start, usable)
            .group_by(quote.ticker)
            .subquery()
        )
        prior = select(quote.ticker, quote.date, quote.close).join(
            prior_dates, (quote.ticker == prior_dates.c.ticker) & (quote.date == prior_dates.c.date)
        )
        statement = window.union_all(prior).order_by("ticker", "date")
        history = {}
        async with self._session_factory() as session:
            for ticker, day, price in (await session.execute(statement)).all():
                history.setdefault(ticker, []).append({"price": price, "date": day})
        return history

    async def preview_wallets(self, owner, wallets, report_digest):
        existing = {row["id"]: row for row in await self.list(owner)}
        plans = []
        for wallet in wallets:
            prior = existing.get(wallet_identity(owner, report_digest, wallet["sheet"]))
            plan = wallet_plan(wallet, prior, owner, report_digest)
            plans.append({k: v for k, v in plan.items() if k not in {"additions", "ledger"}})
        new_wallets = sum(plan["version"] is None for plan in plans)
        return {
            "wallets": plans,
            "ready": sum(plan["ready"] for plan in plans),
            "errors": sum(plan["errors"] or bool(plan["error"]) for plan in plans),
            "newWallets": new_wallets,
            "blockingError": "portfolio_limit" if len(existing) + new_wallets > 20 else None,
        }

    async def import_wallets(self, owner, wallets, report_digest, allow_partial=False):
        """Create all worksheet wallets atomically; a retried upload never overwrites one."""
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    select(UserRow.id).where(UserRow.id == owner).with_for_update()
                )
                identities = [wallet_identity(owner, report_digest, w["sheet"]) for w in wallets]
                rows = (
                    (
                        await session.execute(
                            select(PortfolioRow)
                            .where(PortfolioRow.id.in_(identities))
                            .with_for_update()
                        )
                    )
                    .scalars()
                    .all()
                )
                if any(row.user_id != owner for row in rows):
                    raise PortfolioError("conflict")
                existing = {row.id: row for row in rows}
                plans = [
                    wallet_plan(
                        w,
                        response(existing[key], include_ledger=True) if key in existing else None,
                        owner,
                        report_digest,
                    )
                    for w, key in zip(wallets, identities, strict=True)
                ]
                for plan in plans:
                    if plan["error"]:
                        status = 409 if plan["error"] == "import_preview_changed" else 422
                        raise PortfolioError(plan["error"], status)
                    if plan["errors"] and not allow_partial:
                        raise PortfolioError("import_rows_invalid", 422)
                    if plan["ledgerError"]:
                        raise PortfolioError(plan["ledgerError"])
                count = (
                    await session.execute(
                        select(func.count())
                        .select_from(PortfolioRow)
                        .where(PortfolioRow.user_id == owner)
                    )
                ).scalar_one()
                created = sum(plan["id"] not in existing for plan in plans)
                if count + created > 20:
                    raise PortfolioError("portfolio_limit")
                results = []
                for plan in plans:
                    row = existing.get(plan["id"])
                    if row is None:
                        row = PortfolioRow(
                            id=plan["id"],
                            user_id=owner,
                            name=plan["name"],
                            broker="XTB",
                            cost_method="fifo",
                            transactions=plan["ledger"],
                            version=1,
                            created_at=datetime.now(UTC),
                        )
                        session.add(row)
                    results.append(
                        {
                            "id": row.id,
                            "name": row.name,
                            "version": row.version,
                            "imported": plan["ready"],
                            "duplicates": plan["duplicates"],
                            "skipped": plan["errors"],
                        }
                    )
                return {
                    "wallets": results,
                    "created": created,
                    **{
                        key: sum(row[key] for row in results)
                        for key in ("imported", "duplicates", "skipped")
                    },
                }

    async def change(
        self,
        owner,
        operation,
        *,
        portfolio_id=None,
        payload=None,
        version=None,
        transaction_id=None,
        parsed=None,
        allow_partial=False,
    ):
        async with self._session_factory() as session:
            async with session.begin():
                # Shared lock across account writes handles creation limits and retry races.
                owner_active = (
                    await session.execute(
                        select(UserRow.is_active).where(UserRow.id == owner).with_for_update()
                    )
                ).scalar_one_or_none()
                if operation == "automated_import" and not owner_active:
                    raise PortfolioError("not_found", 404)
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
                checkpoint = xtb_checkpoint(row.transactions)
                if operation in {"import", "automated_import"}:
                    plan = prepare_import(
                        parsed,
                        response(row)["transactions"],
                        row.cost_method,
                        checkpoint=checkpoint,
                    )
                    if plan["errors"] and not allow_partial:
                        raise PortfolioError("import_rows_invalid", 422)
                    if plan["ledgerError"]:
                        raise PortfolioError(plan["ledgerError"])
                    # Browser imports commit their preview version. Automation validates
                    # the complete import against the current ledger under the row lock.
                    if operation == "import" and plan["ready"] and row.version != version:
                        raise PortfolioError("conflict")
                    if plan["ready"]:
                        row.transactions = (
                            [*plan["ledger"], checkpoint] if checkpoint else plan["ledger"]
                        )
                        row.version += 1
                    return {
                        "imported": plan["ready"],
                        "duplicates": plan["duplicates"],
                        "skipped": plan["errors"],
                        "version": row.version,
                    }
                if operation == "add":
                    trade = payload.model_dump(mode="json", exclude={"version"})
                    existing = next(
                        (t for t in row.transactions if t.get("id") == trade["id"]), None
                    )
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
                    if len(row.transactions) - bool(checkpoint) >= 1000:
                        raise PortfolioError("transaction_limit")
                    require_after_checkpoint(trade, checkpoint)
                    trades = [*row.transactions, trade]
                    holdings(trades)  # Validate the entire dated ledger, including backdated sales.
                    row.transactions = trades
                elif operation == "remove":
                    original = next(
                        (t for t in row.transactions if t.get("id") == transaction_id), None
                    )
                    if original is not None:
                        require_after_checkpoint(original, checkpoint)
                    trades = [t for t in row.transactions if t.get("id") != transaction_id]
                    if len(trades) == len(row.transactions):
                        raise PortfolioError("not_found", 404)
                    holdings(trades)
                    row.transactions = trades
                elif operation == "delete":
                    await session.delete(row)
                    return {"ok": True}
                row.version += 1
                return response(row)
