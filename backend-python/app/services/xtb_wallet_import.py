"""Import each XTB worksheet as an independent wallet, including position reports."""

import hashlib
import json
import re
from collections import Counter
from datetime import UTC
from decimal import Decimal, DecimalException

from app.services.portfolio import WARSAW, PortfolioError
from app.services.xtb_import import (
    ACCOUNT_CURRENCY_LABELS,
    ACCOUNT_ID_LABELS,
    ALIASES,
    SECTION_NAMES,
    ParsedImport,
    RowError,
    _header,
    _trade,
    decimal_value,
    is_summary_row,
    normalized,
    parse_xtb_tables,
    read_tables,
    report_broker_account_currency,
    report_broker_account_id,
    timestamp,
)
from app.services.xtb_reconciliation import reconcile_cash_wallets

SNAPSHOT_HEADERS = {
    "ticker": {"ticker", "symbol", "walor"},
    "side": {"type", "typ", "side"},
    "quantity": {"volume", "quantity", "wolumen", "ilosc"},
    "openPrice": {"openprice", "cenaotwarcia"},
    "openTime": {"opentime", "opentimeutc", "czasotwarcia", "czasotwarciautc"},
    "closePrice": {"closeprice", "cenazamkniecia"},
    "closeTime": {"closetime", "closetimeutc", "czaszamkniecia", "czaszamknieciautc"},
    "position": {"positionid", "instrumentposition", "idpozycji", "instrumentpozycja"},
    "assetType": {"category", "instrumenttype", "assettype", "kategoria"},
    "fees": {"commission", "opencommission", "prowizja", "prowizjaotwarcia"},
    "feeCurrency": {"feecurrency", "commissioncurrency", "walutaprowizji"},
    "currency": {"currency", "waluta"},
    "accountCurrency": ACCOUNT_CURRENCY_LABELS,
    "priceCurrency": ALIASES["priceCurrency"],
}


def _snapshot_header(sheet, values):
    kind = SECTION_NAMES.get(normalized(sheet))
    for index, row in enumerate(values[:40]):
        columns = {}
        ambiguous = False
        for position, value in enumerate(row):
            key_name = normalized(value)
            for key, aliases in SNAPSHOT_HEADERS.items():
                if key_name in aliases:
                    if key in columns:
                        if key != "ticker":
                            ambiguous = True
                        elif key_name != "ticker":
                            continue
                    columns[key] = position
        if {"ticker", "side", "quantity", "openPrice", "openTime", "position"} <= columns.keys():
            close_fields = {"closePrice", "closeTime"} & columns.keys()
            closed = len(close_fields) == 2
            if (
                ambiguous
                or ((close_fields or kind == "Closed Positions") and not closed)
                or (kind == "Open Positions" and closed)
            ):
                raise PortfolioError("import_unrecognized_format", 422)
            return index, columns, closed
    return None


def _position_id(value):
    if value in (None, ""):
        raise RowError("missing_reference")
    if isinstance(value, (int, float, Decimal)):
        number = decimal_value(value)
        if number != number.to_integral_value():
            raise RowError("missing_reference")
        return str(int(number))
    value = str(value).strip()
    if not value or len(value) > 100:
        raise RowError("missing_reference")
    return value


def _snapshot_reference(get, *, closed, occurrences):
    # Position IDs can recur for partial closures. Include the executed slice,
    # rather than its row number, so reordering a report retains its identity.
    identity = [
        "closed" if closed else "open",
        _position_id(get("position")),
        str(get("ticker") or "").strip().lower(),
        timestamp(get("openTime")).replace(tzinfo=None).isoformat(timespec="microseconds"),
        str(decimal_value(get("quantity")).normalize()),
        str(decimal_value(get("openPrice")).normalize()),
    ]
    if closed:
        identity.extend(
            [
                timestamp(get("closeTime")).replace(tzinfo=None).isoformat(timespec="microseconds"),
                str(decimal_value(get("closePrice")).normalize()),
            ]
        )
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()
    occurrences[digest] += 1
    return f"position:{digest}:{occurrences[digest]}"


def _parse_positions(sheet, values, header, companies):
    # Keep each source position atomic: a rejected close must not leave behind
    # a fabricated purchase for that same closed slice.
    header_index, columns, closed = header
    labels = values[header_index]
    open_utc = normalized(labels[columns["openTime"]]).endswith("utc")
    close_utc = closed and normalized(labels[columns["closeTime"]]).endswith("utc")
    rows, ignored, occurrences, categories = [], 0, Counter(), {}
    warnings = {"closed_positions_snapshot" if closed else "open_positions_snapshot"}
    for index, cells in enumerate(values[header_index + 1 :], header_index + 2):
        if not any(value not in (None, "") for value in cells):
            continue

        def get(key, cells=cells):
            position = columns.get(key)
            return cells[position] if position is not None and position < len(cells) else None

        if is_summary_row(cells, reference=get("position"), side=get("side"), time=get("openTime")):
            ignored += 1
            continue
        source = {"sheet": sheet, "row": index, "symbol": str(get("ticker") or "")[:80]}
        try:
            if any(isinstance(value, str) and value.startswith("=") for value in cells):
                raise RowError("formula_cell")
            ticker_key = str(get("ticker") or "").strip().lower()
            # Native instrument aggregates have a descriptive name, a category,
            # and no opening time. An individual lot with a missing direction
            # is still an invalid trade, even if its time is also missing.
            position = str(get("position") or "").strip()
            if (
                not closed
                and not get("side")
                and not get("openTime")
                and ticker_key
                and get("assetType")
                and position
                and re.fullmatch(r"\d+(?:\.0+)?", position) is None
            ):
                categories[ticker_key] = get("assetType")
                ignored += 1
                continue
            if normalized(get("side")) not in {"buy", "kupno"}:
                raise RowError("unsupported_operation")
            reference = _snapshot_reference(get, closed=closed, occurrences=occurrences)
            common = {
                "reference": reference,
                "ticker": get("ticker"),
                "quantity": get("quantity"),
                "assetType": get("assetType") or categories.get(ticker_key),
                "priceCurrency": get("priceCurrency"),
                "currency": get("currency") or get("accountCurrency"),
                "feeCurrency": get("feeCurrency"),
            }
            buy = {
                **common,
                "side": "buy",
                "price": get("openPrice"),
                "time": get("openTime"),
                "fees": 0 if closed else get("fees"),
            }
            trades = []
            row_warnings = []
            trade, notices = _trade(
                buy.get, companies, False, utc_time=open_utc, account_currency=True
            )
            trades.append(trade)
            row_warnings.extend(notices)
            if closed:
                opened = timestamp(get("openTime"), assume_utc=open_utc)
                finished = timestamp(get("closeTime"), assume_utc=close_utc)
                if opened.tzinfo or finished.tzinfo:
                    opened = opened.replace(tzinfo=opened.tzinfo or WARSAW)
                    finished = finished.replace(tzinfo=finished.tzinfo or WARSAW)
                if finished < opened:
                    raise RowError("invalid_date")
                sell = {
                    **common,
                    "side": "sell",
                    "price": get("closePrice"),
                    "time": get("closeTime"),
                    "fees": get("fees"),
                }
                trade, notices = _trade(
                    sell.get, companies, False, utc_time=close_utc, account_currency=True
                )
                trades.append(trade)
                row_warnings.extend(notices)
            rows.extend({**source, "status": "ready", "transaction": trade} for trade in trades)
            warnings.update(row_warnings)
        except RowError as exc:
            rows.append({**source, "status": "error", "code": str(exc)})
        except DecimalException:
            rows.append({**source, "status": "error", "code": "invalid_number"})
    if len(rows) > 1000:
        raise PortfolioError("transaction_limit")
    return ParsedImport(rows, ignored, sorted(warnings))


def _report_metadata(values, header):
    account = None
    snapshot_as_of = None
    for row in values[: header[0] if header else 40]:
        if len(row) < 2:
            continue
        label, value = normalized(row[0]), row[1]
        if label in ACCOUNT_ID_LABELS and value not in (None, ""):
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            account = str(value).strip() or None
        if label == "dataasofreportgenerated" and header and not header[2]:
            try:
                snapshot_as_of = (
                    timestamp(value, assume_utc=True)
                    .astimezone(UTC)
                    .isoformat(timespec="microseconds")
                )
            except (RowError, OverflowError):
                pass
    metadata = {"account": account}
    if header and not header[2]:
        metadata["snapshotAsOf"] = snapshot_as_of
    return metadata


def parse_xtb_wallets(data: bytes, filename: str, companies) -> list[dict]:
    wallets = []
    identities = set()
    next_suffixes = Counter()
    tables = read_tables(data, filename)
    for sheet, values in tables:
        occurrence = next_suffixes[sheet] + 1
        identity = sheet if occurrence == 1 else f"{sheet} ({occurrence})"
        while identity in identities:
            occurrence += 1
            identity = f"{sheet} ({occurrence})"
        identities.add(identity)
        next_suffixes[sheet] = occurrence
        header = None
        native_section = None
        try:
            header = _snapshot_header(sheet, values)
            if header:
                native_section = "Closed Positions" if header[2] else "Open Positions"
            elif SECTION_NAMES.get(normalized(sheet)) == "Cash Operations" and any(
                (columns := _header(row)) and {"amount", "comment"} <= columns.keys()
                for row in values[:40]
            ):
                native_section = "Cash Operations"
            parsed = (
                _parse_positions(sheet, values, header, companies)
                if header
                else parse_xtb_tables([(sheet, values)], companies, allow_empty=True)
            )
            if header:
                header_index, columns, _ = header
                parsed.broker_account_id = report_broker_account_id(values[:header_index])
                currency_column = columns.get("accountCurrency")
                currencies = ()
                if currency_column is not None:
                    currencies = (
                        row[currency_column]
                        for row in values[header_index + 1 :]
                        if currency_column < len(row)
                    )
                parsed.broker_account_currency = report_broker_account_currency(
                    values[:header_index], currencies
                )
            error = None
        except PortfolioError as exc:
            parsed, error = ParsedImport([], 0, []), exc.code
        wallets.append(
            {
                "sheet": identity,
                "section": sheet,
                "nativeSection": native_section,
                "name": identity[:80],
                "brokerAccountId": parsed.broker_account_id,
                "parsed": parsed,
                "error": error,
                **_report_metadata(values, header),
            }
        )
    if not wallets:
        raise PortfolioError("import_no_transactions", 422)
    reconcile_cash_wallets(wallets, tables)
    return wallets
