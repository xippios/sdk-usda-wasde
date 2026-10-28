"""Parser tests on the XML samples of ``tests/fixtures/files/wasde_xml/`` (ADR-0020).

Each sample is a verbatim cut of the October 2026 release's file that keeps whole pages
(``tests/fixtures/files/README.md``). The tests assert the parser's shape and the labels
the file prints, never a size: the pages and fields present, the title rule, the
reliability records and their carried unit, the number parse, and that every value
attribute of a sample, and nothing else, gives a record. The refusals are tested on
small XML texts written in the test, never on a fixture file.
"""

import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest
from xippios.core import ValidationError

from xippios.usda.wasde.models import WasdeXmlCell
from xippios.usda.wasde.parse import parse_wasde_xml
from xippios.usda.wasde.parse.wasde_xml import _value

SAMPLES = Path(__file__).parent / "fixtures" / "files" / "wasde_xml"
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


def records(case: str) -> list[WasdeXmlCell]:
    return parse_wasde_xml(SAMPLES / f"{case}.xml")


def page(case: str, report: str, matrix: str | None = None) -> list[WasdeXmlCell]:
    return [
        record
        for record in records(case)
        if record.report == report and (matrix is None or record.matrix == matrix)
    ]


def test_the_samples_are_the_six_cuts() -> None:
    assert CASES == [
        "sr08_sr35_sr36",
        "sr09_sr16",
        "sr11_sr24",
        "sr12_sr37",
        "sr13_sr34",
        "sr31_sr32",
    ]


@pytest.mark.parametrize("case", CASES)
def test_a_sample_gives_records_of_its_pages_in_order(case: str) -> None:
    found = records(case)
    reports = list(dict.fromkeys(record.report for record in found))
    assert reports == case.split("_"), "every page kept, in the file's order"
    for record in found:
        assert record.report_month == "October 2026"
        assert record.page_title == f" WASDE - 676 - {int(record.report[2:])}"
        assert record.table
        if record.statistic is None:
            assert record.matrix.startswith("matrix")
            assert record.unit is None, "pages 8 to 34 carry no unit (parse_wasde_xml)"
        else:
            assert record.matrix.startswith("table")
            assert record.statistic in STATISTICS
        assert record.value is None or record.value.is_finite()


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
    assert [record.cell_value for record in records(case)] == texts


def test_the_record_mirrors_the_file() -> None:
    first = records("sr08_sr35_sr36")[0]
    assert first == WasdeXmlCell(
        report="sr08",
        report_month="October 2026",
        page_title=" WASDE - 676 - 8",
        table="World and U.S. Supply and Use for Grains  1/",
        sub_report_subtitle="Million Metric Tons",
        sub_report_footer=first.sub_report_footer,
        matrix="matrix1",
        commodity_header="World",
        region_header=None,
        commodity="Total Grains 4/",
        region=None,
        market_year="2024/25",
        forecast_month="",
        attribute="Output",
        attribute_group=None,
        statistic=None,
        unit=None,
        cell_value="2858.26",
        value=Decimal("2858.26"),
    )
    assert (first.sub_report_footer or "").startswith("1/ Aggregate of local marketing years.")
    assert list(WasdeXmlCell.model_fields) == list(first.model_dump())


def test_labels_keep_line_breaks_spaces_and_footnote_markers() -> None:
    world = page("sr11_sr24", "sr24", "matrix1")[0]
    assert (world.region_header, world.region) == ("2024/25", "World  3/")
    assert world.attribute == "Beginning\r\nStocks"
    corn = page("sr12_sr37", "sr12", "matrix1")
    assert "Area Harvested " in {record.attribute for record in corn}
    assert "    Supply, Total" in {record.attribute for record in corn}


def test_page_11_by_class_takes_each_label_from_its_attribute_not_its_element() -> None:
    """``attribute2`` sits on ``m2_month_group``, ``forecast_month2`` on ``m2_attribute_group``."""
    by_class = page("sr11_sr24", "sr11", "matrix2")
    assert {record.attribute_group for record in by_class} == {
        "Hard Red\r\nWinter",
        "Hard Red\r\nSpring",
        "Soft Red\r\nWinter",
        "White",
        "Durum",
        "Total",
    }
    months = {record.forecast_month for record in by_class if record.forecast_month}
    assert months == {"Sep", "Oct"}
    assert {record.attribute for record in by_class if record.forecast_month in months} == {
        "Ending Stocks, Total"
    }
    assert {record.market_year for record in by_class} == {"2025/26 (Est.) ", "2026/27 (Proj.) "}


@pytest.mark.parametrize(
    ("case", "report", "tables"),
    [
        (
            "sr09_sr16",
            "sr09",
            {
                "matrix1": (
                    "World and U.S. Supply and Use for Grains, Continued  1/",
                    "Million Metric Tons",
                    "1/ Aggregate of local marketing years.",
                ),
                "matrix2": (
                    "World and U.S. Supply and Use for Cotton  1/",
                    "Million 480-lb. Bales",
                    "1/ Marketing year beginning August 1.",
                ),
            },
        ),
        (
            "sr09_sr16",
            "sr16",
            {
                "matrix1": ("U.S. Sugar Supply and Use  1/", None, "1/ Fiscal years beginning"),
                "matrix2": (
                    "Mexico Sugar Supply and Use and High Fructose Corn Syrup Consumption 1/",
                    None,
                    "1/ HFCS consumption by Mexico",
                ),
            },
        ),
        (
            "sr11_sr24",
            "sr11",
            {
                "matrix1": ("U.S. Wheat Supply and Use  1/", None, "Note: Totals may not add"),
                "matrix2": (
                    "U.S. Wheat by Class: Supply and Use",
                    None,
                    "Note: Totals may not add",
                ),
            },
        ),
        (
            "sr31_sr32",
            "sr31",
            {
                "matrix1": (
                    "U.S. Quarterly Animal Product Production  1/",
                    None,
                    "* Projection. 1/ Commercial production",
                ),
                "matrix2": (
                    "U.S. Quarterly Prices for Animal Products",
                    None,
                    "*Projection. 1/ Simple average of months.",
                ),
            },
        ),
        (
            "sr12_sr37",
            "sr37",
            dict.fromkeys(
                ("table1", "table2", "table3", "table4"),
                (
                    "Reliability of United States October Projections  1/",
                    None,
                    "1/ See pages 35 and 36 for record of reliability",
                ),
            ),
        ),
    ],
)
def test_the_nth_item_takes_the_nth_title_subtitle_and_footer(
    case: str, report: str, tables: dict[str, tuple[str, str | None, str]]
) -> None:
    found = {
        record.matrix: (record.table, record.sub_report_subtitle, record.sub_report_footer)
        for record in page(case, report)
    }
    assert set(found) == set(tables)
    for matrix, (table, subtitle, footer) in tables.items():
        assert found[matrix][:2] == (table, subtitle), matrix
        assert (found[matrix][2] or "").startswith(footer), matrix


def test_one_title_goes_to_every_item() -> None:
    grains = page("sr08_sr35_sr36", "sr08")
    assert {(record.matrix, record.table) for record in grains} == {
        ("matrix1", "World and U.S. Supply and Use for Grains  1/"),
        ("matrix2", "World and U.S. Supply and Use for Grains  1/"),
    }


def test_the_reliability_rows_give_one_record_per_statistic() -> None:
    wheat = [
        record
        for record in page("sr08_sr35_sr36", "sr35")
        if (record.commodity, record.attribute, record.region) == ("WHEAT", "Production", "World")
    ]
    assert {record.statistic: record.cell_value for record in wheat} == {
        "root_mean_square_error": "1.6",
        "confidence_interval": "2.8",
        "average": "7.5",
        "smallest": "0.1",
        "largest": "27.8",
        "below_final": "32",
        "above_final": "11",
    }
    assert {record.unit for record in wheat} == {None}, "page 35 prints its unit outside the XML"
    assert {record.matrix for record in wheat} == {"table1"}


def test_page_37_names_its_statistics_without_the_table_index() -> None:
    reliability = page("sr12_sr37", "sr37")
    assert {record.statistic for record in reliability} == STATISTICS
    assert {record.matrix for record in reliability} == {"table1", "table2", "table3", "table4"}


def test_the_reliability_unit_carries_to_the_rows_after_its_label() -> None:
    units = {(record.matrix, record.commodity): record.unit for record in page("sr12_sr37", "sr37")}
    assert units == {
        ("table1", "CORN"): "Million Bushels",
        ("table1", "SORGHUM"): "Million Bushels",
        ("table1", "BARLEY"): "Million Bushels",
        ("table1", "OATS"): "Million Bushels",
        ("table1", "SOYBEAN MEAL"): "Thousand Short Tons",
        ("table1", "SOYBEAN OIL"): "Million Pounds",
        ("table2", "Beef"): None,
        ("table2", "Pork"): None,
        ("table2", "Broilers"): None,
        ("table2", "Turkeys"): None,
        ("table3", "Eggs"): None,
        ("table4", "Milk"): None,
    }
    soybeans_and_cotton = {
        record.commodity: record.unit for record in page("sr08_sr35_sr36", "sr36")
    }
    assert soybeans_and_cotton == {
        "SOYBEANS": "Million Metric Tons",
        "COTTON": "Million 480-Pound Bales",
    }


def test_the_m_prefixed_and_wb_shapes() -> None:
    beef = page("sr31_sr32", "sr31", "matrix1")[0]
    assert (beef.commodity, beef.market_year, beef.forecast_month) == ("Beef", "2025", "IV")
    assert (beef.cell_value, beef.value) == ("6,647", Decimal("6647"))
    meats = page("sr31_sr32", "sr32")
    assert {record.attribute for record in meats} >= {"Beginning\r\nstocks"}
    mexico = page("sr09_sr16", "sr16", "matrix2")[0]
    assert (mexico.market_year, mexico.forecast_month, mexico.attribute) == (
        "2025/26 Est.",
        "Sep",
        "Beginning\r\nStocks",
    )


def test_text_boxes_and_heading_rows_give_no_label() -> None:
    """Page 13's unit text box and page 34's ``Milk Prices 2/`` heading are layout."""
    labelled = records("sr13_sr34")
    assert {record.unit for record in labelled} == {None}
    assert "Million Bushels" not in {record.attribute for record in labelled}
    assert "Milk Prices 2/" not in {record.attribute for record in labelled}


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("2858.26", Decimal("2858.26")),
        ("2,141", Decimal("2141")),
        ("2,405.84", Decimal("2405.84")),
        ("-4", Decimal("-4")),
        ("10.45 *", None),
        ("776 **", None),
        ("3/", None),
        ("---", None),
        ("NA", None),
        ("", None),
        ("NaN", None),
        ("Infinity", None),
    ],
)
def test_value_parses_a_printed_number_and_nothing_else(text: str, value: Decimal | None) -> None:
    assert _value(text) == value


def test_a_negative_and_a_separated_value_from_the_samples() -> None:
    white = [
        record
        for record in page("sr11_sr24", "sr11", "matrix2")
        if record.cell_value.startswith("-")
    ]
    assert {record.value for record in white} == {Decimal("-4"), Decimal("-10")}
    sugar = page("sr09_sr16", "sr16", "matrix1")[0]
    assert (sugar.cell_value, sugar.value) == ("2,141", Decimal("2141"))


def test_value_serialises_as_a_json_number() -> None:
    first = records("sr08_sr35_sr36")[0]
    assert json.loads(first.model_dump_json())["value"] == 2858.26


PAGE = (
    '<sr99><Report Name="sr99" Report_Month="October 2026" page_title=" WASDE - 676 - 99" '
    'sub_report_title="A table"{titles}><matrix1>{body}</matrix1>{more}</Report></sr99>'
)


def xml_file(tmp_path: Path, body: str, *, titles: str = "", more: str = "") -> Path:
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
    assert (record.report, record.market_year, record.cell_value) == ("sr99", "2026", "1,5")


def test_an_unknown_attribute_is_refused_naming_it(tmp_path: Path) -> None:
    body = '<m1_year_group market_year1="2026"><Cell surprise1="7" /></m1_year_group>'
    with pytest.raises(ValidationError) as caught:
        parse_wasde_xml(xml_file(tmp_path, body))
    message = str(caught.value)
    assert message.startswith("wasde.xml: sr99 matrix1: unknown attribute 'surprise1' on <Cell>")
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


def test_a_file_that_is_not_well_formed_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "wasde.xml"
    path.write_bytes((SAMPLES / "sr08_sr35_sr36.xml").read_bytes()[:5000])
    with pytest.raises(ValidationError, match=r"^wasde\.xml: not well-formed XML"):
        parse_wasde_xml(path)


def test_another_root_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.xml"
    path.write_text('<Report Name="other"></Report>')
    with pytest.raises(ValidationError, match='not <Report Name="wasde">'):
        parse_wasde_xml(path)
