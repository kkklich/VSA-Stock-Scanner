"""Each uploaded worksheet becomes its own independent, reproducible ledger."""

import io
from datetime import datetime
from types import SimpleNamespace

import openpyxl
import pytest

from app.services.xtb_import import prepare_import
from app.services.xtb_wallet_import import parse_xtb_wallets


class Companies:
    def find(self, ticker):
        if ticker in {"kgh", "aapl.us", "hsba.l"}:
            return SimpleNamespace(ticker=ticker, currency=None)
        return None


CLOSED_HEADERS = [
    "Instrument",
    "Ticker",
    "Category",
    "Type",
    "Volume",
    "Open Price",
    "Open Time (UTC)",
    "Close Price",
    "Close Time (UTC)",
    "Product",
    "Commission",
    "Position ID",
]
OPEN_HEADERS = [
    "Product",
    "Instrument/Position",
    "Ticker",
    "Category",
    "Type",
    "Volume",
    "Value",
    "Current price",
    "Open price",
    "Open time (UTC)",
    "Open Commission",
]
CASH_HEADERS = ["ID", "Type", "Time", "Comment", "Symbol", "Amount", "Currency"]
BUY_TIME = datetime(2026, 1, 2, 12, 0, 0)
SELL_TIME = datetime(2026, 1, 3, 13, 0, 0)


def closed(*, quantity=4, price=120, symbol="KGH.PL", category="STOCK", side="BUY", fees=0):
    return [
        "Example",
        symbol,
        category,
        side,
        quantity,
        100,
        BUY_TIME,
        price,
        SELL_TIME,
        "IKE",
        fees,
        12345,
    ]


def opened(*, side="BUY", category="STOCK", fees=None):
    return ["IKE", 23456, "KGH.PL", category, side, 2, 9999, 900, 110, BUY_TIME, fees]


def workbook(*sheets, metadata=()):
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, headers, rows in sheets:
        sheet = book.create_sheet(name)
        sheet.append(["Account number", "anonymous"])
        sheet.append([name])
        for row in metadata:
            sheet.append(row)
        sheet.append([])
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def parse(data):
    return parse_xtb_wallets(data, "example.xlsx", Companies())


def test_all_three_native_report_tabs_produce_independent_wallets():
    data = workbook(
        ("Closed Positions", CLOSED_HEADERS, [closed()]),
        (
            "Cash Operations",
            CASH_HEADERS,
            [
                [
                    "1001",
                    "Stock purchase",
                    BUY_TIME,
                    "OPEN BUY KGH.PL 10 @ 100",
                    "KGH.PL",
                    -1000,
                    "PLN",
                ],
                ["1002", "Stock sell", SELL_TIME, "CLOSE BUY KGH.PL 4 @ 120", "KGH.PL", 480, "PLN"],
            ],
        ),
        ("Open Positions", OPEN_HEADERS, [opened()]),
    )
    wallets = parse(data)
    assert [w["name"] for w in wallets] == ["Closed Positions", "Cash Operations", "Open Positions"]
    assert all(w["error"] is None for w in wallets)
    assert [len(w["parsed"].rows) for w in wallets] == [2, 2, 1]
    for wallet in wallets:
        plan = prepare_import(wallet["parsed"], [], "fifo")
        assert plan["ledgerError"] is None
        assert plan["errors"] == 0
        assert {row["sheet"] for row in plan["rows"]} == {wallet["sheet"]}
    closed_trades = [row["transaction"] for row in wallets[0]["parsed"].rows]
    assert [(t["side"], t["quantity"], t["price"]) for t in closed_trades] == [
        ("buy", "4", "100"),
        ("sell", "4", "120"),
    ]


def test_open_lots_omit_instrument_totals_and_use_execution_price_not_current_or_value():
    aggregate = ["IKE", "Example", "KGH.PL", "STOCK", None, 2, 9999, 900, 110]
    wallet = parse(workbook(("Open Positions", OPEN_HEADERS, [aggregate, opened()])))[0]
    assert wallet["error"] is None
    parsed = wallet["parsed"]
    assert parsed.ignored == 1
    assert len(parsed.rows) == 1
    trade = parsed.rows[0]["transaction"]
    assert (trade["side"], trade["quantity"], trade["price"], trade["currency"]) == (
        "buy",
        "2",
        "110",
        "PLN",
    )
    assert trade["executedAt"] == "2026-01-02T12:00:00.000000+00:00"
    assert parsed.warnings == ["fees_missing", "open_positions_snapshot"]


def test_closed_partial_slices_have_distinct_stable_ids_when_reordered():
    rows = [closed(quantity=4, price=120), closed(quantity=6, price=121)]
    first = parse(workbook(("Closed Positions", CLOSED_HEADERS, rows)))[0]["parsed"]
    reordered = parse(workbook(("Closed Positions", CLOSED_HEADERS, list(reversed(rows)))))[0][
        "parsed"
    ]
    first_ids = {row["transaction"]["id"] for row in first.rows}
    assert len(first_ids) == 4
    assert first_ids == {row["transaction"]["id"] for row in reordered.rows}
    saved = prepare_import(first, [], "fifo")["ledger"]
    repeated = prepare_import(reordered, saved, "fifo")
    assert repeated["ready"] == 0
    assert repeated["duplicates"] == 4


def test_closed_unknown_or_invalid_slice_never_adds_its_other_leg():
    invalid = closed()
    invalid[7] = "not a price"
    wallets = parse(
        workbook(("Closed Positions", CLOSED_HEADERS, [invalid, closed(symbol="UNKNOWN.PL")]))
    )
    rows = wallets[0]["parsed"].rows
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"error"}
    assert {row["code"] for row in rows} == {"invalid_number", "unknown_ticker"}
    assert all("transaction" not in row for row in rows)


@pytest.mark.parametrize("row", [opened(side="SELL"), opened(category="CFD")])
def test_short_or_derivative_position_is_an_explicit_error(row):
    parsed = parse(workbook(("Open Positions", OPEN_HEADERS, [row])))[0]["parsed"]
    assert parsed.rows[0]["code"] == "unsupported_operation"
    assert parsed.rows[0]["status"] == "error"


def test_open_lot_inherits_derivative_category_from_its_instrument_summary():
    aggregate = ["IKE", "Example CFD", "KGH.PL", "CFD", None, 2]
    row = opened(category=None)
    parsed = parse(workbook(("Open Positions", OPEN_HEADERS, [aggregate, row])))[0]["parsed"]
    assert parsed.ignored == 1
    assert parsed.rows[0]["code"] == "unsupported_operation"
    assert parsed.rows[0]["status"] == "error"


def test_snapshot_warnings_explain_the_independent_scope_of_each_wallet():
    wallets = parse(
        workbook(
            ("Closed Positions", CLOSED_HEADERS, [closed()]),
            ("Open Positions", OPEN_HEADERS, [opened(fees=0)]),
        )
    )
    assert wallets[0]["parsed"].warnings == ["closed_positions_snapshot"]
    assert wallets[1]["parsed"].warnings == ["open_positions_snapshot"]


def test_nonzero_commission_requires_its_currency_and_is_assigned_once_for_closed_slice():
    unknown_fee = parse(workbook(("Closed Positions", CLOSED_HEADERS, [closed(fees=2)])))[0]
    assert unknown_fee["parsed"].rows[0]["code"] == "fee_currency_missing"
    known_fee = parse(
        workbook(
            ("Closed Positions", [*CLOSED_HEADERS, "Fee Currency"], [closed(fees=2) + ["PLN"]])
        )
    )[0]
    trades = [row["transaction"] for row in known_fee["parsed"].rows]
    assert [trade["fees"] for trade in trades] == ["0", "2"]


def test_blank_and_unknown_tabs_remain_visible_with_their_own_errors():
    wallets = parse(
        workbook(
            ("Notes", ["Message"], [["Example text"]]),
            ("Empty", [], []),
            ("Open Positions", OPEN_HEADERS, [opened()]),
        )
    )
    assert [w["sheet"] for w in wallets] == ["Notes", "Empty", "Open Positions"]
    assert [w["error"] for w in wallets] == [
        "import_unrecognized_format",
        "import_unrecognized_format",
        None,
    ]
    assert len(wallets[2]["parsed"].rows) == 1


def test_regular_trade_worksheets_are_not_combined_or_filtered_out_by_cash_sheet_name():
    headers = ["ID", "Type", "Time", "Ticker", "Quantity", "Price", "Currency"]
    wallets = parse(
        workbook(
            ("Cash Operations", headers, [["1001", "Buy", BUY_TIME, "KGH.PL", 2, 100, "PLN"]]),
            ("Another wallet", headers, [["1002", "Buy", BUY_TIME, "KGH.PL", 3, 110, "PLN"]]),
        )
    )
    assert [len(w["parsed"].rows) for w in wallets] == [1, 1]
    assert [w["parsed"].rows[0]["transaction"]["quantity"] for w in wallets] == ["2", "3"]


def test_repeated_csv_sections_have_unique_wallet_identities():
    data = (
        b"Cash Operations,,,,,,\n"
        b"ID,Type,Time,Comment,Symbol,Amount,Currency\n"
        b"1001,Buy,2026-01-02 12:00:00,OPEN BUY 1 @ 100,KGH.PL,-100,PLN\n"
        b"Cash Operations,,,,,,\n"
        b"ID,Type,Time,Comment,Symbol,Amount,Currency\n"
        b"1002,Buy,2026-01-02 12:00:00,OPEN BUY 2 @ 100,KGH.PL,-200,PLN\n"
    )
    wallets = parse_xtb_wallets(data, "report.csv", Companies())
    assert [w["sheet"] for w in wallets] == ["Cash Operations", "Cash Operations (2)"]
    assert [w["name"] for w in wallets] == ["Cash Operations", "Cash Operations (2)"]
    assert [len(w["parsed"].rows) for w in wallets] == [1, 1]


@pytest.mark.parametrize("closing_columns", [["Close Price"], ["Close Time (UTC+1)"], []])
def test_incomplete_closed_layout_cannot_import_sold_lots_as_open(closing_columns):
    headers = [*CLOSED_HEADERS[:7], *closing_columns, *CLOSED_HEADERS[9:]]
    row = closed()
    wallet = parse(
        workbook(
            ("Closed Positions", headers, [row[:7] + row[7 : 7 + len(closing_columns)] + row[9:]])
        )
    )[0]
    assert wallet["error"] == "import_unrecognized_format"
    assert wallet["parsed"].rows == []


def test_valid_empty_native_tabs_remain_in_the_batch():
    wallets = parse(
        workbook(
            ("Closed Positions", CLOSED_HEADERS, [["Profit/loss"]]),
            ("Cash Operations", CASH_HEADERS, [["Total"]]),
            ("Open Positions", OPEN_HEADERS, [opened()]),
        )
    )
    assert [w["error"] for w in wallets] == [None, None, None]
    assert [len(w["parsed"].rows) for w in wallets] == [0, 0, 1]
    assert [w["parsed"].ignored for w in wallets] == [1, 1, 0]


def test_missing_direction_is_reported_on_a_detail_row_even_without_open_time():
    row = opened(side=None)
    row[9] = None
    wallet = parse(workbook(("Open Positions", OPEN_HEADERS, [row, opened()])))[0]
    assert wallet["parsed"].ignored == 0
    assert [r["status"] for r in wallet["parsed"].rows] == ["error", "ready"]
    assert wallet["parsed"].rows[0]["code"] == "unsupported_operation"


def test_snapshot_uses_explicit_quote_currency_and_never_guesses_pounds_or_pence():
    row = opened(fees=0)
    row[2], row[8] = "HSBA.UK", 8.5
    unspecified = parse(workbook(("Open Positions", OPEN_HEADERS, [row])))[0]
    assert unspecified["parsed"].rows[0]["code"] == "price_currency_missing"
    priced = parse(
        workbook(("Open Positions", [*OPEN_HEADERS, "Price Currency"], [row + ["GBP"]]))
    )[0]
    transaction = priced["parsed"].rows[0]["transaction"]
    assert (transaction["price"], transaction["currency"]) == ("850.0", "GBp")


def test_large_snapshot_quantity_is_an_invalid_row_instead_of_an_exception():
    row = opened()
    row[5] = "1e1000000"
    wallet = parse(workbook(("Open Positions", OPEN_HEADERS, [row])))[0]
    assert wallet["parsed"].rows[0]["code"] == "invalid_number"


def test_snapshot_retains_utc_instant_and_uses_warsaw_date_without_changing_retry_ids():
    row = opened()
    row[9] = datetime(2026, 1, 2, 23, 30)
    data = workbook(
        ("Open Positions", OPEN_HEADERS, [row]),
        metadata=[("Data as of report generated", datetime(2026, 1, 3, 10, 1, 2, 3000))],
    )
    wallet = parse(data)[0]
    trade = wallet["parsed"].rows[0]["transaction"]
    assert wallet["account"] == "anonymous"
    assert wallet["snapshotAsOf"] == "2026-01-03T10:01:02.003000+00:00"
    assert trade["date"] == "2026-01-03"
    assert trade["executedAt"] == "2026-01-02T23:30:00.000000+00:00"
    old_report = workbook(
        ("Open Positions", [*OPEN_HEADERS[:9], "Open time", *OPEN_HEADERS[10:]], [row])
    )
    old_trade = parse(old_report)[0]["parsed"].rows[0]["transaction"]
    assert old_trade["id"] == trade["id"]
    assert old_trade["date"] == "2026-01-02"
    retried = prepare_import(wallet["parsed"], [old_trade], "fifo")
    assert retried["duplicates"] == 1
    assert retried["ledgerError"] is None


def test_report_title_in_csv_preamble_does_not_create_a_phantom_wallet():
    data = (
        b"XTB Account History,,,,,,\nAccount number,anonymous,,,,,\nCash Operations,,,,,,\n"
        b"ID,Type,Time,Comment,Symbol,Amount,Currency\n"
        b"1001,Buy,2026-01-02 12:00:00,OPEN BUY 1 @ 100,KGH.PL,-100,PLN\n"
    )
    wallets = parse_xtb_wallets(data, "report.csv", Companies())
    assert [w["sheet"] for w in wallets] == ["Cash Operations"]
    assert len(wallets[0]["parsed"].rows) == 1


def test_wallet_csv_sections_keep_separate_exact_account_ids():
    trades = (
        b"Cash Operations,,,,,,\nID,Type,Time,Comment,Symbol,Amount,Currency\n"
        b"1001,Buy,2026-01-02 12:00:00,OPEN BUY 1 @ 100,KGH.PL,-100,PLN\n"
    )
    data = b"Account number,00123456,,,,,\n" + trades + b"Account number,00123457,,,,,\n" + trades
    wallets = parse_xtb_wallets(data, "report.csv", Companies())
    assert [w["sheet"] for w in wallets] == ["Cash Operations", "Cash Operations (2)"]
    assert [w["section"] for w in wallets] == ["Cash Operations", "Cash Operations"]
    assert [w["brokerAccountId"] for w in wallets] == ["00123456", "00123457"]
    assert [w["parsed"].broker_account_id for w in wallets] == ["00123456", "00123457"]
