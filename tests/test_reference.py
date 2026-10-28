"""The packaged lists against the XML samples, and the rules that build them (``_vocabulary``).

The packaged lists in ``reference/`` were read from the whole October 2026 release by
``scripts/refresh_reference.py``; the samples under ``tests/fixtures/files/wasde_xml/``
are verbatim cuts of the same file, pages 8, 9, 11, 12, 13, 16, 24 and 31 to 37. On the
pages the samples hold, the builder gives the packaged tables, regions and attributes,
and every packaged commodity matrix and region is one the samples print. The commodity
rule is checked on records shaped as the whole file's from the packaged list, since the
samples lack pages 14, 15, 17 to 23, 25 to 30 and 33, and no XLS sample exists: the XLS's
block titles are read by the live test only. The refusals are tested on records changed
in the test, and on small XML texts the test writes to ``tmp_path``, never on a fixture
file.
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


def test_the_packaged_footers_are_the_parsers_by_page() -> None:
    """A page's footers, stated once, are the ones ``parse_wasde_xml`` gives its items."""
    checked = 0
    for table in packaged("table", Table):
        if table.report in SAMPLED:
            given = [cell.sub_report_footer for cell in CELLS if cell.report == table.report]
            stated = [table.sub_report_footer, table.sub_report_footer2, table.sub_report_footer3]
            expected: list[str | None] = [footer for footer in stated if footer is not None]
            expected = expected or [None]
            assert list(dict.fromkeys(given)) == expected, table.report
            checked += 1
    assert checked == len(SAMPLED)


def test_a_reliability_page_states_the_footer_of_its_item() -> None:
    """Pages 35 to 37 carry their footer on an item (layout.md): ``table1``, ``table4``."""
    footers = {table.report: table for table in packaged("table", Table)}
    for report in ("sr35", "sr36", "sr37"):
        assert footers[report].sub_report_footer, report
        assert (footers[report].sub_report_footer2, footers[report].sub_report_footer3) == (
            None,
            None,
        )
    assert footers["sr17"].sub_report_footer is None, "page 17 prints sub_report_footer3"
    assert footers["sr17"].sub_report_footer3


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
    assert {row.report for row in rows} == {"sr11", "sr12", "sr13", "sr16", "sr24", "sr32"}
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


def test_the_commodity_list_reads_the_supply_and_use_pages() -> None:
    """Pages 11 to 30, 32 and 33 (G5; the session, 2026-10-28, rule 7), every item each."""
    rows = packaged("commodity", Commodity)
    assert list(dict.fromkeys(int(row.report[2:]) for row in rows)) == [
        *range(11, 31),
        32,
        33,
    ]
    us = [(row.report, row.matrix, row.commodity) for row in rows if row.report in {"sr32", "sr33"}]
    assert us == [
        ("sr32", "matrix1", "Meats"),
        ("sr33", "matrix1", "Egg"),
        ("sr33", "matrix2", "Milk"),
    ]
    assert {row.region for row in rows if row.report in {"sr32", "sr33"}} == {"United States"}


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


def test_a_supply_and_use_page_without_values_is_refused() -> None:
    with pytest.raises(ValidationError, match="sr14 has no values"):
        vocabulary.commodities(CELLS, titles())


def test_records_of_two_months_are_refused() -> None:
    november = CELLS[-1].model_copy(update={"report_month": "November 2026"})
    with pytest.raises(ValidationError, match="2 Report_Month values"):
        vocabulary.regions([*CELLS, november])


PAGE = (
    'Name="sr12" Report_Month="October 2026" page_title=" WASDE - 676 - 12" '
    'sub_report_title="U.S. Feed Grain and Corn Supply and Use  1/"'
)
"""The attributes a page's ``<Report>`` must carry, as page 12 prints them."""


def one_page(tmp_path: Path, page: str, items: str = "<matrix1 />") -> Path:
    """A small XML text written in the test, one page ``<sr12>``: not a fixture."""
    path = tmp_path / "page.xml"
    text = f'<Report Name="wasde"><sr12><Report {page}>{items}</Report></sr12></Report>'
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>{text}', encoding="utf-8")
    return path


def test_tables_reads_a_page_and_its_items_footer(tmp_path: Path) -> None:
    items = '<table1 /><table4 sub_report_footer="1/ See pages 35 and 36." />'
    (table,) = vocabulary.tables(one_page(tmp_path, PAGE, items))
    assert (table.report, table.page, table.matrices) == ("sr12", 12, ["table1", "table4"])
    assert table.sub_report_footer == "1/ See pages 35 and 36."
    assert (table.sub_report_title2, table.sub_report_subtitle, table.sub_report_footer3) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("page", "items", "message"),
    [
        (PAGE, None, "<sr12> holds no <Report>"),
        (
            PAGE.replace('page_title=" WASDE - 676 - 12" ', ""),
            "<matrix1 />",
            "<sr12>'s <Report> lacks ['page_title']",
        ),
        (
            f'{PAGE} sub_report_title4="A fourth"',
            "<matrix1 />",
            "sr12 carries ['sub_report_title4']; a table names titles, subtitles and footers "
            "1 to 3",
        ),
        (
            f'{PAGE} sub_report_footer5="5/"',
            "<matrix1 />",
            "sr12 carries ['sub_report_footer5']",
        ),
        (PAGE.replace("676 - 12", "676 - "), "<matrix1 />", "sr12: page_title ends in no page"),
        (
            f'{PAGE} sub_report_footer="1/"',
            '<table1 sub_report_footer="2/" />',
            "sr12: footers on its <Report> and on ['table1 sub_report_footer']",
        ),
        (
            PAGE,
            '<table1 sub_report_footer="1/" /><table2 sub_report_footer="2/" />',
            "sr12: footers on ['table1 sub_report_footer', 'table2 sub_report_footer']",
        ),
        (
            PAGE,
            '<table1 sub_report_footer2="1/" />',
            "sr12: footers on ['table1 sub_report_footer2']",
        ),
    ],
)
def test_tables_refuses_a_page_it_cannot_read(
    tmp_path: Path, page: str, items: str | None, message: str
) -> None:
    path = one_page(tmp_path, page, items or "")
    if items is None:  # a page element without its <Report>
        text = path.read_text(encoding="utf-8").replace(f"<Report {page}></Report>", "<x />")
        path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError) as caught:
        vocabulary.tables(path)
    assert str(caught.value).startswith(f"reference lists: {message}")
