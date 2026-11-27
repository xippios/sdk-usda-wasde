"""Parser tests on the XML samples of ``tests/fixtures/files/wasde_xml/`` (sdk-core ADR-0020).

Each sample is a verbatim cut of the October 2026 release's file that keeps whole pages
(``tests/fixtures/files/README.md``), and the XLS sample the same release's workbook cut to
six sheets. The tests assert the record's shape and the labels the file prints, never a
size: the fields and their readings, where a commodity and a region come from, the fixed
table of the layout against the XLS sample, the footnotes and their texts, the value with
its number, the reliability records and their carried unit, and that every value
attribute of a sample, and nothing else, gives a record. The refusals are tested on small
XML texts written in the test, never on a fixture file.
"""

import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest
from xippios.core import ValidationError

from xippios.usda.wasde.models import WasdeFootnote, WasdeRecord
from xippios.usda.wasde.parse import parse_wasde_xml, read_block_titles
from xippios.usda.wasde.parse.wasde_xml import LAYOUT, label, marks

SAMPLES = Path(__file__).parent / "fixtures" / "files" / "wasde_xml"
XLS_SAMPLE = (
    Path(__file__).parent
    / "fixtures"
    / "files"
    / "wasde_xls"
    / "wasde_text_page_8_page_12_page_13_page_14_page_15.xls"
)
CASES = sorted(path.stem for path in SAMPLES.glob("*.xml"))
STATISTICS = {
    "root_mean_square_error",
    "confidence_interval",
    "average",
    "smallest",
    "largest",
    "below_final",
    "above_final",
}
VALUE_ATTRIBUTE = re.compile(
    r"(?:m\d+_)?cell_value\d+|wb_value|(?:root_mean_square_error|confidence_interval|average"
    r"|smallest|largest|below_final|above_final)\d*"
)
PAGE_OF = {12: "sr12_sr37", 13: "sr13_sr34", 14: "sr14", 15: "sr15"}
"""The sample that holds each of pages 12 to 15."""


def records(case: str, **kwargs: object) -> list[WasdeRecord]:
    return parse_wasde_xml(SAMPLES / f"{case}.xml", **kwargs)  # type: ignore[arg-type]


def titled(case: str, table: str) -> list[WasdeRecord]:
    """The records of the sample whose table reads ``table``."""
    return [record for record in records(case) if record.table_label == table]


def test_the_samples_are_the_nine_cuts() -> None:
    assert CASES == [
        "sr08_sr35_sr36",
        "sr09_sr16",
        "sr11_sr24",
        "sr12_sr37",
        "sr13_sr34",
        "sr14",
        "sr15",
        "sr17",
        "sr31_sr32",
    ]


@pytest.mark.parametrize("case", CASES)
def test_every_value_attribute_and_nothing_else_gives_a_record(case: str) -> None:
    """Fillers, unit rows and empty cells give none: counted from the sample itself."""
    root = ET.parse(SAMPLES / f"{case}.xml").getroot()
    texts = [
        text
        for element in root.iter()
        for name, text in element.attrib.items()
        if VALUE_ATTRIBUTE.fullmatch(name)
    ]
    assert [record.value for record in records(case)] == texts


def test_the_record_holds_no_page_and_no_matrix() -> None:
    """Complete in itself, in the order of sdk-core ADR-0060, decision 7's record."""
    assert list(WasdeRecord.model_fields) == [
        "report_number",
        "report_month",
        "table",
        "table_label",
        "commodity",
        "commodity_label",
        "commodity_source",
        "region",
        "region_label",
        "market_year",
        "market_year_label",
        "market_year_status",
        "forecast_month",
        "attribute",
        "attribute_label",
        "attribute_group",
        "attribute_group_label",
        "statistic",
        "unit",
        "unit_label",
        "value",
        "value_number",
        "footnotes",
    ]


def test_a_world_record_is_complete_in_itself() -> None:
    """Page 24's world rice, its year from the matrix's heading, its region's footnote."""
    first = records("sr11_sr24")[198]
    assert first.model_dump(exclude={"footnotes"}) == {
        "report_number": 676,
        "report_month": "October 2026",
        "table": "World Rice Supply and Use  (Milled Basis)  1/",
        "table_label": "World Rice Supply and Use (Milled Basis)",
        "commodity": "Rice",
        "commodity_label": "Rice",
        "commodity_source": "title",
        "region": "World  3/",
        "region_label": "World",
        "market_year": "2024/25",
        "market_year_label": "2024/25",
        "market_year_status": None,
        "forecast_month": None,
        "attribute": "Beginning\r\nStocks",
        "attribute_label": "Beginning Stocks",
        "attribute_group": None,
        "attribute_group_label": None,
        "statistic": None,
        "unit": "(Million Metric Tons)",
        "unit_label": "(Million Metric Tons)",
        "value": "180.41",
        "value_number": Decimal("180.41"),
    }
    assert first.footnotes == [
        WasdeFootnote(on="table", mark="1/", text="Aggregate of local marketing years."),
        WasdeFootnote(
            on="region",
            mark="3/",
            text="World imports and exports may not balance due to differences in some countries.",
        ),
    ]


def test_the_region_of_pages_8_to_10_is_the_matrix_heading() -> None:
    """``commodity_headerN`` heads each matrix with its region; the rows state none."""
    regions = {
        record.region
        for record in records("sr08_sr35_sr36")
        if record.table_label.startswith("World and U.S.")
    }
    assert regions == {"World", "United States"}
    foreign = [record for record in records("sr09_sr16") if record.region == "Foreign  3/"]
    assert foreign
    assert {record.region_label for record in foreign} == {"Foreign"}
    assert foreign[0].footnotes[-1].on == "region"
    assert foreign[0].footnotes[-1].text == "Total foreign is equal to world minus United States."


@pytest.mark.parametrize(
    ("printed", "year", "status"),
    [
        ("2024/25", "2024/25", None),
        ("2025/26 Est.", "2025/26", "Est."),
        ("2026/27 Proj.", "2026/27", "Proj."),
        ("2025/26 (Est.) ", "2025/26", "Est."),
        ("2026/27 (Proj.) ", "2026/27", "Proj."),
        ("2027 Proj.", "2027", "Proj."),
    ],
)
def test_a_market_year_is_read_with_its_status(printed: str, year: str, status: str | None) -> None:
    found = {
        (record.market_year_label, record.market_year_status)
        for case in CASES
        for record in records(case)
        if record.market_year == printed
    }
    assert found == {(year, status)}


def test_the_year_of_the_world_pages_is_the_matrix_heading() -> None:
    """``region_headerN`` heads each matrix of pages 18 to 30 with its year."""
    rice = titled("sr11_sr24", "World Rice Supply and Use (Milled Basis)")
    assert [record.market_year for record in rice][:: len(rice) // 2] == ["2024/25", "2025/26 Est."]


def test_a_commodity_the_title_names_says_title() -> None:
    wheat = titled("sr11_sr24", "U.S. Wheat Supply and Use")
    assert {(r.commodity, r.commodity_source, r.region) for r in wheat} == {
        ("Wheat", "title", "U.S.")
    }
    by_class = titled("sr11_sr24", "U.S. Wheat by Class: Supply and Use")
    assert {(r.commodity, r.commodity_source) for r in by_class} == {("Wheat", "title")}
    cotton = titled("sr09_sr16", "World and U.S. Supply and Use for Cotton")
    assert {(r.commodity, r.commodity_source) for r in cotton} == {("Cotton", "title")}
    assert {r.region_label for r in cotton} >= {"World", "United States"}, "the rows' regions"
    mexico = titled(
        "sr09_sr16", "Mexico Sugar Supply and Use and High Fructose Corn Syrup Consumption"
    )
    assert {(r.commodity, r.region) for r in mexico} == {("Sugar", "Mexico")}


def test_a_commodity_the_path_states_has_no_source() -> None:
    meats = titled("sr31_sr32", "U.S. Meats Supply and Use")
    assert {r.commodity_source for r in meats} == {None}
    assert "Beef" in {r.commodity for r in meats}
    dairy = [r for r in records("sr13_sr34") if r.table_label == "U.S. Dairy Prices"]
    assert {(r.commodity, r.commodity_source) for r in dairy} == {(None, None)}, "none named"


def test_pages_12_to_15_read_the_xls_block_titles_by_position() -> None:
    titles = read_block_titles(XLS_SAMPLE)
    rice = records("sr14", block_titles=titles)
    assert list(dict.fromkeys((r.commodity, r.commodity_source) for r in rice)) == [
        ("TOTAL RICE", "xls"),
        ("LONG-GRAIN RICE", "xls"),
        ("MEDIUM & SHORT-GRAIN RICE", "xls"),
    ]
    assert {r.region for r in rice} == {"U.S."}, "the title's region"


def test_without_the_xls_pages_12_to_15_read_the_layout() -> None:
    """The literal ``block_titles`` is an input of the test, not an answer from ESMIS."""
    rice = records("sr14")
    assert list(dict.fromkeys((r.commodity, r.commodity_source) for r in rice)) == [
        ("TOTAL RICE", "layout"),
        ("LONG-GRAIN RICE", "layout"),
        ("MEDIUM & SHORT-GRAIN RICE", "layout"),
    ]
    assert records("sr14", block_titles={14: ["ONE", "TWO"]})[0].commodity_source == "layout", (
        "a sheet with another count of titles is not read"
    )


def test_the_fixed_table_is_the_xls_sample_s_block_titles() -> None:
    """sdk-core ADR-0061, decision 12: the table written by hand, held by an offline test."""
    titles = read_block_titles(XLS_SAMPLE)
    printed = {}
    for page, case in PAGE_OF.items():
        (table,) = {record.table_label for record in records(case)} & set(LAYOUT)
        printed[table] = tuple(titles[page])
    assert printed == dict(LAYOUT)
    assert [len(commodities) for commodities in LAYOUT.values()] == [2, 3, 3, 3]


def test_the_xls_block_titles_are_read_in_columns_0_to_4(tmp_path: Path) -> None:
    """The oldest workbooks print a title in columns 1 to 4, beside the market years.

    The workbook is an input of the test, not an answer from ESMIS.
    """
    import xlwt

    book = xlwt.Workbook()
    sheet = book.add_sheet("Page 12")
    sheet.write(0, 0, "October 2010")
    sheet.write(2, 2, "FEED GRAINS")
    sheet.write(2, 3, "2009/10")
    sheet.write(3, 0, "Area Planted")
    sheet.write(3, 3, 101.5)
    sheet.write(9, 4, "CORN")
    sheet.write(9, 5, "2010/11 Proj.")
    path = tmp_path / "wasde.xls"
    book.save(str(path))
    assert read_block_titles(path) == {12: ["FEED GRAINS", "CORN"]}


def test_a_page_of_the_layout_with_another_count_of_tables_is_refused(tmp_path: Path) -> None:
    """The page written here is an input of the test, not an answer from ESMIS."""
    path = tmp_path / "wasde.xml"
    page = (
        '<sr14><Report Name="sr14" Report_Month="October 2026" page_title=" WASDE - 676 - 14" '
        'sub_report_title="U.S. Rice Supply and Use  1/"><matrix1><m market_year1="2026">'
        '<Cell cell_value1="1" /></m></matrix1><matrix2 /></Report></sr14>'
    )
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?><Report Name="wasde">{page}</Report>')
    with pytest.raises(ValidationError, match="holds 2 tables, where the report's layout has 3"):
        parse_wasde_xml(path)


@pytest.mark.parametrize(
    ("text", "read", "found"),
    [
        ("Total /2\r\nDomestic", "Total Domestic", ["/2"]),
        ("        Argentina", "Argentina", []),
        ("World  3/", "World", ["3/"]),
        ("Steers\r\n2/", "Steers", ["2/"]),
        ("IV*", "IV", ["*"]),
        ("Total\r\nUse 3/", "Total Use", ["3/"]),
        ("2024/25", "2024/25", []),
        ("Area Planted (mil. acres)", "Area Planted (mil. acres)", []),
    ],
)
def test_a_label_collapses_spaces_and_leaves_marks_out(
    text: str, read: str, found: list[str]
) -> None:
    """Each text is an input of the test, not an answer from ESMIS."""
    assert label(text) == read
    assert marks(text) == found


def test_a_value_printed_with_a_mark_keeps_its_number_and_the_mark() -> None:
    """Page 17's six marked values (https://github.com/xippios/sdk-usda-wasde/issues/22)."""
    marked = [record for record in records("sr17") if "*" in record.value]
    assert [(record.value, record.value_number) for record in marked] == [
        ("10.45 *", Decimal("10.45")),
        ("10.45 **", Decimal("10.45")),
        ("8.16 *", Decimal("8.16")),
        ("8.16 **", Decimal("8.16")),
        ("776 *", Decimal("776")),
        ("790 **", Decimal("790")),
    ]
    stars = {note.mark: note.text for note in marked[1].footnotes if note.on == "value"}
    assert stars == {"**": marked[1].footnotes[-1].text}
    assert (stars["**"] or "").startswith("October planted area")


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("2,141", Decimal("2141")),
        ("-4", Decimal("-4")),
        ("10.45 *", Decimal("10.45")),
        ("776 **", Decimal("776")),
        ("3/", None),
        ("", None),
        ("filler", None),
    ],
)
def test_value_number_reads_a_number_with_its_marks_left_out(
    tmp_path: Path, text: str, number: Decimal | None
) -> None:
    """The value written here is an input of the test, not an answer from ESMIS."""
    body = f'<m1_year_group market_year1="2026"><Cell cell_value1="{text}" /></m1_year_group>'
    (record,) = parse_wasde_xml(xml_file(tmp_path, body))
    assert (record.value, record.value_number) == (text, number)
    if text == "3/":
        assert [(note.on, note.mark) for note in record.footnotes] == [("value", "3/")]


def test_value_number_serialises_as_a_json_number() -> None:
    first = records("sr08_sr35_sr36")[0]
    assert json.loads(first.model_dump_json())["value_number"] == 2858.26


def test_a_table_note_without_a_mark_stands_first() -> None:
    wheat = titled("sr11_sr24", "U.S. Wheat Supply and Use")[0]
    assert wheat.footnotes[0] == WasdeFootnote(
        on="table", mark=None, text="Note: Totals may not add due to rounding."
    )
    assert wheat.footnotes[1] == WasdeFootnote(
        on="table", mark="1/", text="Marketing year beginning June 1."
    )


def test_the_reliability_rows_give_one_record_per_statistic() -> None:
    reliability = [r for r in records("sr08_sr35_sr36") if r.statistic is not None]
    assert {r.statistic for r in reliability} == STATISTICS
    assert {r.market_year for r in reliability} == {None}
    corn = [r for r in records("sr12_sr37") if r.statistic == "average" and r.commodity == "CORN"]
    assert {r.unit for r in corn} == {"Million Bushels"}


def test_the_us_pages_state_no_unit() -> None:
    assert {r.unit for r in records("sr14")} == {None}
    assert {r.unit for r in titled("sr11_sr24", "U.S. Wheat Supply and Use")} == {None}


PAGE = (
    '<sr99><Report Name="sr99" Report_Month="October 2026" page_title=" WASDE - 676 - 99" '
    'sub_report_title="A table"{titles}><matrix1>{body}</matrix1>{more}</Report></sr99>'
)


def xml_file(tmp_path: Path, body: str, *, titles: str = "", more: str = "") -> Path:
    """The small XML text written here is an input of the test, not an answer from ESMIS."""
    path = tmp_path / "wasde.xml"
    text = PAGE.format(titles=titles, body=body, more=more)
    path.write_text(f'﻿<?xml version="1.0" encoding="utf-8"?><Report Name="wasde">{text}</Report>')
    return path


def test_a_small_text_parses(tmp_path: Path) -> None:
    body = (
        '<m1_year_group market_year1="2026">'
        '<Cell cell_value1="1,5" FormatFiller3="x" /></m1_year_group>'
    )
    (record,) = parse_wasde_xml(xml_file(tmp_path, body))
    assert (record.report_number, record.market_year, record.value) == (676, "2026", "1,5")
    assert (record.commodity, record.commodity_source, record.region) == (None, None, None)


def test_an_unknown_attribute_is_refused_naming_it(tmp_path: Path) -> None:
    body = '<m1_year_group market_year1="2026"><Cell surprise1="7" /></m1_year_group>'
    with pytest.raises(ValidationError) as caught:
        parse_wasde_xml(xml_file(tmp_path, body))
    message = str(caught.value)
    assert message.startswith("wasde.xml: sr99 matrix1: unknown attribute 'surprise1' on <Cell>")
    assert message.endswith("the layout the parser knows (docs/upstream/OBSERVED.md)")
    assert caught.value.raw == {"report": "sr99", "element": "Cell", "attribute": "surprise1"}


def test_a_dimension_met_twice_on_a_path_is_refused(tmp_path: Path) -> None:
    body = (
        '<m1_year_group market_year1="2026"><s1 m1_market_year1="2027">'
        '<Cell cell_value1="1" /></s1></m1_year_group>'
    )
    with pytest.raises(ValidationError, match="sets market_year again with the attribute"):
        parse_wasde_xml(xml_file(tmp_path, body))


def test_a_title_count_no_item_order_maps_is_refused(tmp_path: Path) -> None:
    titles = ' sub_report_title2="B" sub_report_title3="C"'
    with pytest.raises(ValidationError, match="sr99 has 3 titles for 2 report items"):
        parse_wasde_xml(xml_file(tmp_path, "", titles=titles, more="<matrix2 />"))


def test_an_unknown_page_attribute_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="unknown attribute 'chart' on the page's <Report>"):
        parse_wasde_xml(xml_file(tmp_path, "", titles=' chart="1"'))


def test_a_page_title_without_its_numbers_is_refused(tmp_path: Path) -> None:
    """The text written here is an input of the test, not an answer from ESMIS."""
    path = xml_file(tmp_path, "")
    path.write_text(path.read_text().replace(" WASDE - 676 - 99", "Page 99"))
    with pytest.raises(ValidationError, match="names no report and page number"):
        parse_wasde_xml(path)


def test_a_file_that_is_not_well_formed_is_refused(tmp_path: Path) -> None:
    """The cut sample is an input of the test, not an answer from ESMIS."""
    path = tmp_path / "wasde.xml"
    path.write_bytes((SAMPLES / "sr08_sr35_sr36.xml").read_bytes()[:5000])
    with pytest.raises(ValidationError, match=r"^wasde\.xml: not well-formed XML"):
        parse_wasde_xml(path)


def test_another_root_is_refused(tmp_path: Path) -> None:
    """As July 2010's file is, its root in a namespace (``docs/upstream/OBSERVED.md``).

    The root written here is an input of the test, not an answer from ESMIS.
    """
    path = tmp_path / "other.xml"
    path.write_text('<Report Name="other"></Report>')
    with pytest.raises(ValidationError, match='not <Report Name="wasde">'):
        parse_wasde_xml(path)
