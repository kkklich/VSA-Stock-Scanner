"""Bounded XTB cash-history / executed-trade imports. Never infer price from cash FX."""

import csv
import io
import re
import struct
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, DecimalException, Inexact, InvalidOperation, localcontext
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zipfile import BadZipFile, ZipFile

import openpyxl
import xlrd
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError
from xlrd.compdoc import CompDocError

from app.markets import normalize_ticker, quote_currency
from app.models.portfolio import AddTransaction
from app.services.bounded_xls import open_bounded_xls
from app.services.portfolio import (
    WARSAW,
    PortfolioError,
    holdings,
    require_after_checkpoint,
    trade_order,
)
from app.services.portfolio_instruments import find_portfolio_instrument

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
MAX_COLUMNS = 80
MAX_CELL = 4000
SUMMARY_LABELS = {"total", "suma", "razem", "profitloss"}
ACCOUNT_ID_LABELS = {"accountnumber", "accountid", "numerrachunku", "idrachunku"}
ACCOUNT_CURRENCY_LABELS = {"accountcurrency", "walutarachunku"}


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
        "timeutc",
        "date",
        "datetime",
        "datetimeutc",
        "czas",
        "data",
        "dataczas",
        "executiontime",
        "executiontimeutc",
        "transactiontime",
        "transactiontimeutc",
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
    "assetType": {
        "category",
        "kategoria",
        "instrumenttype",
        "assettype",
        "rodzajinstrumentu",
        "typinstrumentu",
    },
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
    "ikedeposit",
    "ikewithdrawal",
    "wplataike",
    "wyplataike",
    "ikzedeposit",
    "ikzewithdrawal",
    "wplataikze",
    "wyplataikze",
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
COMMENT_START = re.compile(r"\b(OPEN|CLOSE)\s+(BUY|SELL)\s+", re.IGNORECASE)


class RowError(Exception):
    pass


@dataclass
class ParsedImport:
    rows: list[dict]
    ignored: int
    warnings: list[str]
    broker_account_id: str | None = None
    broker_account_currency: str | None = None


@dataclass(frozen=True)
class CommentTrade:
    action: str
    side: str
    quantity: str
    price: str


def _comment_trade(comment: str) -> CommentTrade | None:
    """Scan each numeric span once; overlapping whitespace regexes can backtrack."""
    size = len(comment)

    def whitespace(position):
        while position < size and comment[position].isspace():
            position += 1
        return position

    def number(position, *, grouped=True):
        start = position
        separators = "., \xa0\u202f" if grouped else ".,"
        while position < size and (
            comment[position].isdecimal() or comment[position] in separators
        ):
            position += 1
        return comment[start:position], position

    for start in COMMENT_START.finditer(comment):
        p = whitespace(start.end())
        candidates = [p]
        word_end = p
        while word_end < size and not comment[word_end].isspace():
            word_end += 1
        after_word = whitespace(word_end)
        if after_word < size and after_word != p:
            candidates.append(after_word)

        for candidate_pos in candidates:
            quantity, position = number(candidate_pos)
            if not quantity:
                continue
            position = whitespace(position)
            if position < size and comment[position] == "/":
                denominator, position = number(whitespace(position + 1), grouped=False)
                if not denominator:
                    continue
                position = whitespace(position)
            if position >= size or comment[position] != "@":
                continue
            price, position = number(whitespace(position + 1))
            if not price:
                continue
            if (
                position < size
                and (comment[position].isalnum() or comment[position] in "_.,")
                and not price[-1].isspace()
            ):
                continue
            return CommentTrade(start[1].upper(), start[2].upper(), quantity, price)
    return None


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


def timestamp(value, *, assume_utc: bool = False) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    else:
        text = str(value or "").strip()
        try:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for pattern in (
                "%d.%m.%Y %H:%M:%S",
                "%d.%m.%Y %H:%M",
                "%d.%m.%Y",
                "%Y.%m.%d %H:%M:%S",
                "%Y.%m.%d",
            ):
                try:
                    result = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    continue
            else:
                raise RowError("invalid_date") from None
    return result.replace(tzinfo=UTC) if assume_utc and result.tzinfo is None else result


def is_summary_row(cells, *, reference=None, side=None, time=None) -> bool:
    """A summary has no execution timestamp or trade direction."""
    if time not in (None, "") or (side and normalized(side) not in SUMMARY_LABELS):
        return False
    if reference and normalized(reference) not in SUMMARY_LABELS:
        return False
    return any(normalized(value) in SUMMARY_LABELS for value in cells)


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


SECTION_NAMES = {
    "cashoperations": "Cash Operations",
    "cashoperation": "Cash Operations",
    "operacjegotowkowe": "Cash Operations",
    "operacjigotowkowe": "Cash Operations",
    "cashhistory": "Cash Operations",
    "closedpositions": "Closed Positions",
    "pozycjezamkniete": "Closed Positions",
    "openpositions": "Open Positions",
    "pozycjeotwarte": "Open Positions",
}


def _split_csv_sections(rows: list[list]) -> list[tuple[str, list[list]]]:
    section_indices: list[tuple[int, str]] = []
    for idx, row in enumerate(rows):
        cells = [str(c or "").strip() for c in row if str(c or "").strip()]
        if len(cells) == 1 and normalized(cells[0]) in SECTION_NAMES:
            title = SECTION_NAMES[normalized(cells[0])]
            start_idx = idx
            if idx > 0:
                prev_cells = [str(c or "").strip() for c in rows[idx - 1] if str(c or "").strip()]
                if prev_cells and normalized(prev_cells[0]) in ACCOUNT_ID_LABELS:
                    start_idx = idx - 1
            section_indices.append((start_idx, title))
    if not section_indices:
        return [("CSV", rows)]
    tables: list[tuple[str, list[list]]] = []
    if section_indices[0][0] > 0:
        prefix = rows[: section_indices[0][0]]
        metadata = {"xtbaccounthistory", "accounthistory", "historiarachunku"}
        first_cells = [next((c for c in row if str(c or "").strip()), None) for row in prefix]
        if any(cell is not None and normalized(cell) not in metadata for cell in first_cells):
            tables.append(("CSV", prefix))
    for i, (start_idx, title) in enumerate(section_indices):
        end_idx = section_indices[i + 1][0] if i + 1 < len(section_indices) else len(rows)
        tables.append((title, rows[start_idx:end_idx]))
    return tables


def _check_xlsx_coordinates(source):
    """Check actual coordinates before openpyxl allocates sparse rows or columns."""
    row, column, row_count = 0, 0, 0
    for event, element in iterparse(source, events=("start", "end")):
        tag = element.tag.rsplit("}", 1)[-1]
        if event == "start" and tag == "row":
            row_count += 1
            row = int(element.get("r", row + 1))
            column = 0
            if row < 1 or row > MAX_ROWS or row_count > MAX_ROWS:
                raise PortfolioError("import_too_many_rows", 413)
        elif event == "start" and tag == "c":
            coordinate = element.get("r")
            if coordinate:
                if len(coordinate) > 12:
                    raise PortfolioError("import_too_many_rows", 413)
                cell_row, column = coordinate_to_tuple(coordinate)
            else:
                cell_row, column = row, column + 1
            if not (1 <= cell_row <= MAX_ROWS and 1 <= column <= MAX_COLUMNS):
                raise PortfolioError("import_too_many_rows", 413)
        if event == "end":
            element.clear()


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
            rows = _checked_rows(csv.reader(io.StringIO(text), delimiter=delimiter))
            return _split_csv_sections(rows)
        if extension == ".xls":
            book = open_bounded_xls(
                data,
                max_rows=MAX_ROWS,
                max_columns=MAX_COLUMNS,
                max_cell=MAX_CELL,
                max_sheets=12,
                max_cells=MAX_ROWS * MAX_COLUMNS,
            )
            try:
                if book.nsheets > 12:
                    raise PortfolioError("import_invalid_file", 422)
                tables = []
                for sheet_index in range(book.nsheets):
                    sheet = book.sheet_by_index(sheet_index)
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
                    book.unload_sheet(sheet_index)
                    del sheet
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
                # XTB exports can declare A1:A1 despite containing hundreds of rows.
                # Validate the same XML stream the read-only sheet uses before
                # removing that unreliable metadata and reading all actual cells.
                with book._archive.open(sheet._worksheet_path) as source:
                    _check_xlsx_coordinates(source)
                sheet.reset_dimensions()
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
        LookupError,
        BadZipFile,
        csv.Error,
        xlrd.XLRDError,
        UnicodeError,
        SyntaxError,
        TypeError,
        AssertionError,
        OverflowError,
        struct.error,
        CompDocError,
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


def normalize_broker_account_id(value) -> str | None:
    """Keep textual leading zeros and accept exact integer spreadsheet cells."""
    if isinstance(value, float) and value.is_integer() and 0 <= value < 2**53:
        value = int(value)
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text if re.fullmatch(r"[0-9]{1,32}", text) else None


def report_broker_account_id(rows: list[list]) -> str | None:
    account_ids = {
        account_id
        for row in rows
        if len(row) >= 2
        and normalized(row[0]) in ACCOUNT_ID_LABELS
        and (account_id := normalize_broker_account_id(row[1])) is not None
    }
    if len(account_ids) > 1:
        raise PortfolioError("import_multiple_broker_accounts", 422)
    return next(iter(account_ids), None)


def report_broker_account_currency(metadata, values=()) -> str | None:
    codes = {
        currency(row[1])
        for row in metadata
        if len(row) >= 2 and normalized(row[0]) in ACCOUNT_CURRENCY_LABELS
    }
    codes.update(currency(value) for value in values)
    currencies = {code for code in codes if re.fullmatch(r"[A-Z]{3}", code)}
    if len(currencies) > 1:
        raise PortfolioError("import_multiple_account_currencies", 422)
    return next(iter(currencies), None)


def _company(raw, companies):
    value = str(raw or "").strip().lower()
    for suffix, replacement in {".pl": "", ".fr": ".pa", ".nl": ".as", ".uk": ".l"}.items():
        if value.endswith(suffix):
            value = value[: -len(suffix)] + replacement
            break
    ticker = normalize_ticker(value)
    company = find_portfolio_instrument(ticker, companies) if ticker else None
    if company is None:
        raise RowError("unknown_ticker")
    return company


def _convert_quote_units(value: Decimal, source: str, target: str, error: str) -> Decimal:
    if source == target:
        return value
    if {source, target} != {"GBP", "GBp"}:
        raise RowError(error)
    try:
        with localcontext() as context:
            context.prec = max(context.prec, len(value.as_tuple().digits) + 2)
            context.traps[Inexact] = True
            return value * 100 if source == "GBP" else value / 100
    except DecimalException as exc:
        raise RowError("invalid_number") from exc


def _trade(get, companies, cash_history, *, utc_time=False, account_currency=False):
    side_text = normalized(get("side"))
    comment = str(get("comment") or "")
    match = _comment_trade(comment)
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
        (side == "buy" and match.action != "OPEN") or (side == "sell" and match.action != "CLOSE")
    ):
        raise RowError("unsupported_operation")
    if match and side == "buy" and match.side != "BUY":
        raise RowError("unsupported_operation")
    company = _company(get("ticker"), companies)
    quote_ccy = quote_currency(company)
    explicit_ccy = currency(
        get("priceCurrency") or (get("currency") if not (cash_history or account_currency) else "")
    )
    if quote_ccy == "GBp" and not explicit_ccy:
        raise RowError("price_currency_missing")
    reference = str(get("reference") or "").strip()
    if isinstance(get("reference"), float) and get("reference").is_integer():
        reference = str(int(get("reference")))
    if re.fullmatch(r"\d+\.0", reference):
        reference = reference[:-2]
    if not reference or not re.fullmatch(r"[\w.:/-]{1,100}", reference):
        raise RowError("missing_reference")
    executed = timestamp(get("time"), assume_utc=utc_time)
    try:
        local_date = executed.astimezone(WARSAW).date() if executed.tzinfo else executed.date()
    except OverflowError as exc:
        raise RowError("invalid_date") from exc
    if (get("quantity") in (None, "") or get("price") in (None, "")) and not match:
        raise RowError("missing_execution")
    quantity = decimal_value(
        get("quantity") if get("quantity") not in (None, "") else match.quantity
    )
    price = decimal_value(get("price") if get("price") not in (None, "") else match.price)
    if match and (quantity != decimal_value(match.quantity) or price != decimal_value(match.price)):
        raise RowError("execution_mismatch")
    if explicit_ccy:
        price = _convert_quote_units(price, explicit_ccy, quote_ccy, "currency_mismatch")
    warnings = []
    if get("fees") in (None, ""):
        fees = Decimal(0)
        warnings.append("fees_missing")
    else:
        fees = decimal_value(get("fees")).copy_abs()
        fee_ccy = currency(get("feeCurrency") or get("currency"))
        if fees and not fee_ccy:
            raise RowError("fee_currency_missing")
        if fees:
            fees = _convert_quote_units(fees, fee_ccy, quote_ccy, "fee_currency_mismatch")
    source_id = f"xtb:{reference}:{side}"
    try:
        trade = AddTransaction(
            id=uuid5(NAMESPACE_URL, source_id),
            version=1,
            ticker=company.ticker,
            date=local_date,
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
    return parse_xtb_tables(read_tables(data, filename), companies)


def parse_xtb_tables(
    tables: list[tuple[str, list[list]]], companies, *, allow_empty: bool = False
) -> ParsedImport:
    rows, ignored, recognized, warnings = [], 0, False, set()
    broker_account_id = None
    broker_account_currency = None
    cash_names = {
        "cashoperations",
        "cashoperation",
        "operacjegotowkowe",
        "operacjigotowkowe",
        "cashhistory",
    }
    cash_tables = [table for table in tables if normalized(table[0]) in cash_names]
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
        account_id = report_broker_account_id(values[:header_index])
        if account_id is not None:
            if broker_account_id not in (None, account_id):
                raise PortfolioError("import_multiple_broker_accounts", 422)
            broker_account_id = account_id
        cash_history = "amount" in header and "comment" in header
        currency_column = header.get("currency")
        explicit_account_currency = (
            currency_column is not None
            and normalized(values[header_index][currency_column]) in ACCOUNT_CURRENCY_LABELS
        )
        currencies = ()
        if currency_column is not None and (cash_history or explicit_account_currency):
            side_column = header["side"]
            currencies = (
                row[currency_column]
                for row in values[header_index + 1 :]
                if max(currency_column, side_column) < len(row)
                and normalized(row[side_column]) in BUY | SELL
            )
        account_currency = report_broker_account_currency(values[:header_index], currencies)
        if account_currency:
            if broker_account_currency not in (None, account_currency):
                raise PortfolioError("import_multiple_account_currencies", 422)
            broker_account_currency = account_currency
        utc_time = normalized(values[header_index][header["time"]]).endswith("utc") or (
            cash_history
            and any(
                row and normalized(row[0]) in {"datefromutc", "datetoutc", "dataodutc", "datadoutc"}
                for row in values[:header_index]
            )
        )
        for index in range(header_index + 1, len(values)):
            row = values[index]
            if not any(value not in (None, "") for value in row):
                continue

            def get(key, cells=row, columns=header):
                position = columns.get(key)
                return cells[position] if position is not None and position < len(cells) else None

            if is_summary_row(row, reference=get("reference"), side=get("side"), time=get("time")):
                ignored += 1
                continue
            result = {"sheet": sheet, "row": index + 1, "symbol": str(get("ticker") or "")[:80]}
            try:
                if any(isinstance(value, str) and value.startswith("=") for value in row):
                    raise RowError("formula_cell")
                trade, row_warnings = _trade(
                    get,
                    companies,
                    cash_history,
                    utc_time=utc_time,
                    account_currency=explicit_account_currency,
                )
                if trade is None:
                    ignored += 1
                    continue
                warnings.update(row_warnings)
                rows.append({**result, "transaction": trade, "status": "ready"})
            except RowError as exc:
                rows.append({**result, "status": "error", "code": str(exc)})
    if not recognized:
        raise PortfolioError("import_unrecognized_format", 422)
    if not rows and not allow_empty:
        raise PortfolioError("import_no_transactions", 422)
    if len(rows) > 1000:
        raise PortfolioError("transaction_limit")
    return ParsedImport(rows, ignored, sorted(warnings), broker_account_id, broker_account_currency)


def _trade_key(trade, *, with_time=True, with_fees=True):
    fields = ("ticker", "date", "side", "currency") + (("executedAt",) if with_time else ())
    amounts = ("quantity", "price") + (("fees",) if with_fees else ())
    return tuple(trade.get(key) for key in fields) + tuple(Decimal(trade[key]) for key in amounts)


def _xtb_import_key(trade):
    is_daily_statement = (trade.get("sourceId") or "").startswith("xtb:daily/")
    return is_daily_statement, _trade_key(trade, with_time=False, with_fees=False)


def _same_trade(first, second):
    if _trade_key(first) == _trade_key(second):
        return True
    if not (first.get("executedAt") and second.get("executedAt")):
        return False
    prior, imported = timestamp(first["executedAt"]), timestamp(second["executedAt"])
    if prior.tzinfo and imported.tzinfo:
        return prior == imported and _trade_key(first, with_time=False) == _trade_key(
            second, with_time=False
        )
    if not prior.tzinfo and imported.tzinfo:
        # Older imports stored the report wall time and its calendar date without
        # the timezone. The unchanged source ID must still be safe to retry.
        legacy = {
            **second,
            "date": imported.date().isoformat(),
            "executedAt": imported.replace(tzinfo=None).isoformat(timespec="microseconds"),
        }
        return _trade_key(first) == _trade_key(legacy)
    return False


def prepare_import(
    parsed: ParsedImport, existing: list[dict], cost_method: str, *, checkpoint=None
) -> dict:
    by_id = {trade["id"]: trade for trade in existing}
    manual_keys = {
        _trade_key(trade, with_time=False) for trade in existing if trade.get("source") != "xtb"
    }
    xtb_keys = {_xtb_import_key(trade) for trade in existing if trade.get("source") == "xtb"}
    snapshot_without_cutoff = not checkpoint and any(
        (trade.get("sourceId") or "").startswith("xtb:position:") for trade in existing
    )
    rows, additions = [], []
    for raw in parsed.rows:
        row = dict(raw)
        trade = row.get("transaction")
        if trade:
            prior = by_id.get(trade["id"])
            is_xtb = trade.get("source") == "xtb"
            is_daily_statement, match_key = _xtb_import_key(trade)
            if prior:
                row.update(status="duplicate" if _same_trade(prior, trade) else "error")
                if row["status"] == "error":
                    row["code"] = "reference_conflict"
            elif _trade_key(trade, with_time=False) in manual_keys:
                row.update(status="error", code="manual_overlap")
            elif is_xtb and (not is_daily_statement, match_key) in xtb_keys:
                # Daily statements identify orders, while the cash export uses operation IDs.
                # Matching amounts and dates warrant review without assuming the fills are equal.
                row.update(status="error", code="xtb_source_overlap")
            elif snapshot_without_cutoff and not (trade.get("sourceId") or "").startswith(
                "xtb:position:"
            ):
                row.update(status="error", code="import_snapshot_history_conflict")
            else:
                require_after_checkpoint(trade, checkpoint)
                additions.append(trade)
                by_id[trade["id"]] = trade
                if is_xtb:
                    xtb_keys.add((is_daily_statement, match_key))
        rows.append(row)
    ledger = sorted([*existing, *additions], key=trade_order)
    ledger_error = None
    try:
        holdings([*ledger, checkpoint] if checkpoint else ledger, cost_method)
    except PortfolioError as exc:
        ledger_error = exc.code
    if len(ledger) > 1000:
        ledger_error = "transaction_limit"
    if any(row.get("code") == "reference_conflict" for row in rows):
        ledger_error = "import_reference_conflict"
    if any(row.get("code") == "import_snapshot_history_conflict" for row in rows):
        ledger_error = "import_snapshot_history_conflict"
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
