"""XTB native cash sheets, executed CSV trades, exact values and atomic account imports."""

import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import openpyxl
import pytest

from app.services.portfolio import PortfolioError
from app.services.xtb_import import MAX_FILE_BYTES, parse_xtb, prepare_import
from tests.test_portfolios import client as portfolio_client
from tests.test_portfolios import create, trade


@pytest.fixture
def client():
    yield from portfolio_client.__wrapped__()


HEADERS = ["ID", "Type", "Time", "Comment", "Symbol", "Amount", "Currency"]


def workbook(rows, headers=HEADERS, title="Cash Operations", other=None):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = title
    for row in [["XTB Account History"], ["Account", "example"], [], [], headers, *rows]:
        sheet.append(row)
    if other:
        duplicate = book.create_sheet("Closed Positions")
        for row in [headers, *other]:
            duplicate.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def cash(
    reference="1001",
    kind="Stock purchase",
    time="2026-01-02 12:00:00",
    comment="OPEN BUY 10 @ 100.25",
    symbol="KGH.PL",
    amount=-1002.5,
    currency="PLN",
):
    return [reference, kind, time, comment, symbol, amount, currency]


class Companies:
    def find(self, ticker):
        if ticker in {"kgh", "pkn", "aapl.us", "hsba.l"}:
            return SimpleNamespace(ticker=ticker, currency=None)
        return None


def preview(client, portfolio, data, filename="history.xlsx"):
    return client.post(
        f"/api/portfolios/{portfolio['id']}/imports/xtb/preview",
        params={"filename": filename},
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def commit(client, portfolio, data, filename="history.xlsx", partial=False):
    return client.post(
        f"/api/portfolios/{portfolio['id']}/imports/xtb",
        params={"filename": filename, "version": portfolio["version"], "allow_partial": partial},
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def test_native_cash_import_uses_operation_type_and_does_not_duplicate_other_sheets():
    rows = [
        cash(),
        cash("1002", "Stock sell", "2026-01-02 13:00:00", "CLOSE BUY 4 @ 120", amount=480),
        cash("1003", "Dividend", comment="Dividend", amount=12),
        ["Total", "", "", "", "", 500],
    ]
    parsed = parse_xtb(workbook(rows, other=rows[:2]), "report.xlsx", Companies())
    assert len(parsed.rows) == 2
    assert parsed.ignored == 2
    assert parsed.warnings == ["fees_missing"]
    plan = prepare_import(parsed, [], "fifo")
    assert plan["ready"] == 2
    assert plan["ledgerError"] is None
    assert plan["ledger"][0]["ticker"] == "kgh"
    assert plan["ledger"][0]["price"] == "100.25"
    assert plan["ledger"][1]["side"] == "sell"


def test_partial_fill_numerator_is_not_a_fraction_and_cash_fx_is_not_execution_price():
    parsed = parse_xtb(
        workbook(
            [cash(comment="OPEN BUY 1/100 @ 14.3130", symbol="AAPL.US", currency="PLN", amount=-55)]
        ),
        "PLN.xlsx",
        Companies(),
    )
    trade = parsed.rows[0]["transaction"]
    assert trade["quantity"] == "1"
    assert trade["price"] == "14.3130"
    assert trade["currency"] == "USD"


def test_localized_cash_comments_and_total_label_in_another_column():
    parsed = parse_xtb(
        workbook(
            [
                cash(comment="OPEN BUY 0,125 @ 1 234,56"),
                [None, None, None, None, "Total", 10, "PLN"],
            ]
        ),
        "report.xlsx",
        Companies(),
    )
    assert parsed.rows[0]["transaction"]["quantity"] == "0.125"
    assert parsed.rows[0]["transaction"]["price"] == "1234.56"
    assert parsed.ignored == 1


def test_inconsistent_execution_fields_are_not_silently_preferred():
    data = workbook([cash() + [2, 100.25]], headers=[*HEADERS, "Quantity", "Price"])
    assert parse_xtb(data, "report.xlsx", Companies()).rows[0]["code"] == "execution_mismatch"


def test_polish_csv_and_numeric_formats_preserve_reference_and_execution_time():
    data = (
        "Numer transakcji;Typ;Data;Instrument;Ilość;Cena;Waluta;Prowizja\n"
        "123;Kupno;02.01.2026 13:45:01;KGH.PL;0,125;1 234,56;PLN;1,50\n"
    ).encode("cp1250")
    parsed = parse_xtb(data, "historia.CSV", Companies())
    trade = parsed.rows[0]["transaction"]
    assert trade["quantity"] == "0.125"
    assert trade["price"] == "1234.56"
    assert trade["fees"] == "1.50"
    assert trade["executedAt"] == "2026-01-02T13:45:01.000000"
    assert trade["sourceId"] == "xtb:123:buy"


def test_legacy_xls_cash_export_with_native_excel_dates():
    data = (Path(__file__).parent / "fixtures/xtb_cash_history.xls").read_bytes()
    trade = parse_xtb(data, "history.xls", Companies()).rows[0]["transaction"]
    assert trade["ticker"] == "kgh"
    assert trade["quantity"] == "2"
    assert trade["price"] == "100.25"
    assert trade["executedAt"] == "2026-01-02T13:45:00.000000"


def test_explicit_cfd_instrument_type_cannot_be_imported_as_a_stock():
    data = (
        b"ID,Type,Time,Symbol,Quantity,Price,Currency,Instrument Type\n"
        b"1,Buy,2026-01-02,KGH.PL,2,100,PLN,CFD\n"
    )
    assert parse_xtb(data, "report.csv", Companies()).rows[0]["code"] == "unsupported_operation"


def test_conflicting_references_in_one_report_block_the_whole_batch(client):
    portfolio = create(client)
    data = workbook([cash(), cash(comment="OPEN BUY 11 @ 100.25")])
    assert preview(client, portfolio, data).json()["ledgerError"] == "import_reference_conflict"
    assert commit(client, portfolio, data, partial=True).status_code == 409
    assert client.get("/api/portfolios").json()["items"][0]["transactions"] == []


def test_ticker_column_overrides_a_descriptive_symbol_column():
    headers = ["ID", "Type", "Time", "Comment", "Symbol", "Amount", "Currency", "Ticker"]
    parsed = parse_xtb(
        workbook([cash(symbol="KGHM Polska Miedz") + ["KGH.PL"]], headers),
        "history.xlsx",
        Companies(),
    )
    assert parsed.rows[0]["transaction"]["ticker"] == "kgh"


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (cash(symbol="UNKNOWN.US"), "unknown_ticker"),
        (cash(comment="OPEN BUY NaN @ 10"), "missing_execution"),
        (cash(comment="OPEN SELL 10 @ 100"), "unsupported_operation"),
        (cash(kind="CFD", comment="OPEN BUY 10 @ 100"), "unsupported_operation"),
        (cash(time="2999-01-01"), "invalid_transaction"),
        (cash(time="not a date"), "invalid_date"),
        (cash(reference=""), "missing_reference"),
        (cash(comment="=1+1"), "formula_cell"),
        (cash(symbol="HSBA.UK"), "price_currency_missing"),
    ],
)
def test_invalid_rows_are_reported_not_guessed(row, code):
    parsed = parse_xtb(workbook([row]), "report.xlsx", Companies())
    assert parsed.rows[0]["status"] == "error"
    assert parsed.rows[0]["code"] == code


def test_fee_currency_mismatch_and_unexecuted_orders_are_blocked():
    data = (
        "ID,Type,Time,Symbol,Quantity,Price,Currency,Commission,Status\n"
        "1,Buy,2026-01-02,AAPL.US,2,200,USD,1,Pending\n"
        "2,Buy,2026-01-02,AAPL.US,2,200,PLN,1,Filled\n"
    )
    rows = parse_xtb(data.encode(), "report.csv", Companies()).rows
    assert [row["code"] for row in rows] == ["unexecuted_order", "currency_mismatch"]
    native = workbook([cash(symbol="AAPL.US") + [2]], headers=[*HEADERS, "Commission"])
    assert parse_xtb(native, "report.xlsx", Companies()).rows[0]["code"] == "fee_currency_mismatch"


def test_london_explicit_pounds_are_converted_to_pence_including_fees():
    data = (
        b"ID,Type,Time,Symbol,Quantity,Price,Currency,Commission\n"
        b"1,Buy,2026-01-02,HSBA.UK,2,5.15,GBP,1\n"
    )
    trade = parse_xtb(data, "london.csv", Companies()).rows[0]["transaction"]
    assert trade["currency"] == "GBp"
    assert trade["price"] == "515.00"
    assert trade["fees"] == "100"


@pytest.mark.parametrize(
    ("data", "name", "code"),
    [
        (b"not an Excel file", "bad.xlsx", "import_invalid_file"),
        (b"not an Excel file", "bad.xls", "import_invalid_file"),
        (b"file", "history.pdf", "import_file_type"),
        (b"x" * (MAX_FILE_BYTES + 1), "large.csv", "import_file_too_large"),
        (
            b"Symbol,Volume,Open time,Open price\nKGH.PL,1,2026-01-02,100",
            "positions.csv",
            "import_unrecognized_format",
        ),
    ],
    ids=["corrupt-xlsx", "corrupt-xls", "wrong-extension", "oversized", "positions-only"],
)
def test_file_validation(data, name, code):
    with pytest.raises(PortfolioError) as error:
        parse_xtb(data, name, Companies())
    assert error.value.code == code


def test_expanded_zip_and_huge_sheet_dimensions_are_rejected():
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for index in range(501):
            archive.writestr(str(index), "")
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        parse_xtb(output.getvalue(), "bad.xlsx", Companies())
    book = openpyxl.Workbook()
    book.active["A20001"] = "x"
    output = io.BytesIO()
    book.save(output)
    with pytest.raises(PortfolioError, match="import_too_many_rows"):
        parse_xtb(output.getvalue(), "large.xlsx", Companies())


def test_preview_does_not_save_and_bulk_commit_is_idempotent_across_csv_and_excel(client):
    portfolio = create(client)
    data = workbook(
        [
            cash(time=datetime(2026, 1, 2, 13)),
            cash("1002", "Stock sell", "2026-01-02 14:00:00", "CLOSE BUY 4 @ 120", amount=480),
        ]
    )
    inspected = preview(client, portfolio, data)
    assert inspected.status_code == 200, inspected.text
    assert inspected.headers["cache-control"] == "private, no-store"
    assert inspected.json()["ready"] == 2
    assert client.get("/api/portfolios").json()["items"][0]["transactions"] == []
    saved = commit(client, portfolio, data)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"imported": 2, "duplicates": 0, "skipped": 0, "version": 2}
    # Same raw report and stale original version are a safe retry.
    assert commit(client, portfolio, data).json()["imported"] == 0
    csv = (
        b"ID,Type,Time,Comment,Symbol,Amount,Currency\n"
        b"1001.0,Stock purchase,2026-01-02 13:00:00,OPEN BUY 10.00 @ 100.250,KGH.PL,-1002.5,PLN\n"
    )
    repeated = commit(client, portfolio, csv, "overlap.csv")
    assert repeated.json()["duplicates"] == 1
    holdings = client.get("/api/portfolios").json()["items"][0]["positions"][0]
    assert holdings["quantity"] == 6
    assert holdings["cost"] == 601.5
    assert holdings["realizedPnl"] == 79


def test_same_day_fills_are_replayed_by_execution_time_not_file_order(client):
    portfolio = create(client)
    data = workbook(
        [
            cash("2", "Stock sell", "2026-01-02 14:00:00", "CLOSE BUY 4 @ 120"),
            cash("1", time="2026-01-02 13:00:00"),
        ]
    )
    assert commit(client, portfolio, data).status_code == 200
    assert client.get("/api/portfolios").json()["items"][0]["positions"][0]["quantity"] == 6


def test_partial_import_requires_explicit_choice_and_never_saves_a_short_ledger(client):
    portfolio = create(client)
    data = workbook([cash(), cash("2", symbol="MISSING.US")])
    assert preview(client, portfolio, data).json()["errors"] == 1
    assert commit(client, portfolio, data).status_code == 422
    assert client.get("/api/portfolios").json()["items"][0]["transactions"] == []
    saved = commit(client, portfolio, data, partial=True)
    assert saved.json()["imported"] == 1
    assert saved.json()["skipped"] == 1
    current = client.get("/api/portfolios").json()["items"][0]
    sale = workbook([cash("3", "Stock sell", "2026-01-03", "CLOSE BUY 11 @ 120")])
    assert preview(client, current, sale).json()["ledgerError"] == "insufficient_shares"
    assert commit(client, current, sale, partial=True).status_code == 409
    assert len(client.get("/api/portfolios").json()["items"][0]["transactions"]) == 1


def test_stale_versions_reference_conflicts_and_manual_overlaps_are_not_overwritten(client):
    portfolio = create(client)
    updated = trade(client, portfolio, price="99", fees="0").json()
    data = workbook([cash()])
    assert commit(client, portfolio, data).status_code == 409
    assert commit(client, updated, data).status_code == 200
    current = client.get("/api/portfolios").json()["items"][0]
    changed = workbook([cash(comment="OPEN BUY 11 @ 100.25")])
    assert preview(client, current, changed).json()["ledgerError"] == "import_reference_conflict"
    assert commit(client, current, changed, partial=True).status_code == 409
    manual = workbook([cash("new", comment="OPEN BUY 10 @ 99")])
    assert preview(client, current, manual).json()["rows"][0]["code"] == "manual_overlap"


def test_import_is_private_and_owner_is_checked_before_parsing(client):
    portfolio = create(client)
    client.owner.id = 2
    assert preview(client, portfolio, b"invalid bytes").status_code == 404
    assert commit(client, portfolio, b"invalid bytes").status_code == 404
    assert preview(client, {"id": str(uuid4())}, b"invalid bytes").status_code == 404


def test_rejects_large_raw_upload_before_parsing(client):
    assert preview(client, create(client), b"x" * (MAX_FILE_BYTES + 1)).status_code == 413
