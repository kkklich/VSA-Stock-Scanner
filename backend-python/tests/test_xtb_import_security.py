"""Exercise limits through real BIFF records, before xlrd allocates cell arrays."""

import csv
import io
import struct
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pytest
import xlrd
from xlrd.sheet import Sheet

from app.services import bounded_xls, xtb_import
from app.services.bounded_xls import BoundedBook, open_bounded_xls
from app.services.portfolio import PortfolioError
from app.services.xtb_import import MAX_CELL, MAX_COLUMNS, MAX_ROWS, parse_xtb, read_tables
from tests.test_xtb_import import HEADERS, Companies, cash


def _csv(comment):
    output = io.StringIO(newline="")
    output.write("sep=,\n")
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    writer.writerow(cash(comment=comment))
    return output.getvalue().encode("utf-8")


@pytest.mark.parametrize("space", [" ", "\xa0", "\u202f", "\t", "\u2003"])
def test_maximum_length_malformed_whitespace_comment_is_bounded(space):
    comment = "OPEN BUY" + space * (MAX_CELL - 9) + "X"
    started = perf_counter()
    result = parse_xtb(_csv(comment), "history.csv", Companies())
    assert result.rows[0]["code"] == "missing_execution"
    # The previous overlapping whitespace regex took seconds/minutes on this
    # small input. Parsing this single CSV row should comfortably fit one second.
    assert perf_counter() - started < 1.0


@pytest.mark.parametrize(
    ("comment", "quantity", "price"),
    [
        ("OPEN\tBUY\u20031 /\t100\u2003@\t14.3130", "1", "14.3130"),
        ("OPEN BUY 0,125 @ 1\xa0234,56", "0.125", "1234.56"),
        ("OPEN BUY 1 @ 1\u202f234.56 PLN", "1", "1234.56"),
        ("OPEN BUY 1,234.56 @ 1.234,56", "1234.56", "1234.56"),
        ("OPEN BUY " + " " * 3950 + "1 @ 100.25", "1", "100.25"),
        ("OPEN BUY invalid; " * 100 + "OPEN BUY 2 @ 3", "2", "3"),
    ],
)
def test_linear_comment_parser_preserves_execution_formats(comment, quantity, price):
    transaction = parse_xtb(_csv(comment), "history.csv", Companies()).rows[0]["transaction"]
    assert transaction["quantity"] == quantity
    assert transaction["price"] == price


def _record(code, data=b""):
    return struct.pack("<HH", code, len(data)) + data


def _bof(version=80, stream=0x10):
    if version >= 50:
        return _record(0x0809, struct.pack("<HHHH", 0x0600, stream, 3515, 1996))
    opcode = {21: 0x0009, 30: 0x0209, 40: 0x0409}[version]
    return _record(opcode, struct.pack("<HH", 0, stream))


def _label(row, column, value, version=80):
    encoded = value.encode("latin1")
    if version == 21:
        return _record(
            0x0004, struct.pack("<HH3sB", row, column, b"\0\0\0", len(encoded)) + encoded
        )
    text = struct.pack("<H", len(encoded)) + (b"\0" if version == 80 else b"") + encoded
    return _record(0x0204, struct.pack("<HHH", row, column, 0) + text)


def _cash_cells(version=80):
    return b"".join(
        _label(row_index, column_index, str(value), version)
        for row_index, row in enumerate([HEADERS, cash()])
        for column_index, value in enumerate(row)
    )


def _dimensions(rows=1, columns=1):
    return _record(0x0200, struct.pack("<IIHHH", 0, rows, 0, columns, 0))


def _xls(sheets, *, shared_string="x", globals_extra=b""):
    """Small valid BIFF8 streams need no OLE writer or extra test dependency."""
    encoded = shared_string.encode("latin1")
    globals_prefix = (
        _bof(stream=0x05)
        + _record(0x00E0, bytes(20))  # A numeric XF for NUMBER/RK/FORMULA controls.
        + _record(0x00FC, struct.pack("<IIHB", 1, 1, len(encoded), 0) + encoded)
        + globals_extra
    )
    sheet_streams = [_bof() + _dimensions() + data + _record(0x000A) for data in sheets]
    names = [f"Cash Operations {index}".encode() for index in range(len(sheets))]
    offset = len(globals_prefix) + sum(12 + len(name) for name in names) + 4
    boundsheets = []
    for name, stream in zip(names, sheet_streams, strict=True):
        boundsheets.append(
            _record(0x0085, struct.pack("<IBBBB", offset, 0, 0, len(name), 0) + name)
        )
        offset += len(stream)
    return globals_prefix + b"".join(boundsheets) + _record(0x000A) + b"".join(sheet_streams)


def _legacy_xls(version, data):
    codepage = _record(0x0042, struct.pack("<H", 1252))
    sheet = _bof(40 if version == 45 else version) + codepage + data + _record(0x000A)
    if version != 45:
        return sheet
    name = b"Cash Operations"
    return (
        _bof(40, stream=0x0100)
        + codepage
        + _record(0x008E, struct.pack("<I", 0))
        + _record(0x0085, bytes([len(name)]) + name)
        + _record(0x008F, struct.pack("<IB", len(sheet), len(name)) + name)
        + sheet
        + _record(0x000A)
    )


def _cell_record(kind, row, column):
    address = struct.pack("<HHH", row, column, 0)
    if kind == "label":
        return _label(row, column, "x")
    if kind == "number":
        return _record(0x0203, address + struct.pack("<d", 1.0))
    if kind == "boolerr":
        return _record(0x0205, address + bytes([1, 0]))
    if kind == "rk":
        return _record(0x027E, address + struct.pack("<i", 6))
    if kind == "mulrk":
        return _record(0x00BD, address + struct.pack("<iH", 6, column))
    if kind == "formula":
        return _record(0x0006, address + struct.pack("<dH", 1.0, 0))
    if kind == "formula-string":
        return _record(0x0006, address + b"\0\0\0\0\0\0\xff\xff" + bytes(2)) + _record(
            0x0207, b"\x01\0\0x"
        )
    if kind == "labelsst":
        return _record(0x00FD, address + struct.pack("<i", 0))
    if kind == "rstring":
        return _record(0x00D6, address + b"\x01\0\0x\0\0")
    raise AssertionError(kind)


CELL_KINDS = [
    "label",
    "number",
    "boolerr",
    "rk",
    "mulrk",
    "formula",
    "formula-string",
    "labelsst",
    "rstring",
]


@pytest.mark.parametrize("kind", CELL_KINDS)
@pytest.mark.parametrize("coordinate", [(MAX_ROWS, 0), (1, MAX_COLUMNS), (65535, 255)])
@pytest.mark.parametrize("ragged", [True, False])
def test_xls_rejects_actual_cell_coordinates_before_allocation(
    monkeypatch, kind, coordinate, ragged
):
    original_load = BoundedBook.biff2_8_load

    def load(book, **kwargs):
        kwargs["ragged_rows"] = ragged
        return original_load(book, **kwargs)

    monkeypatch.setattr(BoundedBook, "biff2_8_load", load)
    method = "put_cell_ragged" if ragged else "put_cell_unragged"
    original_put = getattr(Sheet, method)
    written = []

    def put(sheet, row, column, *args):
        written.append((row, column))
        return original_put(sheet, row, column, *args)

    monkeypatch.setattr(Sheet, method, put)
    data = _xls([_cash_cells() + _cell_record(kind, *coordinate)])
    with pytest.raises(PortfolioError, match="import_too_many_rows") as error:
        parse_xtb(data, "history.xls", Companies())
    assert error.value.status == 413
    assert written  # Real headers were decoded before reaching the hostile cell.
    assert all(row < MAX_ROWS and column < MAX_COLUMNS for row, column in written)


@pytest.mark.parametrize("kind", CELL_KINDS)
def test_xls_alternate_cell_records_within_limits_are_supported(kind):
    data = _xls([_cash_cells() + _cell_record(kind, 2, 0)])
    tables = read_tables(data, "history.xls")
    assert tables[0][1][0] == HEADERS
    assert tables[0][1][2][0] in ("x", 1, 1.0)


@pytest.mark.parametrize("version", [21, 30, 40, 45])
def test_early_biff_formats_keep_working_with_bounded_sheet_factory(version):
    cells = _cash_cells(40 if version == 45 else version)
    parsed = parse_xtb(_legacy_xls(version, cells), "history.xls", Companies())
    assert parsed.rows[0]["transaction"]["quantity"] == "10"
    assert parsed.rows[0]["transaction"]["price"] == "100.25"


@pytest.mark.parametrize("version", [21, 30, 40, 45])
def test_early_biff_formats_cannot_bypass_cell_limits(version):
    cell_version = 40 if version == 45 else version
    cells = _cash_cells(cell_version) + _label(1, MAX_COLUMNS, "x", cell_version)
    with pytest.raises(PortfolioError, match="import_too_many_rows"):
        parse_xtb(_legacy_xls(version, cells), "history.xls", Companies())


def test_xls_dimensions_metadata_does_not_allocate_empty_rectangle():
    # xlrd treats this record as advisory; actual cells determine the size.
    data = _xls([_dimensions(65536, 256) + _cash_cells()])
    rows = read_tables(data, "history.xls")[0][1]
    assert len(rows) == 2
    assert len(rows[0]) == len(HEADERS)


def test_xls_repeated_dimensions_cannot_reset_allocation_budget():
    data = _xls([_cash_cells() + _dimensions() + _label(1, 0, "x")])
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(data, "history.xls")


@pytest.mark.parametrize("kind", ["label", "labelsst"])
def test_xls_rejects_oversized_cell_text_before_storage(monkeypatch, kind):
    value = "x" * (MAX_CELL + 1)
    original_put = Sheet.put_cell_ragged

    def put(sheet, row, column, ctype, cell_value, xf_index):
        assert not isinstance(cell_value, str) or len(cell_value) <= MAX_CELL
        return original_put(sheet, row, column, ctype, cell_value, xf_index)

    monkeypatch.setattr(Sheet, "put_cell_ragged", put)
    record = _label(2, 0, value) if kind == "label" else _cell_record(kind, 2, 0)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells() + record], shared_string=value), "history.xls")


def test_xls_aggregate_rows_are_charged_after_unloading_previous_sheet(monkeypatch):
    monkeypatch.setattr(xtb_import, "MAX_ROWS", 3)
    with pytest.raises(PortfolioError, match="import_too_many_rows"):
        read_tables(_xls([_cash_cells(), _cash_cells()]), "history.xls")


def test_xls_sparse_cells_at_the_limits_are_accepted():
    data = _xls([_label(MAX_ROWS - 1, MAX_COLUMNS - 1, "x" * MAX_CELL)])
    rows = read_tables(data, "history.xls")[0][1]
    assert len(rows) == MAX_ROWS
    assert rows[-1][-1] == "x" * MAX_CELL
    assert len(rows[-1]) == MAX_COLUMNS


def test_xls_concurrent_imports_have_independent_budgets(monkeypatch):
    monkeypatch.setattr(xtb_import, "MAX_ROWS", 2)
    valid = _xls([_cash_cells()])
    oversized = _xls([_cash_cells() + _label(2, 0, "x")])

    def parse(data):
        try:
            return parse_xtb(data, "history.xls", Companies()).rows[0]["status"]
        except PortfolioError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(parse, [valid, oversized] * 10))
    assert results == ["ready", "import_too_many_rows"] * 10


def test_xls_aggregate_cells_are_bounded_before_sparse_allocation():
    book = open_bounded_xls(
        _xls([_label(1, 1, "x"), _label(1, 1, "x")]),
        max_rows=10,
        max_columns=10,
        max_cell=MAX_CELL,
        max_sheets=12,
        max_cells=7,
    )
    try:
        assert book.sheet_by_index(0).nrows == 2
        book.unload_sheet(0)
        with pytest.raises(PortfolioError, match="import_too_many_rows"):
            book.sheet_by_index(1)
    finally:
        book.release_resources()


def test_xls_sheet_count_is_checked_before_any_sheet_is_loaded(monkeypatch):
    def unexpected_load(*args, **kwargs):
        raise AssertionError("Sheet allocation must not precede the sheet count check")

    monkeypatch.setattr(BoundedBook, "get_sheet", unexpected_load)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([b""] * 13), "history.xls")


def test_xls_reads_and_unloads_one_sheet_at_a_time(monkeypatch):
    original_get = BoundedBook.get_sheet
    seen = []

    def get(book, number, update_pos=True):
        assert all(sheet is None for sheet in book._sheet_list)
        seen.append(number)
        return original_get(book, number, update_pos)

    monkeypatch.setattr(BoundedBook, "get_sheet", get)
    assert len(read_tables(_xls([_cash_cells(), _cash_cells()]), "history.xls")) == 2
    assert seen == [0, 1]


def test_xls_unused_hyperlinks_cannot_expand_cell_ranges(monkeypatch):
    def unexpected_link(*args, **kwargs):
        raise AssertionError("Unused hyperlink ranges must not be expanded")

    monkeypatch.setattr(Sheet, "handle_hlink", unexpected_link)
    hyperlink = struct.pack("<HHHH", 0, 65535, 0, 65535)
    hyperlink += bytes.fromhex("d0c9ea79f9bace118c8200aa004ba90b")
    hyperlink += struct.pack("<II", 2, 0)
    data = _xls([_cash_cells() + _record(0x01B8, hyperlink)])
    assert parse_xtb(data, "history.xls", Companies()).rows[0]["status"] == "ready"


def _fragmented_annotation(*, with_object=True):
    obj = _record(0x005D, struct.pack("<5H", 0x15, 18, 25, 1, 0) + bytes(16))
    txo = _record(0x01B6, struct.pack("<HH6sHHH", 0, 0, bytes(6), 64, 0, 0))
    continuations = _record(0x003C, b"\0x") * 64
    note = _record(0x001C, struct.pack("<5HB", 0, 0, 0, 1, 1, 0) + b"a")
    return (obj if with_object else b"") + txo + continuations + note


def test_xls_fragmented_unused_metadata_does_not_consume_cached_cell_strings(monkeypatch):
    def unexpected_metadata(*args, **kwargs):
        raise AssertionError("Unused fragmented metadata must not be concatenated")

    monkeypatch.setattr(xlrd.book.Book, "handle_externsheet", unexpected_metadata)
    for method in ("handle_obj", "handle_txo", "handle_note"):
        monkeypatch.setattr(Sheet, method, unexpected_metadata)
    # Sixty-four external references, deliberately fragmented into single bytes.
    external = _record(0x0017, struct.pack("<H", 64)) + _record(0x003C, b"\0") * (64 * 6)
    comment = b"OPEN BUY 10 @ 100.25"
    cached_string = (
        _record(0x0006, struct.pack("<HHH", 1, 3, 0) + bytes(6) + b"\xff\xff" + bytes(2))
        + _record(0x0207, struct.pack("<HB", len(comment), 0) + comment[:9])
        + _record(0x003C, b"\0" + comment[9:])
    )
    data = _xls([_fragmented_annotation() + _cash_cells() + cached_string], globals_extra=external)
    transaction = parse_xtb(data, "history.xls", Companies()).rows[0]["transaction"]
    assert transaction["quantity"] == "10"
    assert transaction["price"] == "100.25"


def test_xls_unused_annotation_without_a_preceding_object_is_safe():
    data = _xls([_fragmented_annotation(with_object=False) + _cash_cells()])
    assert parse_xtb(data, "history.xls", Companies()).rows[0]["status"] == "ready"


@pytest.mark.parametrize("version", [21, 30, 40, 45])
def test_legacy_xls_fragmented_notes_do_not_consume_trade_cells(monkeypatch, version):
    def unexpected_note(*args, **kwargs):
        raise AssertionError("Unused legacy notes must not be assembled")

    monkeypatch.setattr(Sheet, "handle_note", unexpected_note)
    notes = _record(0x001C, struct.pack("<HHH", 0, 0, 64) + b"x")
    notes += _record(0x001C, struct.pack("<HHH", 65535, 0, 1) + b"x") * 63
    cells = _cash_cells(40 if version == 45 else version)
    assert (
        parse_xtb(_legacy_xls(version, notes + cells), "history.xls", Companies()).rows[0]["status"]
        == "ready"
    )


def _name_chain(levels=10):
    records = []
    for index in range(levels + 1):
        name = f"N{index}".encode()
        previous = b"\x23" + struct.pack("<I", index)  # One-based tName reference.
        formula = previous * 2 + b"\x08" if index else b"\x17\x01\0x"
        header = struct.pack("<HBBHHH4B", 0, 0, len(name), len(formula), 0, 0, 0, 0, 0, 0)
        records.append(_record(0x0018, header + b"\0" + name + formula))
    return b"".join(records)


def test_xls_unused_defined_names_are_never_evaluated(monkeypatch):
    data = _xls([_cash_cells()], globals_extra=_name_chain())
    # Validate the actual NAME-chain fixture at a deliberately tiny safe size.
    with xlrd.open_workbook(file_contents=data, on_demand=True) as original:
        assert original.name_obj_list[-1].result.value == "x" * 1024

    def unexpected_evaluation(*args, **kwargs):
        raise AssertionError("Unused defined names must never be evaluated")

    monkeypatch.setattr(xlrd.book, "evaluate_name_formula", unexpected_evaluation)
    monkeypatch.setattr(xlrd.formula, "evaluate_name_formula", unexpected_evaluation)
    parsed = parse_xtb(data, "history.xls", Companies())
    assert parsed.rows[0]["transaction"]["quantity"] == "10"
    assert parsed.rows[0]["transaction"]["price"] == "100.25"


def _sst_chunks(*chunks):
    return _record(0x00FC, chunks[0]) + b"".join(_record(0x003C, chunk) for chunk in chunks[1:])


def _sst_text(value):
    return struct.pack("<HB", len(value), 0) + value.encode("latin1")


@pytest.mark.parametrize("unique", [1, 16, 0x7FFFFFFF])
def test_xls_shared_strings_cannot_rewind_phonetic_data(unique):
    payload = struct.pack("<IIHBi", unique, unique, 0, 4, -7)
    data = _xls([_cash_cells()], globals_extra=_sst_chunks(payload))
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(data, "history.xls")


def test_xls_shared_strings_cannot_repeat_large_text_with_a_negative_phonetic_length():
    text = b"x" * MAX_CELL
    payload = struct.pack("<IIHBi", 2, 2, len(text), 4, -(7 + len(text))) + text
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells()], globals_extra=_sst_chunks(payload)), "history.xls")


def test_xls_shared_strings_have_a_cumulative_storage_budget(monkeypatch):
    monkeypatch.setattr(bounded_xls, "MAX_SST_BYTES", 160)
    payload = struct.pack("<II", 2, 2) + _sst_text("abcde") + _sst_text("fghij")
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells()], globals_extra=_sst_chunks(payload)), "history.xls")


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (
            [struct.pack("<IIHB", 1, 1, 2, 0) + b"a", b"\1" + "ą".encode("utf-16-le")],
            ["aą"],
        ),
        (
            [struct.pack("<IIHB", 1, 1, 2, 1) + "ą".encode("utf-16-le"), b"\0b"],
            ["ąb"],
        ),
        (
            [struct.pack("<II", 2, 2) + _sst_text("a"), _sst_text("b")],
            ["a", "b"],
        ),
        (
            [struct.pack("<II", 2, 2) + _sst_text(""), _sst_text("b")],
            ["", "b"],
        ),
        (
            [
                struct.pack("<IIHBH", 2, 2, 1, 8, 1) + b"a",
                struct.pack("<HH", 0, 0) + _sst_text("b"),
            ],
            ["a", "b"],
        ),
        (
            [
                struct.pack("<IIHBHI", 2, 2, 1, 12, 1, 6) + b"a\0\0",
                b"\0\0" + b"12",
                b"3456" + _sst_text("b"),
            ],
            ["a", "b"],
        ),
        (
            [struct.pack("<IIHB", 1, 1, 2, 1) + b"\x3d\xd8", b"\1\0\xde"],
            ["😀"],
        ),
    ],
    ids=[
        "compressed-to-wide",
        "wide-to-compressed",
        "string-boundary",
        "empty-string-boundary",
        "richtext-continuation",
        "phonetics-across-records",
        "surrogate-pair-continuation",
    ],
)
def test_xls_shared_strings_preserve_continuations_and_skip_metadata(chunks, expected, monkeypatch):
    def unexpected_upstream_decode(*args, **kwargs):
        raise AssertionError("Shared strings must use the bounded decoder")

    monkeypatch.setattr(xlrd.book, "unpack_SST_table", unexpected_upstream_decode)
    cells = _cash_cells() + b"".join(
        _record(0x00FD, struct.pack("<HHHi", 2 + index, 0, 0, index))
        for index in range(len(expected))
    )
    data = _xls([cells], globals_extra=_sst_chunks(*chunks))
    rows = read_tables(data, "history.xls")[0][1]
    assert [row[0] for row in rows[2:]] == expected
    assert parse_xtb(data, "history.xls", Companies()).rows[0]["status"] == "ready"


@pytest.mark.parametrize(
    "payload",
    [
        struct.pack("<IIHB", 1, 2, 0, 0),  # More unique strings than references.
        struct.pack("<IIHB", 1, 1, MAX_CELL + 1, 0),  # Oversized before decoding.
        struct.pack("<IIHB", 1, 1, 2, 0) + b"a",  # Truncated continued text.
        struct.pack("<IIHBH", 1, 1, 0, 8, 65535),  # Truncated rich-text runs.
        struct.pack("<IIHBI", 1, 1, 0, 4, 100),  # Truncated phonetic payload.
    ],
)
def test_xls_malformed_shared_string_lengths_are_rejected(payload):
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells()], globals_extra=_sst_chunks(payload)), "history.xls")


def _format_record(value, key=164):
    return _record(0x041E, struct.pack("<HHB", key, len(value), 0) + value.encode("latin1"))


def test_xls_format_brackets_never_reach_the_backtracking_classifier(monkeypatch):
    def unexpected_regex(*args, **kwargs):
        raise AssertionError("Format metadata must use the linear classifier")

    monkeypatch.setattr(xlrd.formatting, "fmt_bracketed_sub", unexpected_regex)
    data = _xls([_cash_cells()], globals_extra=_format_record("[" * MAX_CELL))
    started = perf_counter()
    assert parse_xtb(data, "history.xls", Companies()).rows[0]["status"] == "ready"
    assert perf_counter() - started < 1.0


@pytest.mark.parametrize("workers", [1, 4])
def test_xls_format_guards_survive_reinitialization_and_concurrent_imports(monkeypatch, workers):
    def unexpected_regex(*args, **kwargs):
        raise AssertionError("xlrd's class rebinding must not replace instance guards")

    monkeypatch.setattr(xlrd.formatting, "fmt_bracketed_sub", unexpected_regex)
    data = _xls([_cash_cells()], globals_extra=_format_record("[" * MAX_CELL))

    def parse(_):
        return parse_xtb(data, "history.xls", Companies()).rows[0]["status"]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        assert list(pool.map(parse, range(12))) == ["ready"] * 12


@pytest.mark.parametrize(
    ("key", "format_string", "is_date"),
    [
        (14, None, True),  # Built-in date formats still use xlrd's format table.
        (0, None, False),
        (164, "yyyy-mm-dd hh:mm:ss", True),
        (164, 'yyyy-mm-dd" literal "hh:mm:ss', True),
        (164, r"yyyy\y-mm\m-dd\d hh\h:mm\m:ss\s", True),
        (164, "[Red][>=1]yyyy-mm-dd hh:mm:ss", True),
        (164, "[[nested]yyyy-mm-dd[", True),
        (164, "[$-409]m/d/yy h:mm;@", True),
        (164, '0 "days"', False),
        (164, 'General"."', False),
        (164, "0.00E+00", False),
        (164, r"0\y_m*d", False),
        (164, "0ymd", True),
        (164, "0y", False),
        (164, "000y", False),
    ],
)
def test_xls_format_classifier_preserves_native_dates_and_numbers(key, format_string, is_date):
    formats = _format_record(format_string, key) if format_string is not None else b""
    # XF index 1 uses this format; index 0 remains the default numeric XF.
    formats += _record(0x00E0, struct.pack("<HH", 0, key) + bytes(16))
    serial = xlrd.xldate.xldate_from_datetime_tuple((2026, 1, 2, 13, 45, 0), 0)
    time_cell = _record(0x0203, struct.pack("<HHHd", 1, 2, 1, serial))
    data = _xls([_cash_cells() + time_cell], globals_extra=formats)
    result = parse_xtb(data, "history.xls", Companies()).rows[0]
    if is_date:
        assert result["transaction"]["executedAt"] == "2026-01-02T13:45:00.000000"
    else:
        assert result["code"] == "invalid_date"
        assert read_tables(data, "history.xls")[0][1][1][2] == serial


def test_xls_format_metadata_count_is_bounded_before_classification(monkeypatch):
    monkeypatch.setattr(bounded_xls, "MAX_FORMATS", 2)
    calls = []
    classify = BoundedBook._is_date_format_string

    def count(book, value):
        calls.append(value)
        return classify(book, value)

    monkeypatch.setattr(BoundedBook, "_is_date_format_string", count)
    formats = b"".join(_format_record("0", 164 + index) for index in range(3))
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells()], globals_extra=formats), "history.xls")
    assert calls == ["0", "0"]


def test_xls_format_metadata_aggregate_payload_is_bounded(monkeypatch):
    monkeypatch.setattr(bounded_xls, "MAX_FORMAT_BYTES", 10)
    formats = _format_record("0") + _format_record("0", 165)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells()], globals_extra=formats), "history.xls")


def test_xls_xf_metadata_is_bounded_before_allocating_formatting_objects(monkeypatch):
    monkeypatch.setattr(bounded_xls, "MAX_XFS", 2)
    calls = []
    allocate = bounded_xls.xlrd_handle_xf

    def count(book, value):
        calls.append(value)
        return allocate(book, value)

    monkeypatch.setattr(bounded_xls, "xlrd_handle_xf", count)
    # The fixture already has one XF record; only the first additional one fits.
    extras = _record(0x00E0, bytes(20)) * 2
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_xls([_cash_cells()], globals_extra=extras), "history.xls")
    assert calls == [bytes(20), bytes(20)]


@pytest.mark.parametrize("limit", [16, 17])
def test_legacy_xls_synthesized_formats_share_the_xf_budget(monkeypatch, limit):
    monkeypatch.setattr(bounded_xls, "MAX_XFS", limit)
    calls = []
    allocate = Sheet.insert_new_BIFF20_xf

    def count(sheet, cell_attr, style=0):
        calls.append(cell_attr)
        return allocate(sheet, cell_attr, style)

    monkeypatch.setattr(Sheet, "insert_new_BIFF20_xf", count)
    data = _legacy_xls(21, _cash_cells(21))
    # BIFF2 synthesizes sixteen default XFs, then one for the cell attributes.
    if limit == 16:
        with pytest.raises(PortfolioError, match="import_invalid_file"):
            parse_xtb(data, "history.xls", Companies())
    else:
        assert parse_xtb(data, "history.xls", Companies()).rows[0]["status"] == "ready"
    assert len(calls) == limit


def test_xls_oversized_format_text_is_rejected():
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(
            _xls([_cash_cells()], globals_extra=_format_record("[" * (MAX_CELL + 1))),
            "history.xls",
        )


@pytest.mark.parametrize(
    "bad_record",
    [
        _record(0x0203, b"\0"),  # Truncated numeric cell: struct.error.
        _record(0x00FD, struct.pack("<HHHi", 0, 0, 0, 99)),  # Bad SST index.
        _record(0x0205, struct.pack("<HHHBB", 0, 0, 0, 1, 9)),  # Bad BOOLERR type.
    ],
)
def test_malformed_xls_parser_errors_are_reported_as_invalid_file(bad_record):
    with pytest.raises(PortfolioError, match="import_invalid_file") as error:
        read_tables(_xls([bad_record]), "history.xls")
    assert error.value.status == 422


def test_unsupported_legacy_codepage_is_reported_as_invalid_file():
    data = _legacy_xls(40, _record(0x0042, struct.pack("<H", 65535)) + _cash_cells(40))
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(data, "history.xls")
