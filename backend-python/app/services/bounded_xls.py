"""Cell-allocation limits for the XTB XLS reader, integrated with xlrd 2.0.2.

xlrd has no sheet factory or pre-allocation callback. The small get_sheet and
open_bounded_xls adapters follow that pinned version's Book.get_sheet and
open_workbook_xls initialization, including BIFF 2-4 and 4W. Keep these adapters
and the allocation-route regression tests in sync when upgrading xlrd. No
process-global classes or methods are changed.
"""

import struct
from time import perf_counter

from xlrd.biffh import XL_CONTINUE, XL_FORMAT, XL_WORKBOOK_GLOBALS, XL_WORKSHEET, XLRDError
from xlrd.book import SUPPORTED_VERSIONS, Book
from xlrd.formatting import date_char_dict, non_date_formats, num_char_dict, skip_char_dict
from xlrd.formatting import handle_format as xlrd_handle_format
from xlrd.formatting import handle_xf as xlrd_handle_xf
from xlrd.sheet import Sheet

from app.services.portfolio import PortfolioError
from app.services.xls_container import validate_xls_container

MAX_SST_BYTES = 30 * 1024 * 1024
MAX_FORMATS = 1024
MAX_FORMAT_BYTES = 256 * 1024
MAX_XFS = 4096


class _SSTReader:
    """Forward-only access to SST records; only continued text has a flag byte."""

    def __init__(self, records):
        self.records = records
        self.index = 0
        self.position = 0
        self.remaining = sum(map(len, records))

    def _next(self):
        self.index += 1
        self.position = 0
        if self.index >= len(self.records):
            raise PortfolioError("import_invalid_file", 422)

    def read(self, size, *, discard=False):
        if not 0 <= size <= self.remaining:
            raise PortfolioError("import_invalid_file", 422)
        pieces = []
        while size:
            record = self.records[self.index]
            available = len(record) - self.position
            if not available:
                self._next()
                continue
            count = min(size, available)
            if not discard:
                pieces.append(record[self.position : self.position + count])
            self.position += count
            self.remaining -= count
            size -= count
        return b"".join(pieces)

    def text(self, characters, wide):
        pieces = []
        while characters:
            record = self.records[self.index]
            if self.position == len(record):
                self._next()
                flag = self.read(1)[0]
                if flag not in (0, 1):
                    raise PortfolioError("import_invalid_file", 422)
                wide = bool(flag)
                record = self.records[self.index]
            width = 2 if wide else 1
            count = min(characters, (len(record) - self.position) // width)
            if not count:
                raise PortfolioError("import_invalid_file", 422)
            raw = self.read(count * width)
            pieces.append(raw if wide else raw.decode("latin1").encode("utf-16-le"))
            characters -= count
            if characters and self.position != len(record):
                # BIFF continuations split between UTF-16 code units.
                raise PortfolioError("import_invalid_file", 422)
        # Joining first also supports a surrogate pair split between records.
        return b"".join(pieces).decode("utf-16-le")


class BoundedSheet(Sheet):
    def __init__(self, book, position, name, number):
        super().__init__(book, position, name, number)
        self._bounded_rows = 0
        self._bounded_columns = 0

    def _check_dimensions(self):
        # DIMENSIONS is advisory, not an allocation bound. A second DIMENSIONS
        # record after cells resets xlrd's counters without clearing its arrays.
        if self.nrows != len(self._cell_values):
            raise PortfolioError("import_invalid_file", 422)

    def _check_cell(self, rowx, colx, value):
        book = self.book
        if not (0 <= rowx < book.max_rows and 0 <= colx < book.max_columns):
            raise PortfolioError("import_too_many_rows", 413)
        if isinstance(value, str) and len(value) > book.max_cell:
            raise PortfolioError("import_invalid_file", 422)
        self._check_dimensions()
        rows = max(self._bounded_rows, rowx + 1)
        columns = max(self._bounded_columns, colx + 1)
        total_rows = book.total_rows + rows - self._bounded_rows
        # Charge the full rectangle even for ragged storage, including sparse
        # gaps. The budget remains charged after a sheet has been unloaded.
        total_cells = book.total_cells + rows * columns - self._bounded_rows * self._bounded_columns
        if total_rows > book.max_rows or total_cells > book.max_cells:
            raise PortfolioError("import_too_many_rows", 413)
        book.total_rows, book.total_cells = total_rows, total_cells
        self._bounded_rows, self._bounded_columns = rows, columns

    def put_cell_ragged(self, rowx, colx, ctype, value, xf_index):
        self._check_cell(rowx, colx, value)
        super().put_cell_ragged(rowx, colx, ctype, value, xf_index)

    def put_cell_unragged(self, rowx, colx, ctype, value, xf_index):
        self._check_cell(rowx, colx, value)
        super().put_cell_unragged(rowx, colx, ctype, value, xf_index)

    def insert_new_BIFF20_xf(self, cell_attr, style=0):
        # BIFF2 synthesizes XFs from cell attributes before calling put_cell.
        self.book._charge_xf()
        return super().insert_new_BIFF20_xf(cell_attr, style)

    def tidy_dimensions(self):
        self._check_dimensions()
        # formatting_info=False skips merged ranges, so xlrd cannot enlarge the
        # rectangle here. Its final padding stays within the charged dimensions.
        super().tidy_dimensions()

    def handle_hlink(self, data):
        """Ignore unused links: xlrd expands their ranges into a per-cell map."""

    def handle_quicktip(self, data):
        """Ignore the tooltips attached to the unused hyperlink records."""

    def handle_obj(self, data):
        """Ignore drawing objects; returning None also clears their pending ID."""

    def handle_txo(self, data):
        """Ignore annotation text; the sheet loop skips its CONTINUE records."""

    def handle_note(self, data, txos):
        """Ignore annotations, including old BIFF's chained NOTE records."""


class BoundedBook(Book):
    def __init__(self, *, max_rows, max_columns, max_cell, max_sheets, max_cells):
        super().__init__()
        self.max_rows = max_rows
        self.max_columns = max_columns
        self.max_cell = max_cell
        self.max_sheets = max_sheets
        self.max_cells = max_cells
        self.total_rows = 0
        self.total_cells = 0
        self._format_count = 0
        self._format_bytes = 0
        self._xf_count = 0
        # initialise_book dynamically installs formatting methods on the book's
        # class on every parse. Instance bindings to distinct private methods
        # survive that step, including concurrent and subsequent imports.
        self.handle_format = self._handle_format
        self.is_date_format_string = self._is_date_format_string
        self.handle_xf = self._handle_xf

    def handle_boundsheet(self, data):
        super().handle_boundsheet(data)
        if self._all_sheets_count > self.max_sheets:
            raise PortfolioError("import_invalid_file", 422)

    def handle_name(self, data):
        # The import reads cell values and cached formula results. It never
        # resolves defined names. xlrd evaluates their formulas during globals
        # parsing, where repeated concatenation can expand tiny input endlessly.
        pass

    def handle_externsheet(self, data):
        # Cached cell results do not resolve external references or names.
        # Leave fragmented CONTINUE records to the globals loop, which skips
        # them individually instead of concatenating the entire metadata table.
        pass

    def _handle_format(self, data, rectype=XL_FORMAT):
        self._format_count += 1
        self._format_bytes += len(data)
        if self._format_count > MAX_FORMATS or self._format_bytes > MAX_FORMAT_BYTES:
            raise PortfolioError("import_invalid_file", 422)
        xlrd_handle_format(self, data, rectype)

    def _charge_xf(self):
        # Each short XF record constructs several formatting objects. Enforce
        # the classic XLS format ceiling before calling the allocating handler.
        self._xf_count += 1
        if self._xf_count > MAX_XFS:
            raise PortfolioError("import_invalid_file", 422)

    def _handle_xf(self, data):
        self._charge_xf()
        xlrd_handle_xf(self, data)

    def _is_date_format_string(self, fmt):
        """xlrd's date heuristic with linear quote/escape/bracket removal."""
        if len(fmt) > self.max_cell:
            raise PortfolioError("import_invalid_file", 422)
        reduced = []
        state = 0
        for character in fmt:
            if state == 0:
                if character == '"':
                    state = 1
                elif character in "\\_*":
                    state = 2
                elif character not in skip_char_dict:
                    reduced.append(character)
            elif state == 1:
                if character == '"':
                    state = 0
            else:
                state = 0
        text = "".join(reduced)
        # Match xlrd's leftmost '[' through next ']' removal. An unmatched '['
        # leaves the suffix intact; each character is searched at most twice.
        parts = []
        position = 0
        while True:
            opening = text.find("[", position)
            closing = text.find("]", opening + 1) if opening >= 0 else -1
            if closing < 0:
                parts.append(text[position:])
                break
            parts.append(text[position:opening])
            position = closing + 1
        text = "".join(parts)
        if text in non_date_formats:
            return False
        date_count = sum(date_char_dict.get(character, 0) for character in text)
        number_count = sum(num_char_dict.get(character, 0) for character in text)
        return date_count > number_count

    def handle_sst(self, data):
        # xlrd's decoder accepts a signed phonetic length and can move backwards
        # over the same string. Decode monotonically and charge before creating
        # each Python string. Rich-text runs and phonetics are unused metadata.
        records = [data]
        while True:
            code, _, continuation = self.get_record_parts_conditional(XL_CONTINUE)
            if code is None:
                break
            records.append(continuation)
        reader = _SSTReader(records)
        total, unique = struct.unpack("<II", reader.read(8))
        if unique > min(total, self.max_cells, reader.remaining // 3, MAX_SST_BYTES // 64):
            raise PortfolioError("import_invalid_file", 422)
        strings = []
        storage = 0
        for _ in range(unique):
            characters, flags = struct.unpack("<HB", reader.read(3))
            if characters > self.max_cell or flags & ~0x0D:
                raise PortfolioError("import_invalid_file", 422)
            storage += 64 + 4 * characters
            if storage > MAX_SST_BYTES:
                raise PortfolioError("import_invalid_file", 422)
            runs = struct.unpack("<H", reader.read(2))[0] if flags & 0x08 else 0
            phonetic = struct.unpack("<I", reader.read(4))[0] if flags & 0x04 else 0
            if runs * 4 + phonetic > reader.remaining:
                raise PortfolioError("import_invalid_file", 422)
            text = reader.text(characters, bool(flags & 1))
            reader.read(runs * 4 + phonetic, discard=True)
            strings.append(text)
        self._sharedstrings = strings
        self._rich_text_runlist_map = {}

    def get_sheet(self, sh_number, update_pos=True):
        if self._resources_released:
            raise XLRDError("Can't load sheets after releasing resources.")
        if not 0 <= sh_number < self.max_sheets:
            raise PortfolioError("import_invalid_file", 422)
        if update_pos:
            self._position = self._sh_abs_posn[sh_number]
        self.getbof(XL_WORKSHEET)
        sheet = BoundedSheet(self, self._position, self._sheet_names[sh_number], sh_number)
        sheet.read(self)
        self._sheet_list[sh_number] = sheet
        return sheet


def open_bounded_xls(data, *, max_rows, max_columns, max_cell, max_sheets, max_cells):
    validate_xls_container(data)
    book = BoundedBook(
        max_rows=max_rows,
        max_columns=max_columns,
        max_cell=max_cell,
        max_sheets=max_sheets,
        max_cells=max_cells,
    )
    start = perf_counter()
    try:
        book.biff2_8_load(
            file_contents=data,
            on_demand=True,
            ragged_rows=True,
            formatting_info=False,
        )
        loaded = perf_counter()
        book.load_time_stage_1 = loaded - start
        version = book.getbof(XL_WORKBOOK_GLOBALS)
        if version not in SUPPORTED_VERSIONS:
            raise XLRDError("Unsupported or undetermined BIFF version")
        book.biff_version = version
        if version <= 40:
            book.on_demand = False
            # This path calls the overridden get_sheet via get_sheets.
            book.fake_globals_get_sheet()
        elif version == 45:
            book.on_demand = False
            # Embedded BIFF4W sheets also call the overridden get_sheet.
            book.parse_globals()
        else:
            book.parse_globals()
            book._sheet_list = [None for _ in book._sheet_names]
        book.nsheets = len(book._sheet_list)
        if book.nsheets > max_sheets:
            raise PortfolioError("import_invalid_file", 422)
        book.load_time_stage_2 = perf_counter() - loaded
    except BaseException:
        book.release_resources()
        raise
    if not book.on_demand:
        book.release_resources()
    return book
