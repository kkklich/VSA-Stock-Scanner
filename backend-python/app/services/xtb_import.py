"""Bounded XTB cash-history / executed-trade imports. Never infer price from cash FX."""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zipfile import BadZipFile, ZipFile

import openpyxl
import xlrd
from defusedxml.common import DefusedXmlException
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError

from app.markets import normalize_ticker, quote_currency
from app.models.portfolio import AddTransaction
from app.services.portfolio import PortfolioError, holdings, trade_order

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
MAX_COLUMNS = 80
MAX_CELL = 4000


def normalized(value) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").replace("ł", "l").replace("Ł", "L"))
    return re.sub(r"[^a-z0-9]", "", value.encode("ascii", "ignore").decode().lower())


ALIASES = {
    "reference": {
        "id",
        "transactionid",
        "operationid",
        "orderid",
        "dealid",
        "numertransakcji",
        "identyfikator",
        "numeroperacji",
        "numerzlecenia",
    },
    "ticker": {"symbol", "ticker", "instrument", "walor"},
    "side": {"type", "typ", "rodzaj", "operation", "operationtype", "typoperacji", "side"},
    "time": {
        "time",
        "date",
        "datetime",
        "czas",
        "data",
        "dataczas",
        "executiontime",
        "transactiontime",
        "datatransakcji",
        "czaswykonania",
    },
    "quantity": {"volume", "quantity", "shares", "wolumen", "ilosc", "liczbasztuk"},
    "price": {"price", "executionprice", "cena", "cenawykonania", "cenazasztuke"},
    "currency": {"currency", "waluta", "accountcurrency", "walutarachunku"},
    "priceCurrency": {"pricecurrency", "instrumentcurrency", "quotecurrency", "walutanotowania"},
    "fees": {"commission", "fees", "fee", "prowizja", "prowizje"},
    "feeCurrency": {"feecurrency", "commissioncurrency", "walutaprowizji"},
    "comment": {"comment", "comments", "komentarz", "description", "opis"},
    "status": {"status", "orderstatus", "statuszlecenia"},
    "assetType": {"instrumenttype", "assettype", "rodzajinstrumentu", "typinstrumentu"},
    "amount": {"amount", "kwota", "value", "wartosc"},
}
BUY = {"stockpurchase", "stockbuy", "zakupakcji", "kupnoakcji", "kupno", "buy"}
SELL = {"stocksell", "stocksale", "sprzedazakcji", "sprzedaz", "sell"}
CASH = {
    "deposit",
    "withdrawal",
    "dividend",
    "divident",
    "dividendtax",
    "withholdingtax",
    "freefundsinterest",
    "freefundsinteresttax",
    "currencyconversion",
    "transfer",
    "subaccounttransfer",
    "wplata",
    "wyplata",
    "dywidenda",
    "podatekoddywidendy",
    "przewalutowanie",
    "odsetki",
    "commission",
    "fee",
    "prowizja",
    "tax",
    "podatek",
}
FILLED = {
    "filled",
    "executed",
    "completed",
    "zrealizowane",
    "wykonane",
    "zrealizowany",
    "wykonany",
    "zrealizowana",
    "wykonana",
}
COMMENT_TRADE = re.compile(
    r"\b(OPEN|CLOSE)\s+(BUY|SELL)\s+([\d.,\xa0\u202f ]+)"
    r"(?:\s*/\s*[\d.,]+)?\s*@\s*([\d.,\xa0\u202f ]+)(?![\w.,])",
    re.IGNORECASE,
)


class RowError(Exception):
    pass


@dataclass
class ParsedImport:
    rows: list[dict]
    ignored: int
    warnings: list[str]


def decimal_value(value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RowError("invalid_number")
    text = str(value).strip().replace("\xa0", " ").replace("\u202f", " ")
    if " " in text:
        if not re.fullmatch(r"[+-]?\d{1,3}(?: \d{3})+(?:[.,]\d+)?", text):
            raise RowError("invalid_number")
        text = text.replace(" ", "")
    if "," in text and "." in text:
        # 1,234.56 and 1.234,56 have an unambiguous final decimal separator.
        pattern = (
            r"[+-]?\d{1,3}(?:,\d{3})+\.\d+"
            if text.rfind(".") > text.rfind(",")
            else r"[+-]?\d{1,3}(?:\.\d{3})+,\d+"
        )
        if not re.fullmatch(pattern, text):
            raise RowError("invalid_number")
        text = (
            text.replace(",", "")
            if text.rfind(".") > text.rfind(",")
            else text.replace(".", "").replace(",", ".")
        )
    else:
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise RowError("invalid_number") from exc
    if not number.is_finite():
        raise RowError("invalid_number")
    return number


def timestamp(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        for pattern in (
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d",
        ):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
    raise RowError("invalid_date")


def currency(value) -> str:
    text = str(value or "").strip()
    return "GBp" if text in {"GBp", "GBX", "GBx"} else text.upper()


def _checked_rows(rows):
    result = []
    for index, row in enumerate(rows):
        if index >= MAX_ROWS or len(row) > MAX_COLUMNS:
            raise PortfolioError("import_too_many_rows", 413)
        values = list(row)
        if any(len(str(value or "")) > MAX_CELL for value in values):
            raise PortfolioError("import_invalid_file", 422)
        result.append(values)
    return result


def read_tables(data: bytes, filename: str) -> list[tuple[str, list[list]]]:
    extension = Path(filename).suffix.lower()
    if len(data) > MAX_FILE_BYTES:
        raise PortfolioError("import_file_too_large", 413)
    if extension not in {".xlsx", ".xls", ".csv"}:
        raise PortfolioError("import_file_type", 422)
    try:
        if extension == ".csv":
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("cp1250")
            lines = text.splitlines()
            if lines and lines[0].lower().startswith("sep="):
                text = "\n".join(lines[1:])
                delimiter = lines[0][4:5]
            else:
                # Headers, rather than metadata, determine the separator.
                delimiter = max(
                    (";", "\t", ","), key=lambda sep: sum(line.count(sep) for line in lines[:30])
                )
            return [("CSV", _checked_rows(csv.reader(io.StringIO(text), delimiter=delimiter)))]
        if extension == ".xls":
            book = xlrd.open_workbook(file_contents=data, on_demand=True)
            try:
                if book.nsheets > 12:
                    raise PortfolioError("import_invalid_file", 422)
                tables = []
                for sheet in book.sheets():
                    if sheet.nrows > MAX_ROWS or sheet.ncols > MAX_COLUMNS:
                        raise PortfolioError("import_too_many_rows", 413)
                    rows = [
                        [
                            xlrd.xldate_as_datetime(cell.value, book.datemode)
                            if cell.ctype == xlrd.XL_CELL_DATE
                            else cell.value
                            for cell in sheet.row(i)
                        ]
                        for i in range(sheet.nrows)
                    ]
                    tables.append((sheet.name, _checked_rows(rows)))
                return tables
            finally:
                book.release_resources()
        # Bound the uncompressed workbook before openpyxl reads shared strings / styles.
        with ZipFile(io.BytesIO(data)) as archive:
            if (
                len(archive.infolist()) > 500
                or sum(info.file_size for info in archive.infolist()) > 30 * 1024 * 1024
            ):
                raise PortfolioError("import_invalid_file", 422)
            if any(info.flag_bits & 1 for info in archive.infolist()):
                raise PortfolioError("import_invalid_file", 422)
        book = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=False, keep_links=False
        )
        try:
            if len(book.worksheets) > 12:
                raise PortfolioError("import_invalid_file", 422)
            tables = []
            total_rows = 0
            for sheet in book.worksheets:
                if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
                    raise PortfolioError("import_too_many_rows", 413)
                rows = _checked_rows(sheet.values)
                total_rows += len(rows)
                if total_rows > MAX_ROWS:
                    raise PortfolioError("import_too_many_rows", 413)
                tables.append((sheet.title, rows))
            return tables
        finally:
            book.close()
    except PortfolioError:
        raise
    except (
        ValueError,
        OSError,
        KeyError,
        BadZipFile,
        csv.Error,
        xlrd.XLRDError,
        UnicodeError,
        SyntaxError,
        TypeError,
        DefusedXmlException,
        InvalidFileException,
    ) as exc:
        raise PortfolioError("import_invalid_file", 422) from exc


def _header(row):
    header = {}
    for index, cell in enumerate(row):
        for key, aliases in ALIASES.items():
            if normalized(cell) in aliases:
                if key in header:
                    if key != "ticker":
                        return None
                    if normalized(cell) != "ticker":
                        continue
                header[key] = index
    if {"reference", "ticker", "side", "time"} <= header.keys():
        if {"quantity", "price"} <= header.keys() or "comment" in header:
            return header
    return None


def _company(raw, companies):
    value = str(raw or "").strip().lower()
    for suffix, replacement in {".pl": "", ".fr": ".pa", ".nl": ".as", ".uk": ".l"}.items():
        if value.endswith(suffix):
            value = value[: -len(suffix)] + replacement
            break
    ticker = normalize_ticker(value)
    company = companies.find(ticker) if ticker else None
    if company is None:
        raise RowError("unknown_ticker")
    return company


def _trade(get, companies, cash_history):
    side_text = normalized(get("side"))
    comment = str(get("comment") or "")
    match = COMMENT_TRADE.search(comment)
    if side_text in CASH:
        return None, []
    if normalized(get("assetType")) in {
        "cfd",
        "forex",
        "future",
        "futures",
        "option",
        "options",
        "crypto",
        "kryptowaluty",
    }:
        raise RowError("unsupported_operation")
    if side_text in BUY:
        side = "buy"
    elif side_text in SELL:
        side = "sell"
    else:
        raise RowError("unsupported_operation")
    status = normalized(get("status"))
    if status and status not in FILLED:
        raise RowError("unexecuted_order")
    if cash_history and not match and not (get("quantity") and get("price")):
        raise RowError("missing_execution")
    # A CLOSE BUY comment may accompany Stock sell: the operation type wins.
    if match and (
        (side == "buy" and match[1].upper() != "OPEN")
        or (side == "sell" and match[1].upper() != "CLOSE")
    ):
        raise RowError("unsupported_operation")
    if match and side == "buy" and match[2].upper() != "BUY":
        raise RowError("unsupported_operation")
    company = _company(get("ticker"), companies)
    quote_ccy = quote_currency(company)
    explicit_ccy = currency(get("priceCurrency") or (get("currency") if not cash_history else ""))
    if explicit_ccy and explicit_ccy != quote_ccy:
        if {explicit_ccy, quote_ccy} != {"GBP", "GBp"}:
            raise RowError("currency_mismatch")
    if quote_ccy == "GBp" and not explicit_ccy:
        raise RowError("price_currency_missing")
    reference = str(get("reference") or "").strip()
    if isinstance(get("reference"), float) and get("reference").is_integer():
        reference = str(int(get("reference")))
    if re.fullmatch(r"\d+\.0", reference):
        reference = reference[:-2]
    if not reference or not re.fullmatch(r"[\w.:/-]{1,100}", reference):
        raise RowError("missing_reference")
    executed = timestamp(get("time"))
    if (get("quantity") in (None, "") or get("price") in (None, "")) and not match:
        raise RowError("missing_execution")
    quantity = decimal_value(get("quantity") if get("quantity") not in (None, "") else match[3])
    price = decimal_value(get("price") if get("price") not in (None, "") else match[4])
    if match and (quantity != decimal_value(match[3]) or price != decimal_value(match[4])):
        raise RowError("execution_mismatch")
    if explicit_ccy == "GBP" and quote_ccy == "GBp":
        price *= 100
    elif explicit_ccy == "GBp" and quote_ccy == "GBP":
        price /= 100
    warnings = []
    if get("fees") in (None, ""):
        fees = Decimal(0)
        warnings.append("fees_missing")
    else:
        fees = abs(decimal_value(get("fees")))
        fee_ccy = currency(get("feeCurrency") or get("currency"))
        if fees and not fee_ccy:
            raise RowError("fee_currency_missing")
        if fees and fee_ccy != quote_ccy:
            if fee_ccy == "GBP" and quote_ccy == "GBp":
                fees *= 100
            elif fee_ccy == "GBp" and quote_ccy == "GBP":
                fees /= 100
            else:
                raise RowError("fee_currency_mismatch")
    source_id = f"xtb:{reference}:{side}"
    try:
        trade = AddTransaction(
            id=uuid5(NAMESPACE_URL, source_id),
            version=1,
            ticker=company.ticker,
            date=executed.date(),
            side=side,
            quantity=quantity,
            price=price,
            fees=fees,
            currency=quote_ccy,
        )
    except ValidationError as exc:
        raise RowError("invalid_transaction") from exc
    return {
        **trade.model_dump(mode="json", exclude={"version"}),
        "source": "xtb",
        "sourceId": source_id,
        "executedAt": executed.isoformat(timespec="microseconds"),
    }, warnings


def parse_xtb(data: bytes, filename: str, companies) -> ParsedImport:
    tables = read_tables(data, filename)
    rows, ignored, recognized, warnings = [], 0, False, set()
    cash_tables = [
        table
        for table in tables
        if normalized(table[0])
        in {"cashoperations", "cashoperation", "operacjegotowkowe", "cashhistory"}
    ]
    # Never combine a cash ledger with open/closed-position snapshots.
    for sheet, values in cash_tables or tables:
        header, header_index = None, None
        for index, row in enumerate(values[:40]):
            header = _header(row)
            if header:
                header_index = index
                break
        if header is None:
            continue
        recognized = True
        cash_history = "amount" in header and "comment" in header
        for index in range(header_index + 1, len(values)):
            row = values[index]
            if not any(value not in (None, "") for value in row):
                continue

            def get(key, cells=row, columns=header):
                position = columns.get(key)
                return cells[position] if position is not None and position < len(cells) else None

            if normalized(get("reference")) in {"total", "suma", "razem"} or (
                not get("reference")
                and not get("side")
                and any(normalized(value) in {"total", "suma", "razem"} for value in row)
            ):
                ignored += 1
                continue
            result = {"sheet": sheet, "row": index + 1, "symbol": str(get("ticker") or "")[:80]}
            try:
                if any(isinstance(value, str) and value.startswith("=") for value in row):
                    raise RowError("formula_cell")
                trade, row_warnings = _trade(get, companies, cash_history)
                if trade is None:
                    ignored += 1
                    continue
                warnings.update(row_warnings)
                rows.append({**result, "transaction": trade, "status": "ready"})
            except RowError as exc:
                rows.append({**result, "status": "error", "code": str(exc)})
    if not recognized:
        raise PortfolioError("import_unrecognized_format", 422)
    if not rows:
        raise PortfolioError("import_no_transactions", 422)
    if len(rows) > 1000:
        raise PortfolioError("transaction_limit")
    return ParsedImport(rows, ignored, sorted(warnings))


def _trade_key(trade, *, with_time=True):
    fields = ("ticker", "date", "side", "currency") + (("executedAt",) if with_time else ())
    return tuple(trade.get(key) for key in fields) + tuple(
        Decimal(trade[key]) for key in ("quantity", "price", "fees")
    )


def _same_trade(first, second):
    return _trade_key(first) == _trade_key(second)


def prepare_import(parsed: ParsedImport, existing: list[dict], cost_method: str) -> dict:
    by_id = {trade["id"]: trade for trade in existing}
    manual_keys = {
        _trade_key(trade, with_time=False) for trade in existing if trade.get("source") != "xtb"
    }
    rows, additions = [], []
    for raw in parsed.rows:
        row = dict(raw)
        trade = row.get("transaction")
        if trade:
            prior = by_id.get(trade["id"])
            if prior:
                row.update(status="duplicate" if _same_trade(prior, trade) else "error")
                if row["status"] == "error":
                    row["code"] = "reference_conflict"
            elif _trade_key(trade, with_time=False) in manual_keys:
                row.update(status="error", code="manual_overlap")
            else:
                additions.append(trade)
                by_id[trade["id"]] = trade
        rows.append(row)
    ledger = sorted([*existing, *additions], key=trade_order)
    ledger_error = None
    try:
        holdings(ledger, cost_method)
    except PortfolioError as exc:
        ledger_error = exc.code
    if len(ledger) > 1000:
        ledger_error = "transaction_limit"
    if any(row.get("code") == "reference_conflict" for row in rows):
        ledger_error = "import_reference_conflict"
    return {
        "rows": rows,
        "additions": additions,
        "ledger": ledger,
        "ready": len(additions),
        "duplicates": sum(r["status"] == "duplicate" for r in rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "ignored": parsed.ignored,
        "warnings": parsed.warnings,
        "ledgerError": ledger_error,
    }
