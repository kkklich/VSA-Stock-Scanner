"""XTB workbooks may declare A1:A1 despite containing complete report tables."""

import io
import re
from types import SimpleNamespace
from zipfile import ZipFile

import openpyxl
import pytest

from app.services.portfolio import PortfolioError
from app.services.xtb_import import MAX_COLUMNS, MAX_ROWS, parse_xtb, read_tables


class Companies:
    def find(self, ticker):
        return SimpleNamespace(ticker=ticker, currency="PLN") if ticker == "kgh" else None


def report(*, dimension="A1:A1", extra_cell=None, second_sheet=False):
    """Generate anonymous report data and alter only its worksheet dimensions."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Cash Operations"
    sheet.append(["Account number", "example"])
    sheet.append(["Cash Operations"])
    sheet.append([])
    sheet.append(["ID", "Type", "Time", "Comment", "Symbol", "Amount", "Currency"])
    sheet.append(
        [
            "1001",
            "Stock purchase",
            "2026-01-02 12:00:00",
            "OPEN BUY 10 @ 100.25",
            "KGH.PL",
            -1002.5,
            "PLN",
        ]
    )
    if extra_cell:
        sheet.cell(*extra_cell, value="extra")
    if second_sheet:
        other = book.create_sheet("Other wallet")
        other.append(["ID", "Type", "Time", "Symbol", "Quantity", "Price", "Currency"])
        other.append(["1002", "Buy", "2026-01-03 12:00:00", "KGH.PL", 2, 110, "PLN"])
    source = io.BytesIO()
    book.save(source)
    output = io.BytesIO()
    with ZipFile(source) as original, ZipFile(output, "w") as rewritten:
        for info in original.infolist():
            payload = original.read(info.filename)
            if info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml"):
                replacement = (
                    b"" if dimension is None else f'<dimension ref="{dimension}"/>'.encode()
                )
                payload, count = re.subn(rb'<dimension ref="[^"]*"\s*/>', replacement, payload)
                assert count == 1
            rewritten.writestr(info, payload)
    return output.getvalue()


@pytest.mark.parametrize("dimension", ["A1:A1", "A1:B2", None])
def test_read_tables_uses_actual_cells_when_dimensions_are_inaccurate_or_absent(dimension):
    tables = read_tables(report(dimension=dimension), "report.xlsx")
    assert len(tables) == 1
    title, rows = tables[0]
    assert title == "Cash Operations"
    assert len(rows) == 5
    assert rows[3][:3] == ["ID", "Type", "Time"]
    assert rows[4][4:] == ["KGH.PL", -1002.5, "PLN"]


@pytest.mark.parametrize("dimension", ["A1:A1", None])
def test_parse_xtb_reads_complete_trade_from_inaccurate_or_absent_dimensions(dimension):
    parsed = parse_xtb(report(dimension=dimension), "report.xlsx", Companies())
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row["sheet"] == "Cash Operations"
    assert row["row"] == 5
    assert row["status"] == "ready"
    assert row["transaction"]["ticker"] == "kgh"
    assert row["transaction"]["quantity"] == "10"
    assert row["transaction"]["price"] == "100.25"


@pytest.mark.parametrize("dimension", ["A1:A1", None])
@pytest.mark.parametrize(
    "extra_cell",
    [(MAX_ROWS + 1, 1), (6, MAX_COLUMNS + 1), (6, 16384)],
)
def test_actual_out_of_bounds_cells_cannot_hide_behind_dimensions(dimension, extra_cell):
    with pytest.raises(PortfolioError) as caught:
        read_tables(report(dimension=dimension, extra_cell=extra_cell), "report.xlsx")
    assert caught.value.code == "import_too_many_rows"
    assert caught.value.status == 413


def test_each_worksheet_is_read_beyond_its_declared_dimensions():
    tables = read_tables(report(second_sheet=True), "report.xlsx")
    assert [(title, len(rows)) for title, rows in tables] == [
        ("Cash Operations", 5),
        ("Other wallet", 2),
    ]
    assert tables[1][1][1][0] == "1002"
