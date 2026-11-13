"""Reconcile a native cash ledger with the matching XTB open-lot snapshot."""

from collections import defaultdict
from decimal import Decimal, localcontext

from app.services.portfolio import (
    WARSAW,
    XTB_RECONCILIATION,
    holdings,
    trade_order,
)
from app.services.xtb_import import (
    RowError,
    decimal_value,
    normalized,
    prepare_import,
    timestamp,
)


def _section(values, required):
    for index, row in enumerate(values[:40]):
        columns = [normalized(value) for value in row]
        if required <= set(columns):
            return {
                row_number: dict(zip(columns, cells, strict=False))
                for row_number, cells in enumerate(values[index + 1 :], index + 2)
            }
    return {}


def _metadata(values, label):
    return next(
        (row[1] for row in values[:8] if len(row) > 1 and normalized(row[0]) == label), None
    )


def _lot_key(row, id_column):
    reference = row.get(id_column)
    if isinstance(reference, float) and reference.is_integer():
        reference = int(reference)
    return str(reference or "").strip(), str(row.get("ticker") or "").strip().upper()


def _linked_sections(cash_rows, open_rows, cash_plan, open_plan):
    cash_details = [cash_rows.get(row["row"], {}) for row in cash_plan["rows"]]
    open_details = [open_rows.get(row["row"], {}) for row in open_plan["rows"]]
    products = {
        str(row.get("product") or "").strip().upper() for row in [*cash_details, *open_details]
    }
    if len(products) != 1 or "" in products:
        return False
    cash_keys = {_lot_key(row, "positionid") for row in cash_details}
    open_keys = {_lot_key(row, "instrumentposition") for row in open_details}
    return any(reference and ticker for reference, ticker in cash_keys & open_keys)


def _snapshot_matches_summaries(open_rows, open_plan):
    lots, summaries = defaultdict(Decimal), defaultdict(Decimal)
    for row in open_plan["rows"]:
        lots[str(row["symbol"]).strip().upper()] += Decimal(row["transaction"]["quantity"])
    for row in open_rows.values():
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and not row.get("type"):
            summaries[ticker] += decimal_value(row.get("volume"))
    return bool(lots) and lots == summaries


def reconciliation_view(checkpoint):
    if checkpoint is None:
        return None
    return {
        "asOf": checkpoint["executedAt"],
        "changes": checkpoint["changes"],
    }


def _checkpoint(cash, opened, cash_values, open_values):
    cash_plan = prepare_import(cash["parsed"], [], "fifo")
    open_plan = prepare_import(opened["parsed"], [], "fifo")
    if any(plan["errors"] or plan["ledgerError"] for plan in (cash_plan, open_plan)):
        return None
    if not opened.get("snapshotAsOf"):
        return None
    try:
        as_of = timestamp(opened["snapshotAsOf"])
        cash_end = timestamp(_metadata(cash_values, "datetoutc"), assume_utc=True)
        # Both sections come from one export. Do not combine a later snapshot
        # with an independently selected historical cash-report interval.
        if not 0 <= (as_of - cash_end).total_seconds() <= 60:
            return None
        cash_rows = _section(cash_values, {"product", "positionid", "ticker"})
        open_rows = _section(open_values, {"product", "instrumentposition", "ticker", "type"})
        if not _linked_sections(cash_rows, open_rows, cash_plan, open_plan):
            return None
        if not _snapshot_matches_summaries(open_rows, open_plan):
            return None
    except RowError:
        return None

    event = {
        "kind": XTB_RECONCILIATION,
        "date": as_of.astimezone(WARSAW).date().isoformat(),
        "executedAt": as_of.isoformat(timespec="microseconds"),
        "positions": [],
        "changes": [],
    }
    if any(
        trade_order(trade) > trade_order(event)
        for plan in (cash_plan, open_plan)
        for trade in plan["ledger"]
    ):
        return None

    def positions(plan):
        return {(p["ticker"], p["currency"]): p for p in holdings(plan["ledger"], "fifo")}

    previous, snapshot = positions(cash_plan), positions(open_plan)
    with localcontext() as context:
        context.prec = 50
        lots = defaultdict(list)
        for trade in open_plan["ledger"]:
            quantity = Decimal(trade["quantity"])
            cost = quantity * Decimal(trade["price"]) + Decimal(trade["fees"])
            lots[trade["ticker"], trade["currency"]].append(
                {"quantity": str(quantity), "cost": str(cost)}
            )
        for ticker, currency in sorted(previous.keys() | snapshot.keys()):
            key = (ticker, currency)
            old, new = previous.get(key, {}), snapshot.get(key, {})
            current = {
                "ticker": ticker,
                "currency": currency,
                "quantity": str(new.get("quantity", 0)),
                "cost": str(new.get("cost", 0)),
            }
            event["positions"].append({**current, "lots": lots[key]})
            if all(old.get(field, 0) == new.get(field, 0) for field in ("quantity", "cost")):
                continue
            event["changes"].append(
                {
                    **current,
                    "previousQuantity": str(old.get("quantity", 0)),
                    "previousCost": str(old.get("cost", 0)),
                }
            )
    return event


def reconcile_cash_wallets(wallets, tables):
    cash = [wallet for wallet in wallets if wallet["nativeSection"] == "Cash Operations"]
    opened = [wallet for wallet in wallets if wallet["nativeSection"] == "Open Positions"]
    if len(cash) != 1 or len(opened) != 1:
        return
    cash, opened = cash[0], opened[0]
    cash_account, open_account = cash["brokerAccountId"], opened["brokerAccountId"]
    different_account = cash_account and open_account and cash_account != open_account
    if different_account:
        # The two history tabs identify the account on a full export. The open
        # snapshot can carry a different number and still show that account's lots.
        closed = [wallet for wallet in wallets if wallet["nativeSection"] == "Closed Positions"]
        if len(wallets) != 3 or len(closed) != 1 or closed[0]["brokerAccountId"] != cash_account:
            cash["parsed"].warnings.append("xtb_reconciliation_unavailable")
            return
        opened["supplementalSnapshot"] = True
    cash_currency = cash["parsed"].broker_account_currency
    open_currency = opened["parsed"].broker_account_currency
    if cash["error"] or opened["error"] or (
        cash_currency and open_currency and open_currency != cash_currency
    ):
        cash["parsed"].warnings.append("xtb_reconciliation_unavailable")
        return
    values = dict(tables)
    checkpoint = _checkpoint(cash, opened, values[cash["section"]], values[opened["section"]])
    if checkpoint is None:
        cash["parsed"].warnings.append("xtb_reconciliation_unavailable")
    elif checkpoint["changes"]:
        cash["checkpoint"] = checkpoint
        cash["checkpointSheet"] = opened["sheet"]
