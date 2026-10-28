"""The packaged lists against the XML samples, and the rules that build them (``_vocabulary``).

The packaged lists in ``reference/`` were read from the whole October 2026 release by
``scripts/refresh_reference.py``; the samples under ``tests/fixtures/files/wasde_xml/``
are verbatim cuts of the same file, pages 8, 9, 11, 12, 13, 16, 24 and 31 to 37. On the
pages the samples hold, the builder gives the packaged tables, regions and attributes,
and every packaged commodity matrix and region is one the samples print. The commodity
rule is checked on records shaped as the whole file's from the packaged list, since the
samples lack pages 14, 15, 17 to 23 and 25 to 30, and no XLS sample exists: the XLS's
block titles are read by the live test only. The refusals are tested on records changed
in the test, never on a fixture file.
"""

import re
from pathlib import Path

import pytest
from xippios.core import PackagedList, ValidationError

from xippios.usda.wasde import _vocabulary as vocabulary
from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import Attribute, Commodity, Region, Table, WasdeXmlCell
from xippios.usda.wasde.params import PACKAGE
from xippios.usda.wasde.parse import parse_wasde_xml

SAMPLES = sorted((Path(__file__).parent / "fixtures" / "files" / "wasde_xml").glob("*.xml"))
CELLS = [cell for path in SAMPLES for cell in parse_wasde_xml(path)]
SAMPLED = {cell.report for cell in CELLS}
"""The pages the samples hold, by ``Name``."""


def packaged[M: (Table, Commodity, Region, Attribute)](name: str, model: type[M]) -> list[M]:
    return PackagedList.load(PACKAGE, name).parse(model, source=SOURCE)


def test_the_samples_hold_these_pages() -> None:
    pages = {8, 9, 11, 12, 13, 16, 24, 31, 32, 34, 35, 36, 37}
    assert {vocabulary.report_name(page) for page in pages} == SAMPLED


def test_the_builder_gives_the_packaged_tables_of_the_sampled_pages() -> None:
    built = [table for path in SAMPLES for table in vocabulary.tables(path)]
    expected = [table for table in packaged("table", Table) if table.report in SAMPLED]
    assert sorted(built, key=lambda table: table.page) == expected


def test_the_packaged_tables_name_the_samples_matrices() -> None:
    for table in packaged("table", Table):
        if table.report in SAMPLED:
            held = [cell.matrix for cell in CELLS if cell.report == table.report]
            assert list(dict.fromkeys(held)) == table.matrices, table.report


def test_the_builder_gives_the_packaged_attributes_of_the_sampled_pages() -> None:
    built = {
        (row.report, row.matrix, row.attribute): row
        for path in SAMPLES
        for row in vocabulary.attributes(parse_wasde_xml(path))
    }
    expected = {
        (row.report, row.matrix, row.attribute): row
        for row in packaged("attribute", Attribute)
        if row.report in SAMPLED
    }
    assert built == expected
    # Within a page, the file's order.
    for report in SAMPLED:
        order = [key for key in built if key[0] == report]
        assert order == [key for key in expected if key[0] == report], report


def test_the_builder_gives_the_packaged_regions_of_the_sampled_pages() -> None:
    built = {row.region: row.reports for row in vocabulary.regions(CELLS)}
    expected = {
        row.region: [report for report in row.reports if report in SAMPLED]
        for row in packaged("region", Region)
        if set(row.reports) & SAMPLED
    }
    assert {region: sorted(reports) for region, reports in built.items()} == expected


def test_every_packaged_region_is_printed_on_its_sampled_pages() -> None:
    printed = {(cell.report, cell.region) for cell in CELLS if cell.region is not None}
    for row in packaged("region", Region):
        for report in set(row.reports) & SAMPLED:
            assert (report, row.region) in printed, (report, row.region)


def test_every_packaged_commodity_matrix_of_a_sampled_page_is_the_samples() -> None:
    held = {(cell.report, cell.matrix): cell.table for cell in CELLS}
    rows = [row for row in packaged("commodity", Commodity) if row.report in SAMPLED]
    assert {row.report for row in rows} == {"sr11", "sr12", "sr13", "sr16", "sr24"}
    for row in rows:
        assert held.get((row.report, row.matrix)) == row.table, (row.report, row.matrix)
    on_pages = {key for key in held if int(key[0][2:]) in vocabulary.COMMODITY_PAGES}
    assert on_pages == {(row.report, row.matrix) for row in rows}, "every matrix, none more"


def whole_file() -> list[WasdeXmlCell]:
    """One record per packaged commodity matrix, shaped as the whole file's records.

    A sample record with the report, matrix and title of each packaged commodity row, in
    the packaged order, the file's: what ``commodities`` reads of the records.
    """
    template = CELLS[0]
    return [
        template.model_copy(update={"report": row.report, "matrix": row.matrix, "table": row.table})
        for row in packaged("commodity", Commodity)
    ]


def titles() -> dict[str, list[str]]:
    """The block titles of pages 12 to 15 as packaged, as ``block_titles`` reads them."""
    found: dict[str, list[str]] = {}
    for row in packaged("commodity", Commodity):
        if int(row.report[2:]) in vocabulary.BLOCK_PAGES:
            found.setdefault(row.report, []).append(row.commodity)
    return found


def test_the_commodity_rule_gives_the_packaged_list() -> None:
    assert vocabulary.commodities(whole_file(), titles()) == packaged("commodity", Commodity)


def test_the_block_titles_of_pages_12_to_15_are_the_xls_headings() -> None:
    assert titles() == {
        "sr12": ["FEED GRAINS", "CORN"],
        "sr13": ["SORGHUM", "BARLEY", "OATS"],
        "sr14": ["TOTAL RICE", "LONG-GRAIN RICE", "MEDIUM & SHORT-GRAIN RICE"],
        "sr15": ["SOYBEANS", "SOYBEAN OIL", "SOYBEAN MEAL"],
    }


@pytest.mark.parametrize(
    ("title", "region", "commodity"),
    [
        ("U.S. Wheat Supply and Use  1/", "United States", "Wheat"),
        ("U.S. Wheat by Class: Supply and Use", "United States", "Wheat"),
        (
            "Mexico Sugar Supply and Use and High Fructose Corn Syrup Consumption 1/",
            "Mexico",
            "Sugar",
        ),
        ("World Coarse Grain Supply and Use  1/  (Cont'd.)", "World", "Coarse Grain"),
        ("World Rice Supply and Use  (Milled Basis)  1/", "World", "Rice"),
        ("World Soybean Meal Supply and Use  1/", "World", "Soybean Meal"),
    ],
)
def test_a_title_gives_its_region_and_commodity(title: str, region: str, commodity: str) -> None:
    records = [
        cell.model_copy(update={"table": title}) if cell.report == "sr17" else cell
        for cell in whole_file()
    ]
    sr17 = [row for row in vocabulary.commodities(records, titles()) if row.report == "sr17"]
    assert [(row.region, row.commodity, row.table) for row in sr17] == [(region, commodity, title)]


def test_a_block_page_with_another_count_of_titles_is_refused() -> None:
    fewer = titles() | {"sr13": ["SORGHUM", "BARLEY"]}
    with pytest.raises(ValidationError) as caught:
        vocabulary.commodities(whole_file(), fewer)
    assert str(caught.value) == (
        "reference lists: sr13: the XLS sheet 'Page 13' prints 2 block titles for the XML's "
        "3 report items ['matrix1', 'matrix2', 'matrix3']; the commodity of the Nth item is "
        "the Nth title, so the counts must match"
    )
    missing = {report: names for report, names in titles().items() if report != "sr15"}
    with pytest.raises(ValidationError, match="sr15: the XLS sheet 'Page 15' prints 0 block"):
        vocabulary.commodities(whole_file(), missing)


def test_a_title_the_rule_cannot_read_is_refused() -> None:
    records = [
        cell.model_copy(update={"table": "U.S. Wheat Outlook"}) if cell.report == "sr11" else cell
        for cell in whole_file()
    ]
    message = "sr11 matrix1: the title 'U.S. Wheat Outlook' does not start with U.S."
    with pytest.raises(ValidationError, match=re.escape(message)):
        vocabulary.commodities(records, titles())


def test_a_page_of_11_to_30_without_values_is_refused() -> None:
    with pytest.raises(ValidationError, match="sr14 has no values"):
        vocabulary.commodities(CELLS, titles())


def test_records_of_two_months_are_refused() -> None:
    november = CELLS[-1].model_copy(update={"report_month": "November 2026"})
    with pytest.raises(ValidationError, match="2 Report_Month values"):
        vocabulary.regions([*CELLS, november])
