r"""Parse the narrative of a WASDE release's XLS file into one record per paragraph (ADR-0020).

The workbook is Excel 97-2003 (BIFF8), read with xlrd (``docs/upstream/layout.md``). Its
sheet ``WASDE Text`` holds the report's narrative in one column, one paragraph a row, as
the PDF prints it on its first pages: in October 2026 26 rows, row 0 ``WASDE - 676``
followed by a carriage return, row 1 empty, rows 2 to 25 the paragraphs from ``WHEAT:``
to the cotton paragraphs, 16,004 characters. Sheets ``Page 8`` to ``Page 37`` hold the
tables, of which this parser reads one cell, the report month.

- **The rows.** One ``WasdeXlsText`` per row of ``WASDE Text`` whose cell holds text
  other than spaces and line breaks, in sheet order, the text verbatim (the carriage
  return after ``WASDE - 676`` kept); a row without text gives none (25 records in
  October 2026). A text cell holding no character counts as empty, as an empty cell does.
- **The report month.** ``report_month``, on every record, is the text of cell (0, 0) of
  the workbook's first sheet named ``Page N`` where it reads ``<Month> <year>``, as
  printed: ``Page 8`` prints ``October 2026`` there; ``None`` where it holds other text or
  none (``Page 9`` prints the month a row lower, so the rule reads the first page sheet
  only).

A file xlrd cannot open as an XLS raises ``ValidationError``, as does a cell of
``WASDE Text`` that holds anything but text, or text in a column after the first: a
layout the parser does not know. A workbook without the sheet, or whose sheet holds no
text, raises ``NotFoundError`` naming its sheets: it holds no narrative, which the
release's PDF may hold. ESMIS lists other workbooks as the XLS of some releases, revision
tables in 2001 to 2008 (``layout.md``), and the parser does not know which older report
workbooks carry the sheet.
"""

import io
import re
from os import PathLike
from pathlib import Path
from typing import NoReturn

import xlrd
from xippios.core import NotFoundError, ValidationError, XippiosError

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import WasdeXlsText

__all__ = ["MONTH_NAMES", "TEXT_SHEET", "parse_wasde_xls"]

FILE_KIND = "wasde.xls"
"""The file kind, as messages name it."""
TEXT_SHEET = "WASDE Text"
"""The sheet that holds the narrative, as the workbook names it."""
_PAGE_SHEET = re.compile(r"Page \d+")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
"""The month names WASDE prints, in English, written out so that no locale changes them."""
_MONTH = re.compile(rf"(?:{'|'.join(MONTH_NAMES)}) \d{{4}}")
_EMPTY = (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK)


def _refuse(message: str, raw: object) -> NoReturn:
    """Raise the family's ``ValidationError`` for the file, without a chained cause."""
    raise ValidationError(f"{FILE_KIND}: {message}", raw=raw, source=SOURCE) from None


def _report_month(book: xlrd.book.Book) -> str | None:
    """Cell (0, 0) of the first sheet named ``Page N`` where it reads ``<Month> <year>``."""
    name = next((name for name in book.sheet_names() if _PAGE_SHEET.fullmatch(name)), None)
    if name is None:
        return None
    sheet = book.sheet_by_name(name)
    if sheet.nrows == 0 or sheet.ncols == 0:
        return None
    cell = sheet.cell(0, 0)
    text = str(cell.value)
    return text if cell.ctype == xlrd.XL_CELL_TEXT and _MONTH.fullmatch(text) else None


def _rows(path: Path) -> list[WasdeXlsText]:
    """The narrative's records of the workbook at ``path``; ``parse_wasde_xls`` is its door."""
    with xlrd.open_workbook(str(path), logfile=io.StringIO(), on_demand=True) as book:
        sheets = book.sheet_names()
        if TEXT_SHEET not in sheets:
            raise NotFoundError(
                f"{FILE_KIND}: the workbook has no sheet {TEXT_SHEET!r}, which holds the "
                f"narrative; its sheets: {', '.join(sheets) or 'none'}",
                source=SOURCE,
            )
        month = _report_month(book)
        sheet = book.sheet_by_name(TEXT_SHEET)
        records: list[WasdeXlsText] = []
        for row in range(sheet.nrows):
            for column, cell in enumerate(sheet.row(row)):
                if cell.ctype in _EMPTY or cell.value == "":
                    continue
                if cell.ctype != xlrd.XL_CELL_TEXT or column != 0:
                    kind = xlrd.sheet.ctype_text.get(cell.ctype, str(cell.ctype))
                    _refuse(
                        f"sheet {TEXT_SHEET!r}, row {row}, column {column} holds a {kind} "
                        "cell; the narrative is text in the first column "
                        "(docs/upstream/layout.md)",
                        {"sheet": TEXT_SHEET, "row": row, "column": column},
                    )
                text = str(cell.value)
                if text.strip():
                    records.append(
                        WasdeXlsText(sheet=TEXT_SHEET, row=row, text=text, report_month=month)
                    )
        if not records:
            raise NotFoundError(
                f"{FILE_KIND}: the workbook's sheet {TEXT_SHEET!r} holds no text; its "
                f"sheets: {', '.join(sheets)}",
                source=SOURCE,
            )
    return records


def parse_wasde_xls(path: str | PathLike[str]) -> list[WasdeXlsText]:
    """The narrative of a WASDE release's XLS file, one record per paragraph, in sheet order.

    The rows of sheet ``WASDE Text`` that hold text, verbatim, each with the report month
    the first table sheet prints; the rules are this module's docstring.

    Args:
        path: The XLS file as ESMIS serves it, e.g. ``"wasde1026.xls"``.

    Raises:
        NotFoundError: The workbook has no sheet ``WASDE Text``, or the sheet holds no
            text: the file holds no narrative; the message names its sheets.
        ValidationError: The file is no workbook xlrd reads (any error xlrd raises on it,
            its class and text named), or a cell of the sheet holds something other than
            text, or text after the first column; the message names the row and the
            column. An ``OSError``, a file that cannot be opened, passes as raised.
    """
    try:
        return _rows(Path(path))
    except (XippiosError, OSError):
        raise
    except Exception as error:  # xlrd raises more than its own errors on a corrupt file
        _refuse(f"not a workbook xlrd reads: {type(error).__name__}: {error}", str(path))
