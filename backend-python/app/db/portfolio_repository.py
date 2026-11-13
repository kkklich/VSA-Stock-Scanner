"""Account-scoped, versioned portfolio persistence and batched stored quote lookup."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from app.db.models import DailyQuoteRow, PortfolioRow, UserRow
from app.services.portfolio import (
    WARSAW,
    XTB_RECONCILIATION,
    PortfolioError,
    check_broker_account,
    holdings,
    require_after_checkpoint,
    trade_order,
    xtb_checkpoint,
)
from app.services.xtb_import import ParsedImport, prepare_import
from app.services.xtb_reconciliation import reconciliation_view


def response(row, *, include_ledger=False):
    ledger = row.transactions
    checkpoint = xtb_checkpoint(ledger)
    data = {
        "id": row.id,
        "name": row.name,
        "broker": row.broker,
        "brokerAccountId": row.broker_account_id,
        "brokerAccountCurrency": row.broker_account_currency,
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


def wallet_plan(sources, row, wallet_id, account, account_currency, *, exact, skip=False):
    first = sources[0]
    old_account = row["brokerAccountId"] if row else None
    old_currency = row["brokerAccountCurrency"] if row else None
    check_broker_account(old_account, account)
    check_account_currency(old_currency, account_currency)
    parsed = ParsedImport(
        [] if skip else [entry for source in sources for entry in source["parsed"].rows],
        0 if skip else sum(source["parsed"].ignored for source in sources),
        []
        if skip
        else sorted({warning for source in sources for warning in source["parsed"].warnings}),
    )
    old_checkpoint = xtb_checkpoint(row["ledger"]) if row else None
    checkpoint = old_checkpoint
    if len(sources) == 1 and (not row or not row["ledger"]):
        checkpoint = first.get("checkpoint")
    if not checkpoint and len(sources) == 1 and (not row or not row["ledger"]):
        # A dated open-position snapshot can seed a ledger. Its cutoff guards
        # subsequent cash imports against replaying the fills behind that snapshot.
        if _section(first) == "Open Positions" and first.get("snapshotAsOf") and parsed.rows:
            as_of = datetime.fromisoformat(first["snapshotAsOf"])
            checkpoint = {
                "kind": XTB_RECONCILIATION,
                "date": as_of.astimezone(WARSAW).date().isoformat(),
                "executedAt": first["snapshotAsOf"],
                "positions": [],
                "changes": [],
            }
    error = None if skip else next((source["error"] for source in sources if source["error"]), None)
    if checkpoint and not old_checkpoint:
        checkpoint_order = trade_order(checkpoint)
        if any(
            trade_order(entry["transaction"]) > checkpoint_order
            for entry in parsed.rows
            if entry.get("transaction")
        ):
            checkpoint = None
    plan = prepare_import(
        parsed,
        row["transactions"] if row else [],
        row["costMethod"] if row else "fifo",
        checkpoint=old_checkpoint,
    )
    if not error and not row and plan["errors"] and not plan["ready"]:
        error = "import_no_transactions"
    if not error and exact and plan["ready"]:
        error = "import_preview_changed"
    if checkpoint:
        plan["ledger"].append(checkpoint)
    can_link = not row or (
        row["broker"].casefold() == "xtb" and bool(plan["ready"] or plan["duplicates"])
    )
    broker_account_id = old_account or (account if can_link else None)
    broker_account_currency = old_currency or (account_currency if can_link else None)
    return {
        **plan,
        "id": wallet_id,
        "name": row["name"] if row else first["name"],
        "brokerAccountId": broker_account_id,
        "sourceBrokerAccountId": account,
        "linksBrokerAccount": bool(broker_account_id and not old_account),
        "brokerAccountCurrency": broker_account_currency,
        "sourceBrokerAccountCurrency": account_currency,
        "setsBrokerAccountCurrency": bool(broker_account_currency and not old_currency),
        "sheet": first["sheet"],
        "version": row["version"] if row else None,
        "error": error,
        "reconciliation": reconciliation_view(checkpoint)
        if checkpoint and checkpoint["changes"]
        else None,
    }


def check_account_currency(expected, received):
    if expected and received and expected != received:
        raise PortfolioError("broker_account_currency_mismatch")


def _section(wallet):
    return wallet["nativeSection"]


def _source_currency(wallet):
    return wallet["parsed"].broker_account_currency


def _wallet_groups(wallets):
    native_accounts = {}
    for wallet in wallets:
        if _section(wallet) and (account := wallet["brokerAccountId"]):
            currencies = native_accounts.setdefault(account, set())
            if account_currency := _source_currency(wallet):
                currencies.add(account_currency)
    native_currencies = {
        account_currency
        for wallet in wallets
        if _section(wallet) and (account_currency := _source_currency(wallet))
    }
    groups = {}
    for wallet in wallets:
        account = wallet["brokerAccountId"]
        account_currency = _source_currency(wallet)
        if not account and _section(wallet):
            matching = [
                account_id
                for account_id, currencies in native_accounts.items()
                if not account_currency or not currencies or account_currency in currencies
            ]
            if len(matching) == 1:
                account = matching[0]
            elif len(matching) > 1:
                raise PortfolioError("import_ambiguous_wallet", 422)
            elif not account_currency and len(native_currencies) == 1:
                account_currency = next(iter(native_currencies))
            elif not account_currency and len(native_currencies) > 1:
                raise PortfolioError("import_ambiguous_wallet", 422)
        if account:
            key = ("account", account)
        elif _section(wallet):
            key = ("native", account_currency)
        else:
            key = ("sheet", wallet["sheet"])
        group = groups.setdefault(key, [])
        if _section(wallet) and any(
            _section(other) == _section(wallet)
            and not (wallet["brokerAccountId"] and other["brokerAccountId"])
            for other in group
        ):
            raise PortfolioError("import_ambiguous_wallet", 422)
        group.append(wallet)
    return list(groups.values())


def _trade_sources(group):
    # Cash and generic executed trades describe fills. Native position sheets
    # are alternative views and must not be added alongside those fills.
    for section in ("Cash Operations", None, "Open Positions", "Closed Positions"):
        sources = [wallet for wallet in group if _section(wallet) == section]
        if any(wallet["parsed"].rows or wallet["error"] for wallet in sources):
            return sources
    return [next((wallet for wallet in group if _section(wallet) == "Cash Operations"), group[0])]


def wallet_plans(owner, wallets, report_digest, existing, target_wallet_id):
    target = existing.get(target_wallet_id)
    if target_wallet_id is not None and target is None:
        raise PortfolioError("not_found", 404)
    linked = {row["brokerAccountId"]: row for row in existing.values() if row["brokerAccountId"]}
    supplemental = {wallet["sheet"] for wallet in wallets if wallet.get("supplementalSnapshot")}
    routed = [wallet for wallet in wallets if wallet["sheet"] not in supplemental]
    plans, skipped = [], set(supplemental)
    for group in [routed] if target else _wallet_groups(routed):
        accounts = {wallet["brokerAccountId"] for wallet in group if wallet["brokerAccountId"]}
        if len(accounts) > 1:
            raise PortfolioError("import_multiple_broker_accounts", 422)
        currencies = {_source_currency(wallet) for wallet in group if _source_currency(wallet)}
        if len(currencies) > 1:
            raise PortfolioError("import_multiple_account_currencies", 422)
        account = next(iter(accounts), None)
        account_currency = next(iter(currencies), None)
        sources = _trade_sources(group)
        key = wallet_identity(owner, report_digest, sources[0]["sheet"])
        linked_wallet = linked.get(account)
        if target:
            check_broker_account(target["brokerAccountId"], account)
            if linked_wallet and target["id"] != linked_wallet["id"]:
                raise PortfolioError("broker_account_already_linked")
        row = target or linked_wallet or existing.get(key)
        exact = bool(row and row["id"] == key)
        snapshot = _section(sources[0]) in {"Open Positions", "Closed Positions"}
        skip = bool(
            row
            and row["ledger"]
            and snapshot
            and not exact
            and not _snapshot_is_saved(row, sources)
        )
        source_sheets = {wallet["sheet"] for wallet in sources} if not skip else set()
        skipped.update(wallet["sheet"] for wallet in group if wallet["sheet"] not in source_sheets)
        plan = wallet_plan(
            sources,
            row,
            row["id"] if row else key,
            account,
            account_currency,
            exact=exact,
            skip=skip,
        )
        snapshot_sheet = sources[0].get("checkpointSheet")
        if snapshot_sheet and xtb_checkpoint(plan["ledger"]) == sources[0]["checkpoint"]:
            skipped.discard(snapshot_sheet)
        plans.append(plan)
    return plans, [wallet["sheet"] for wallet in wallets if wallet["sheet"] in skipped]


def _snapshot_is_saved(row, sources):
    trades = [
        entry["transaction"]
        for source in sources
        for entry in source["parsed"].rows
        if entry.get("transaction")
    ]
    existing = {trade["id"]: trade for trade in row["transactions"]}
    return bool(trades) and all(existing.get(trade["id"]) == trade for trade in trades)


async def require_broker_account_available(session, owner, portfolio_id, account):
    if account is None:
        return
    existing = (
        await session.execute(
            select(PortfolioRow.id).where(
                PortfolioRow.user_id == owner,
                PortfolioRow.broker_account_id == account,
                PortfolioRow.id != portfolio_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise PortfolioError("broker_account_already_linked")


async def broker_account_for_import(session, owner, portfolio_id, broker, current, received):
    check_broker_account(current, received)
    if current or received is None or broker.casefold() != "xtb":
        return current
    await require_broker_account_available(session, owner, portfolio_id, received)
    return received


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

    async def preview_import_account(self, owner, portfolio, parsed):
        check_account_currency(portfolio["brokerAccountCurrency"], parsed.broker_account_currency)
        async with self._session_factory() as session:
            return await broker_account_for_import(
                session,
                owner,
                portfolio["id"],
                portfolio["broker"],
                portfolio["brokerAccountId"],
                parsed.broker_account_id,
            )

    async def preview_wallets(self, owner, wallets, report_digest, *, target_wallet_id=None):
        existing = {row["id"]: row for row in await self.list(owner)}
        raw_plans, skipped = wallet_plans(owner, wallets, report_digest, existing, target_wallet_id)
        plans = [
            {k: v for k, v in plan.items() if k not in {"additions", "ledger"}}
            for plan in raw_plans
        ]
        new_wallets = sum(plan["version"] is None for plan in plans)
        return {
            "wallets": plans,
            "skippedSheets": skipped,
            "ready": sum(plan["ready"] for plan in plans),
            "errors": sum(plan["errors"] or bool(plan["error"]) for plan in plans),
            "newWallets": new_wallets,
            "blockingError": "portfolio_limit" if len(existing) + new_wallets > 20 else None,
        }

    async def import_wallets(
        self,
        owner,
        wallets,
        report_digest,
        allow_partial=False,
        *,
        verify_preview,
        target_wallet_id=None,
    ):
        """Save the reviewed XTB import atomically and safely retry a completed import."""
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    select(UserRow.id).where(UserRow.id == owner).with_for_update()
                )
                rows = (
                    (
                        await session.execute(
                            select(PortfolioRow)
                            .where(PortfolioRow.user_id == owner)
                            .with_for_update()
                        )
                    )
                    .scalars()
                    .all()
                )
                existing = {row.id: row for row in rows}
                plans, _ = wallet_plans(
                    owner,
                    wallets,
                    report_digest,
                    {row.id: response(row, include_ledger=True) for row in rows},
                    target_wallet_id,
                )
                verify_preview(plans)
                for plan in plans:
                    if plan["error"]:
                        status = 409 if plan["error"] == "import_preview_changed" else 422
                        raise PortfolioError(plan["error"], status)
                    if plan["errors"] and not allow_partial:
                        raise PortfolioError("import_rows_invalid", 422)
                    if plan["ledgerError"]:
                        raise PortfolioError(plan["ledgerError"])
                new_ids = {plan["id"] for plan in plans if plan["id"] not in existing}
                if len(existing) + len(new_ids) > 20:
                    raise PortfolioError("portfolio_limit")
                if (
                    new_ids
                    and (
                        await session.execute(
                            select(PortfolioRow.id).where(PortfolioRow.id.in_(new_ids)).limit(1)
                        )
                    ).scalar_one_or_none()
                ):
                    raise PortfolioError("conflict")
                results = []
                for plan in plans:
                    row = existing.get(plan["id"])
                    if row is None:
                        row = PortfolioRow(
                            id=plan["id"],
                            user_id=owner,
                            name=plan["name"],
                            broker="XTB",
                            broker_account_id=plan["brokerAccountId"],
                            broker_account_currency=plan["brokerAccountCurrency"],
                            cost_method="fifo",
                            transactions=plan["ledger"],
                            version=1,
                            created_at=datetime.now(UTC),
                        )
                        session.add(row)
                    elif (
                        plan["ready"]
                        or plan["linksBrokerAccount"]
                        or plan["setsBrokerAccountCurrency"]
                    ):
                        if plan["ready"]:
                            row.transactions = plan["ledger"]
                        row.broker_account_id = plan["brokerAccountId"]
                        row.broker_account_currency = plan["brokerAccountCurrency"]
                        row.version += 1
                    results.append(
                        {
                            "id": row.id,
                            "name": row.name,
                            "brokerAccountId": row.broker_account_id,
                            "brokerAccountCurrency": row.broker_account_currency,
                            "version": row.version,
                            "imported": plan["ready"],
                            "duplicates": plan["duplicates"],
                            "skipped": plan["errors"],
                        }
                    )
                return {
                    "wallets": results,
                    "created": len(new_ids),
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
                destination = PortfolioRow.id == key
                if operation == "automated_import" and key is None:
                    if parsed.broker_account_id is None:
                        raise PortfolioError("broker_account_required", 422)
                    destination = PortfolioRow.broker_account_id == parsed.broker_account_id
                row = (
                    await session.execute(
                        select(PortfolioRow)
                        .where(
                            PortfolioRow.user_id == owner,
                            destination,
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
                            or (
                                "broker_account_id" in payload.model_fields_set
                                and row.broker_account_id != payload.broker_account_id
                            )
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
                    await require_broker_account_available(
                        session, owner, key, payload.broker_account_id
                    )
                    row = PortfolioRow(
                        id=key,
                        user_id=owner,
                        name=payload.name,
                        broker=payload.broker,
                        broker_account_id=payload.broker_account_id,
                        cost_method=payload.cost_method,
                        transactions=[],
                        version=1,
                        created_at=datetime.now(UTC),
                    )
                    session.add(row)
                    return response(row)
                if row is None:
                    if operation == "automated_import" and key is None:
                        raise PortfolioError("broker_account_unlinked", 404)
                    raise PortfolioError("not_found", 404)
                checkpoint = xtb_checkpoint(row.transactions)
                if operation in {"import", "automated_import"}:
                    received = parsed.broker_account_id
                    account = row.broker_account_id
                    account_currency = row.broker_account_currency
                    check_broker_account(account, received)
                    check_account_currency(account_currency, parsed.broker_account_currency)
                    if operation == "automated_import" and received is not None:
                        if account is None:
                            raise PortfolioError("broker_account_unlinked", 404)
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
                    if (
                        operation == "import"
                        and account is None
                        and (plan["ready"] or plan["duplicates"])
                    ):
                        account = await broker_account_for_import(
                            session, owner, row.id, row.broker, account, received
                        )
                    if row.broker.casefold() == "xtb" and (plan["ready"] or plan["duplicates"]):
                        account_currency = account_currency or parsed.broker_account_currency
                    link_changed = (
                        account != row.broker_account_id
                        or account_currency != row.broker_account_currency
                    )
                    # Browser imports commit their preview version. Automation validates
                    # the complete import against the current ledger under the row lock.
                    if (
                        operation == "import"
                        and (plan["ready"] or link_changed)
                        and row.version != version
                    ):
                        raise PortfolioError("conflict")
                    if plan["ready"]:
                        row.transactions = (
                            [*plan["ledger"], checkpoint] if checkpoint else plan["ledger"]
                        )
                    if plan["ready"] or link_changed:
                        row.broker_account_id = account
                        row.broker_account_currency = account_currency
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
                    account = row.broker_account_id
                    if "broker_account_id" in payload.model_fields_set:
                        account = payload.broker_account_id
                    elif payload.broker.casefold() != "xtb":
                        account = None
                    await require_broker_account_available(session, owner, row.id, account)
                    if payload.broker.casefold() != "xtb" or (
                        row.broker_account_id and account != row.broker_account_id
                    ):
                        row.broker_account_currency = None
                    row.broker_account_id = account
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
