"""Read executed stock purchases from XTB's Polish DailyStatement PDF."""

import re
from datetime import datetime
from io import BytesIO
from itertools import chain

from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError

from app.services.portfolio import PortfolioError
from app.services.xtb_import import (
    MAX_FILE_BYTES,
    ParsedImport,
    RowError,
    decimal_value,
    normalize_broker_account_id,
    normalized,
    parse_xtb_tables,
)

_TITLE = re.compile(r"Potwierdzenie zleceń wykonanych w dniu (\d{2}\.\d{2}\.\d{4})")
_ACCOUNT_HEADER = re.compile(r"\b(?:Konto|Numer rachunku)\s{2,}(Waluta rachunku)\s{2,}(Saldo)")
_SECTION = re.compile(r"Wykonane zlecenia (kupna|sprzedaży) (.+?) \((\d{1,4})\)")
_ORDER = re.compile(r"\s*\d{1,4}\s+(\d{1,24})(?=\s)")
_TIME = re.compile(r"\d{2}:\d{2}:\d{2}")
_REPORT_COLUMNS = {
    "symbol": ("Symbol", "Nazwa"),
    "quantity": ("Wolumen", "Data i czas"),
    "time": ("Data i czas", "Zlecenie"),
    "price": ("Cena", "Cena całkowita"),
    "asset": ("Klasa aktywów", "Waluta"),
    "currency": ("Waluta", "Kurs"),
    "fx_cost": ("Koszty", "Prowizja"),
    "commission": ("Prowizja", "Łączne koszty"),
}
_TRADE_COLUMNS = [
    "ID",
    "Type",
    "Time",
    "Symbol",
    "Quantity",
    "Price",
    "Currency",
    "Commission",
    "Commission Currency",
]
_STOCKS = {"akcja", "akcje", "prawaulamkowedotakcji", "prawoulamkowedotakcji"}
_MAX_PAGES = 40
_MAX_PAGE_TEXT = 100_000
_MAX_ORDERS = 1_000


def _invalid():
    return PortfolioError("import_invalid_daily_statement", 422)


def _page_lines(data: bytes, password: str):
    if len(data) > MAX_FILE_BYTES:
        raise PortfolioError("import_file_too_large", 413)
    if not data.startswith(b"%PDF-"):
        raise _invalid()
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted and not reader.decrypt(password):
            raise PortfolioError("import_statement_password_invalid", 422)
        if not 1 <= len(reader.pages) <= _MAX_PAGES:
            raise _invalid()
        for page in reader.pages:
            text = page.extract_text(extraction_mode="layout")
            if len(text) > _MAX_PAGE_TEXT:
                raise _invalid()
            yield [line for line in text.splitlines() if line.strip()]
    except DependencyError as exc:
        raise PortfolioError("import_statement_crypto_unavailable", 503) from exc
    except (PyPdfError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        raise _invalid() from exc


def _account_summary(lines) -> tuple[str, str] | None:
    summary = None
    for index, line in enumerate(lines[:-1]):
        if match := _ACCOUNT_HEADER.search(line):
            values = lines[index + 1]
            account_id = normalize_broker_account_id(values[match.start() : match.start(1)])
            currency = values[match.start(1) : match.start(2)].strip()
            if account_id is None:
                raise PortfolioError("import_statement_broker_account_missing", 422)
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise _invalid()
            if summary is not None and summary != (account_id, currency):
                raise PortfolioError("import_multiple_broker_accounts", 422)
            summary = (account_id, currency)
    return summary


def _columns(line):
    labels = {
        part.group().strip(): part.start()
        for part in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", line)
    }
    if "Symbol, którego" in labels:
        labels["Symbol"] = labels["Symbol, którego"]
    try:
        columns = {
            name: slice(labels[start], labels[end])
            for name, (start, end) in _REPORT_COLUMNS.items()
        }
    except KeyError as exc:
        raise _invalid() from exc
    if any(column.start >= column.stop for column in columns.values()):
        raise _invalid()
    return columns


def _purchase(order, line, next_line, columns, report_date, account_currency):
    values = {name: line[column].strip() for name, column in columns.items()}
    continuation = next_line[columns["time"]].strip()
    if _TIME.fullmatch(continuation):
        values["time"] += f" {continuation}"
    asset_continuation = next_line[columns["asset"]].strip()
    if normalized(asset_continuation).startswith("dot"):
        values["asset"] += f" {asset_continuation}"
    if normalized(values["asset"]) not in _STOCKS:
        raise PortfolioError("import_statement_unsupported_asset", 422)
    try:
        when = datetime.strptime(values["time"], "%d.%m.%Y %H:%M:%S")
        has_fx_cost = bool(decimal_value(values["fx_cost"])) if values["fx_cost"] else False
    except (ValueError, RowError) as exc:
        raise _invalid() from exc
    symbol = values["symbol"].upper()
    if when.date() != report_date or not re.fullmatch(r"[A-Z0-9.\-]{1,30}", symbol):
        raise _invalid()
    reference = f"daily/{order}/{when:%Y%m%dT%H%M%S}/{symbol}"
    return [
        reference,
        "Buy",
        when,
        symbol,
        values["quantity"],
        values["price"],
        values["currency"],
        values["commission"],
        account_currency,
    ], has_fx_cost


def parse_xtb_daily_statement(data: bytes, password: str, companies) -> ParsedImport:
    """Preserve the report's execution clock and use a separate order-ID namespace."""
    pages = _page_lines(data, password)
    first_page = next(pages, [])
    title = next((match for line in first_page if (match := _TITLE.fullmatch(line.strip()))), None)
    if title is None:
        raise _invalid()
    try:
        report_date = datetime.strptime(title[1], "%d.%m.%Y").date()
    except ValueError as exc:
        raise _invalid() from exc
    account = _account_summary(first_page)
    if account is None:
        raise _invalid()
    broker_account_id, account_currency = account
    rows = [_TRADE_COLUMNS]
    refs = set()
    section = None
    remaining = 0
    ignored_sales = 0
    total_orders = 0
    fx_cost = False
    for page_index, lines in enumerate(chain((first_page,), pages)):
        if page_index and (summary := _account_summary(lines)) is not None and summary != account:
            raise PortfolioError("import_multiple_broker_accounts", 422)
        columns = None
        for index, line in enumerate(lines):
            if line.lstrip().startswith("Wykonane zlecenia"):
                match = _SECTION.fullmatch(line.strip())
                if match is None:
                    raise _invalid()
                name = match.groups()
                if remaining and name != section:
                    raise _invalid()
                if not remaining:
                    section, remaining = name, int(match[3])
                    total_orders += remaining
                    if total_orders > _MAX_ORDERS:
                        raise _invalid()
                columns = None
            elif section and re.match(r"\s*Nr\s+Numer zlecenia\s+", line):
                columns = _columns(line)
            elif section and (order := _ORDER.match(line)):
                if not remaining or columns is None:
                    raise _invalid()
                remaining -= 1
                if section[0] == "sprzedaży":
                    ignored_sales += 1
                    continue
                next_line = lines[index + 1] if index + 1 < len(lines) else ""
                row, has_fx_cost = _purchase(
                    order[1], line, next_line, columns, report_date, account_currency
                )
                if row[0] in refs:
                    raise PortfolioError("import_statement_ambiguous_fill", 422)
                refs.add(row[0])
                rows.append(row)
                fx_cost |= has_fx_cost
    if section is None or remaining:
        raise _invalid()
    parsed = parse_xtb_tables([("DailyStatement", rows)], companies, allow_empty=True)
    parsed.broker_account_id = broker_account_id
    parsed.ignored += ignored_sales
    if fx_cost:
        parsed.warnings.append("fx_cost_not_imported")
    return parsed
