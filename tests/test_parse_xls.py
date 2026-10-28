r"""Parser tests on the XLS sample of ``tests/fixtures/files/wasde_xls/`` (ADR-0020).

The sample is the October 2026 release's XLS cut to its sheets ``WASDE Text`` and
``Page 8``, copied cell by cell with xlwt (``tests/fixtures/files/README.md``). The tests
assert the parser's shape and the text as printed, never a size: one record per row that
holds text, in sheet order, verbatim, and the report month of the first table sheet,
each row checked against the sample as xlrd reads it. The refusals and the month rule's
edges are tested on small workbooks written in the test with xlwt, never on a fixture
file.
"""

import io
from collections.abc import Mapping
from pathlib import Path

import pytest
import xlrd
import xlwt
from xippios.core import NotFoundError, ValidationError

from xippios.usda.wasde.models import WasdeXlsText
from xippios.usda.wasde.parse import parse_wasde_xls
from xippios.usda.wasde.parse.wasde_xls import TEXT_SHEET

SAMPLE = Path(__file__).parent / "fixtures" / "files" / "wasde_xls" / "wasde_text_page_8.xls"


def sheet_rows(path: Path) -> list[tuple[int, str]]:
    """The rows of ``WASDE Text`` as xlrd reads them, the parser left out: row and text."""
    with xlrd.open_workbook(str(path), logfile=io.StringIO()) as book:
        sheet = book.sheet_by_name(TEXT_SHEET)
        return [(row, str(sheet.cell_value(row, 0))) for row in range(sheet.nrows)]


def workbook(tmp_path: Path, sheets: Mapping[str, Mapping[tuple[int, int], object]]) -> Path:
    """A small workbook written with xlwt: each sheet's values by row and column."""
    book = xlwt.Workbook()
    for name, cells in sheets.items():
        sheet = book.add_sheet(name)
        for (row, column), value in cells.items():
            sheet.write(row, column, value)
    path = tmp_path / "wasde.xls"
    book.save(str(path))
    return path


def test_the_sample_gives_one_record_per_row_with_text_in_sheet_order() -> None:
    records = parse_wasde_xls(SAMPLE)
    expected = [(row, text) for row, text in sheet_rows(SAMPLE) if text.strip()]
    assert [(record.row, record.text) for record in records] == expected, "verbatim"
    assert len(records) < len(sheet_rows(SAMPLE)), "the empty row gives none"
    for record in records:
        assert (record.sheet, record.report_month) == ("WASDE Text", "October 2026")


def test_the_first_row_is_the_report_number_with_its_carriage_return() -> None:
    first, second = parse_wasde_xls(SAMPLE)[:2]
    assert first == WasdeXlsText(
        sheet="WASDE Text", row=0, text="WASDE - 676\r", report_month="October 2026"
    )
    assert second.row == 2
    assert second.text.startswith("WHEAT: ")
    assert list(WasdeXlsText.model_fields) == list(first.model_dump())


def test_the_paragraphs_run_from_wheat_to_cotton() -> None:
    paragraphs = parse_wasde_xls(SAMPLE)[1:]
    heads = [record.text.split(":", 1)[0] for record in paragraphs if ":" in record.text]
    assert [head for head in heads if head.isupper()] == [
        "WHEAT",
        "COARSE GRAINS",
        "RICE",
        "OILSEEDS",
        "SUGAR",
        "LIVESTOCK, POULTRY, AND DAIRY",
        "COTTON",
    ]


def test_the_month_is_the_first_page_sheets_first_cell(tmp_path: Path) -> None:
    text = {(0, 0): "WASDE - 1\r", (2, 0): "WHEAT: text"}
    path = workbook(
        tmp_path,
        {TEXT_SHEET: text, "Page 9": {(1, 0): "July 2027"}, "Page 8": {(0, 0): "June 2027"}},
    )
    assert {record.report_month for record in parse_wasde_xls(path)} == {None}, (
        "the first page sheet in workbook order, Page 9 here, prints no month in (0, 0)"
    )
    path = workbook(tmp_path, {TEXT_SHEET: text, "Page 8": {(0, 0): "Oct 2027"}})
    assert {record.report_month for record in parse_wasde_xls(path)} == {None}, "no month name"
    path = workbook(tmp_path, {TEXT_SHEET: text})
    assert {record.report_month for record in parse_wasde_xls(path)} == {None}, "no page sheet"
    path = workbook(tmp_path, {TEXT_SHEET: text, "Page 8": {(0, 0): "July 2027"}})
    assert [record.report_month for record in parse_wasde_xls(path)] == ["July 2027"] * 2


def test_a_row_of_spaces_gives_none(tmp_path: Path) -> None:
    path = workbook(tmp_path, {TEXT_SHEET: {(0, 0): "WASDE - 1", (1, 0): "  \n", (2, 0): " a "}})
    assert [(record.row, record.text) for record in parse_wasde_xls(path)] == [
        (0, "WASDE - 1"),
        (2, " a "),
    ]


def test_a_workbook_without_the_sheet_holds_no_narrative(tmp_path: Path) -> None:
    path = workbook(tmp_path, {"Revisions": {(0, 0): "Wheat"}, "Sheet2": {}})
    with pytest.raises(NotFoundError) as caught:
        parse_wasde_xls(path)
    assert str(caught.value) == (
        "wasde.xls: the workbook has no sheet 'WASDE Text', which holds the narrative; its "
        "sheets: Revisions, Sheet2"
    )


def test_a_sheet_without_text_holds_no_narrative(tmp_path: Path) -> None:
    path = workbook(tmp_path, {TEXT_SHEET: {(3, 0): " "}, "Page 8": {}})
    with pytest.raises(NotFoundError, match="sheet 'WASDE Text' holds no text"):
        parse_wasde_xls(path)


@pytest.mark.parametrize(
    ("cells", "where"),
    [
        ({(0, 0): "WASDE - 1", (4, 0): 676.0}, "row 4, column 0 holds a number cell"),
        ({(0, 0): "WASDE - 1", (2, 1): "beside"}, "row 2, column 1 holds a text cell"),
        ({(0, 0): True}, "row 0, column 0 holds a bool cell"),
    ],
)
def test_a_cell_the_layout_does_not_know_is_refused(
    tmp_path: Path, cells: dict[tuple[int, int], object], where: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_wasde_xls(workbook(tmp_path, {TEXT_SHEET: cells}))
    assert str(caught.value).startswith(f"wasde.xls: sheet 'WASDE Text', {where}")


@pytest.mark.parametrize("content", [b"", b"not a workbook", b"%PDF-1.5\n"])
def test_a_file_that_is_no_workbook_is_refused(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "wasde.xls"
    path.write_bytes(content)
    with pytest.raises(ValidationError, match=r"^wasde\.xls: not a workbook xlrd reads"):
        parse_wasde_xls(path)
