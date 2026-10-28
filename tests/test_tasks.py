"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.

The tasks send through xippios-usda-esmis's tasks, so the fixtures are esmis's answers,
recorded here on 2026-10-28 under esmis's wrapper names (ADR-0021 decision 4): WASDE's
release page 0 (``release_find_by_identifier/wasde_page0.json``), release 796099
(``release_find_by_id/796099.json``) and the downloads of its XML and its XLS: two
fixtures of the XML (``download_release_file/wasde1026_xml.json`` and
``wasde1026_xml_sr11_sr24.json``), whose bodies are the samples
``files/wasde_xml/sr08_sr35_sr36.xml`` and ``sr11_sr24.xml``, so ``get_release``,
``get_table`` and ``get_balance_sheet`` replay as the parser reads those samples, and one
of the XLS (``wasde1026_xls.json``), whose body is ``files/wasde_xls/wasde_text_page_8.xls``.
The PDF path of ``read_report_text`` replays release 95659 of 2010-07
(``release_find_by_id/95659.json``) and the download of its PDF, whole
(``download_release_file/wasde-07-09-2010_pdf.json``): that release carries an XLS too, so
the test reads it as one without, its XLS left out of the recorded release, as the tests of
``get_release``'s refusals leave out an XML file. The three list tasks answer from the
packaged lists in ``reference/`` and send nothing. Every tool is called end to end through
the MCP server; the bulk task is neither a tool nor a route.
"""

import json
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.routing import APIRoute
from pydantic import TypeAdapter
from xippios.core import (
    InvalidRequestError,
    NotFoundError,
    PackagedList,
    ResultCap,
    UnknownCode,
    UpstreamModel,
)
from xippios.core.mcp import tool_name
from xippios.core.testing import (
    ReplayFixture,
    assert_projection,
    assert_time_between,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_urls,
)
from xippios.usda.esmis.models import Release as EsmisRelease
from xippios.usda.esmis.models import ReleaseFile, ReleaseResults

from xippios.usda.wasde import tasks
from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.http import router
from xippios.usda.wasde.mcp import server
from xippios.usda.wasde.models import (
    Attribute,
    Commodity,
    Region,
    Release,
    Table,
    WasdeTableValue,
    WasdeXmlCell,
)
from xippios.usda.wasde.params import PACKAGE, PACKAGED_LISTS
from xippios.usda.wasde.parse import parse_wasde_pdf, parse_wasde_xls, parse_wasde_xml

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "files" / "wasde_xml" / "sr08_sr35_sr36.xml"
SR11_SR24 = FIXTURES / "files" / "wasde_xml" / "sr11_sr24.xml"
XLS_SAMPLE = FIXTURES / "files" / "wasde_xls" / "wasde_text_page_8.xls"
PDF_SAMPLE = FIXTURES / "files" / "wasde_pdf" / "wasde-07-09-2010.pdf"
ESMIS = "https://esmis.nal.usda.gov"
PAGE_0 = f"{ESMIS}/api/v1/release/findByIdentifier/wasde?page=0"
RELEASE = f"{ESMIS}/api/v1/release/findById/796099"
RELEASE_2010 = f"{ESMIS}/api/v1/release/findById/95659"
XML = f"{ESMIS}/sites/default/release-files/796099/wasde1026.xml"
XLS = f"{ESMIS}/sites/default/release-files/796099/wasde1026.xls"
FILES_2010 = f"{ESMIS}/sites/default/release-files/3t945q76s/3n203z415"
PDF_2010 = f"{FILES_2010}/8c97kq758/wasde-07-09-2010.pdf"
XLS_2010 = f"{FILES_2010}/jh343s72z/wasde-07-09-2010.xls"
RELEASES = "esmis_api_release_findByIdentifier"
OCTOBER_PRINTED = datetime(2026, 10, 9, 12, 0)
"""The October 2026 release's ``release_datetime`` as printed, its ``+0000`` dropped."""
JULY_2010_PRINTED = datetime(2010, 7, 9, 12, 0)
"""The July 2010 release's ``release_datetime`` as printed, its ``+0000`` dropped."""
PACKAGED_FETCHED = datetime(2026, 10, 28, 16, 26, 51, tzinfo=UTC)
"""The packaged lists' ``fetched``, when the refresh script's XML download was complete."""
FILE_KEYS = {"param", "endpoint", "fetched", "note", "records"}
"""The keys a packaged file may hold (ADR-0022, amendment point 8)."""


def page_0() -> list[EsmisRelease]:
    """ESMIS's releases on the recorded page 0, parsed as esmis parses them."""
    fixture = load_fixture(FIXTURES / "release_find_by_identifier" / "wasde_page0.json")
    body = json.loads(fixture.response.content)
    return TypeAdapter(ReleaseResults).validate_python(body).results


def test_list_releases_re_shapes_esmis_releases(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    since = date(2026, 1, 1)
    before = datetime.now(UTC)
    result = tasks.list_releases(since=since)
    after = datetime.now(UTC)
    assert [release.month for release in result.data] == [
        f"2026-{month:02d}" for month in range(10, 0, -1)
    ]
    assert [release.id for release in result.data][:2] == ["796099", "796054"]
    assert {release.month: release.revision for release in result.data if release.revision} == {
        "2026-06": "v2",
        "2026-05": "v2",
    }
    october = result.data[0]
    assert october.release_datetime == datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    assert october.files == [
        ReleaseFile(
            url=f"{ESMIS}/sites/default/release-files/796099/wasde1026.{kind}",
            name=f"wasde1026.{kind}",
            format=kind,
        )
        for kind in ("pdf", "txt", "xls", "xml")
    ]
    assert result.meta.source == SOURCE
    assert result.meta.endpoint == RELEASES
    assert result.meta.total == 703, "ESMIS's count before the date filter"
    assert result.meta.request == {"since": since}, "until left None is omitted"
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert_time_between(result.meta.retrieved_at, before, after)
    # Page 0's oldest release (2024-09-12) is before since: one request.
    assert sent_urls(route) == [PAGE_0]


def test_a_release_is_a_projection_of_esmis_release() -> None:
    """Every release of page 0: id and time copied, files, revision and month parsed."""
    for upstream in page_0():
        release = tasks._release(upstream)
        assert_projection(
            release,
            upstream,
            files=tasks._files(upstream),
            revision=release.revision,
            month=upstream.release_datetime.strftime("%Y-%m"),
        )
        assert [file.url for file in release.files] == upstream.files


@pytest.mark.parametrize(
    ("since", "until", "revision"),
    [
        (date(2024, 12, 1), date(2024, 12, 31), "v2"),  # wasde1224v2.*
        (date(2024, 11, 1), date(2024, 11, 30), None),  # wasde1124.xml beside latest.pdf
        (date(2025, 4, 1), date(2025, 5, 31), "v2"),  # 2025-05 and 2025-04
        (date(2026, 10, 1), date(2026, 10, 31), None),
    ],
)
def test_revision_is_the_suffix_every_file_carries(
    replay_fixture: ReplayFixture, since: date, until: date, revision: str | None
) -> None:
    replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    result = tasks.list_releases(since=since, until=until)
    assert result.data
    assert {release.revision for release in result.data} == {revision}
    assert result.meta.request == {"since": since, "until": until}


def test_get_latest_release(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    result = tasks.get_latest_release()
    assert (result.data.id, result.data.month, result.data.revision) == ("796099", "2026-10", None)
    assert result.meta.source == SOURCE
    assert result.meta.endpoint == RELEASES
    assert result.meta.vintage == "796099"
    assert (result.meta.published_at, result.meta.published_at_naive) == (OCTOBER_PRINTED, True)
    assert result.meta.request == {}
    assert result.meta.total is None
    assert sent_urls(route) == [PAGE_0]


@pytest.mark.parametrize(("month", "catalog"), [(None, PAGE_0), ("2026-10", PAGE_0)])
def test_get_release_reads_the_xml(
    replay_fixture: ReplayFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    month: str | None,
    catalog: str,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    listed = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    release = replay_fixture("release_find_by_id", "796099")
    download = replay_fixture("download_release_file", "wasde1026_xml")
    before = datetime.now(UTC)
    result = tasks.get_release(month)
    after = datetime.now(UTC)
    assert result.data == parse_wasde_xml(SAMPLE), "the records of the replayed body"
    assert {record.report for record in result.data} == {"sr08", "sr35", "sr36"}
    assert result.meta.source == SOURCE
    assert result.meta.endpoint == "wasde1026.xml", "the file's name as catalogued"
    assert result.meta.vintage == "October 2026", "the file's Report_Month as printed"
    assert (result.meta.published_at, result.meta.published_at_naive) == (OCTOBER_PRINTED, True)
    expected = {"release_id": 796099, "url": XML} | ({"month": month} if month else {})
    assert result.meta.request == expected
    assert result.meta.total is None
    assert_time_between(result.meta.retrieved_at, before, after)
    assert sent_urls(listed) == [catalog]
    assert sent_urls(release) == [RELEASE]
    assert sent_urls(download) == [XML]
    assert list(tmp_path.iterdir()) == [], "the temporary directory is removed"


def test_get_release_of_a_month_without_one_names_the_latest(
    replay_fixture: ReplayFixture,
) -> None:
    """October 2025 has no WASDE (layout.md): the month's list is empty, then the latest."""
    listed = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    download = replay_fixture("download_release_file", "wasde1026_xml")
    with pytest.raises(NotFoundError) as caught:
        tasks.get_release("2025-10")
    assert str(caught.value) == (
        "ESMIS lists no WASDE release in 2025-10; the latest is that of 2026-10 "
        "(release 796099, 2026-10-09)"
    )
    assert sent_urls(listed) == [PAGE_0, PAGE_0]
    assert sent_urls(download) == []


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "Oct 2026", "2026-10-01", "202610"])
def test_get_release_refuses_a_month_not_written_yyyy_mm(
    replay_fixture: ReplayFixture, month: str
) -> None:
    listed = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    with pytest.raises(InvalidRequestError, match="month must be 'YYYY-MM'"):
        tasks.get_release(month)
    assert sent_urls(listed) == [], "refused before anything is sent"


def without_xml(release: EsmisRelease) -> EsmisRelease:
    """A recorded release with its PDF and TXT only, as the releases before 2010-07 are."""
    return release.model_copy(update={"files": release.files[:2]})


def test_a_month_without_an_xml_file_is_refused_naming_its_formats() -> None:
    """Every month before 2010-07 has none (layout.md); built from page 0's releases."""
    october = tasks._release(without_xml(page_0()[0]))
    with pytest.raises(NotFoundError) as caught:
        tasks._with_xml([october], "no WASDE release of 2026-10 has an XML file")
    assert str(caught.value) == (
        "no WASDE release of 2026-10 has an XML file: release 796099 (2026-10-09) has pdf, "
        "txt. Of the WASDE releases ESMIS lists, the first with an XML file is that of "
        "2010-07-09 (release 95659)."
    )


def test_a_month_answers_its_latest_release_with_an_xml_file() -> None:
    """As 2014-01 does, whose later release carries an ASC file only (layout.md).

    Built from page 0's releases, no recording: ESMIS's page 0 lists one release a month.
    """
    september, october = page_0()[1], page_0()[0]
    later_without = [tasks._release(without_xml(october)), tasks._release(september)]
    assert tasks._with_xml(later_without, "no XML in 2026-10").id == "796054"
    both = [tasks._release(october), tasks._release(september)]
    assert tasks._with_xml(both, "no XML in 2026-10").id == "796099", "the latest release time"


SLICE_FIELDS = [
    "report",
    "table",
    "matrix",
    "commodity_header",
    "region_header",
    "commodity",
    "region",
    "market_year",
    "forecast_month",
    "attribute",
    "attribute_group",
    "statistic",
    "unit",
    "cell_value",
    "value",
]
"""The fields a slice's record keeps (Johannes, 2026-10-28, G5 inside PR 5)."""


def values(records: list[WasdeXmlCell]) -> list[WasdeTableValue]:
    """The records as the slices answer them, without their page's labels."""
    return [WasdeTableValue.project(record) for record in records]


def test_a_slice_record_is_the_xml_record_without_its_pages_labels() -> None:
    """Every field copied unchanged; the page's title, subtitle, footer and month left out."""
    assert list(WasdeTableValue.model_fields) == SLICE_FIELDS
    dropped = set(WasdeXmlCell.model_fields) - set(SLICE_FIELDS)
    assert dropped == {"page_title", "sub_report_subtitle", "sub_report_footer", "report_month"}
    assert [name for name in WasdeXmlCell.model_fields if name in SLICE_FIELDS] == SLICE_FIELDS
    for record in parse_wasde_xml(SR11_SR24):
        assert_projection(WasdeTableValue.project(record), record)


def test_the_pages_labels_are_list_tables_s() -> None:
    """What a slice leaves out is stated once per page, as the page's records carry it."""
    tables = {table.report: table for table in tasks.list_tables().data}
    for record in parse_wasde_xml(SR11_SR24):
        table = tables[record.report]
        assert record.report_month == table.report_month
        assert record.table in {table.sub_report_title, table.sub_report_title2}
        assert record.sub_report_subtitle in {table.sub_report_subtitle, None}
        footers = {table.sub_report_footer, table.sub_report_footer2, table.sub_report_footer3}
        assert record.sub_report_footer in footers


def replay_october(replay_fixture: ReplayFixture, download: str) -> list[respx.Route]:
    """Page 0, release 796099 and one of its downloads: the routes, in that order."""
    return [
        replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"]),
        replay_fixture("release_find_by_id", "796099"),
        replay_fixture("download_release_file", download),
    ]


@pytest.mark.parametrize("month", [None, "2026-10"])
def test_get_table_answers_one_page(
    replay_fixture: ReplayFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    month: str | None,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    listed, release, download = replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    before = datetime.now(UTC)
    result = tasks.get_table("sr24", month)
    after = datetime.now(UTC)
    page = [record for record in parse_wasde_xml(SR11_SR24) if record.report == "sr24"]
    assert result.data == values(page), "the page's values of the replayed body, in file order"
    assert result.meta.endpoint == "wasde1026.xml"
    assert result.meta.vintage == "October 2026"
    assert (result.meta.published_at, result.meta.published_at_naive) == (OCTOBER_PRINTED, True)
    expected = {"table": "sr24", "release_id": 796099, "url": XML}
    assert result.meta.request == expected | ({"month": month} if month else {})
    assert_time_between(result.meta.retrieved_at, before, after)
    assert (sent_urls(listed), sent_urls(release), sent_urls(download)) == (
        [PAGE_0],
        [RELEASE],
        [XML],
    )
    assert list(tmp_path.iterdir()) == [], "the temporary directory is removed"


@pytest.mark.parametrize(
    ("table", "first"),
    [
        ("SR12", "sr12 (page 12: U.S. Feed Grain and Corn Supply and Use  1/)"),
        ("12", "sr12 (page 12: U.S. Feed Grain and Corn Supply and Use  1/)?"),
        ("sr7", "sr37 (page 37: Reliability of United States October Projections  1/)"),
    ],
)
def test_get_table_refuses_a_page_list_tables_lacks(
    respx_mock: respx.MockRouter, table: str, first: str
) -> None:
    with pytest.raises(UnknownCode) as caught:
        tasks.get_table(table)
    message = str(caught.value)
    assert message.startswith(
        f"{table!r} is not a table in the packaged table list (fetched 2026-10-28). "
        f"Did you mean {first}"
    )
    assert "'sr' and its two-digit printed number: page 12 is 'sr12'" in message
    assert isinstance(caught.value, InvalidRequestError)
    assert respx_mock.calls.call_count == 0, "refused before anything is sent"


def test_get_table_of_a_page_the_file_lacks(replay_fixture: ReplayFixture) -> None:
    """The replayed body holds pages 11 and 24 only, as a month without a page would."""
    replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    with pytest.raises(NotFoundError) as caught:
        tasks.get_table("sr12")
    assert str(caught.value) == (
        "wasde1026.xml of release 796099 holds no page sr12; its pages: sr11, sr24"
    )


BALANCE_SHEETS: list[tuple[str, str, list[tuple[str, str]], bool]] = [
    ("Wheat", "United States", [("sr11", "matrix1")], False),
    ("Wheat", "Argentina", [("sr18", "matrix1"), ("sr18", "matrix2"), ("sr19", "matrix1")], True),
    ("Wheat", "World", [("sr18", "matrix1"), ("sr18", "matrix2"), ("sr19", "matrix1")], True),
    ("CORN", "United States", [("sr12", "matrix2")], False),
    (
        "Corn",
        "United States",
        [("sr22", "matrix1"), ("sr22", "matrix2"), ("sr23", "matrix1")],
        True,
    ),
    ("Cotton", "United States", [("sr17", "matrix1")], False),
    ("Cotton", "India", [("sr26", "matrix3"), ("sr26", "matrix4"), ("sr27", "matrix2")], True),
    ("Sugar", "United States", [("sr16", "matrix1")], False),
    ("Sugar", "Mexico", [("sr16", "matrix2")], False),
    ("Soybean", "Paraguay", [("sr28", "matrix4"), ("sr28", "matrix5"), ("sr28", "matrix3")], True),
    ("Meats", "United States", [("sr32", "matrix1")], False),
    ("Milk", "United States", [("sr33", "matrix2")], False),
]


@pytest.mark.parametrize(("commodity", "region", "matrices", "sliced"), BALANCE_SHEETS)
def test_a_balance_sheet_is_the_packaged_matrices_of_its_commodity_and_region(
    respx_mock: respx.MockRouter,
    commodity: str,
    region: str,
    matrices: list[tuple[str, str]],
    sliced: bool,
) -> None:
    """A U.S. or Mexico matrix where the list has one, else the world pages by region."""
    found, slices = tasks._balance_sheet(commodity, region)
    assert [(row.report, row.matrix) for row in found] == matrices
    assert slices is sliced
    assert all(tasks.BY_CLASS not in row.table for row in found), "page 11's by-class table"
    assert respx_mock.calls.call_count == 0


def test_the_us_rows_of_a_world_table_answer_the_commodities_without_a_us_matrix() -> None:
    """As the docstring names them: no U.S. matrix carries their name as printed."""
    rows = tasks.list_commodities().data
    world = {row.commodity for row in rows if row.region == "World"}
    national = {row.commodity for row in rows if row.region == "United States"}
    assert sorted(world - national) == [
        "Coarse Grain",
        "Corn",
        "Rice",
        "Soybean",
        "Soybean Meal",
        "Soybean Oil",
    ]
    assert sorted(world & national) == ["Cotton", "Wheat"]


def test_get_balance_sheet_of_a_us_commodity(
    replay_fixture: ReplayFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Page 11's first matrix; its by-class table, the page's second matrix, is left out."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    listed, release, download = replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    result = tasks.get_balance_sheet("Wheat")
    matrix = [
        record
        for record in parse_wasde_xml(SR11_SR24)
        if (record.report, record.matrix) == ("sr11", "matrix1")
    ]
    assert result.data == values(matrix)
    assert {record.table for record in result.data} == {"U.S. Wheat Supply and Use  1/"}
    assert result.meta.endpoint == "wasde1026.xml"
    assert result.meta.vintage == "October 2026"
    assert result.meta.request == {
        "commodity": "Wheat",
        "region": "United States",
        "release_id": 796099,
        "url": XML,
    }
    assert (sent_urls(listed), sent_urls(release), sent_urls(download)) == (
        [PAGE_0],
        [RELEASE],
        [XML],
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("region", "printed"),
    [
        ("Thailand", {"        Thailand"}),
        ("World", {"World  3/"}),
        ("United States", {"United States"}),
        ("European Union", {"        European Union  6/"}),
        ("World Less China", {"    World Less China"}),
    ],
)
def test_get_balance_sheet_of_a_world_commodity_by_region(
    replay_fixture: ReplayFixture, region: str, printed: set[str]
) -> None:
    """The world rice rows of the region; the replayed body holds page 24, not page 25."""
    replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    result = tasks.get_balance_sheet("Rice", region, "2026-10")
    rows = [
        record
        for record in parse_wasde_xml(SR11_SR24)
        if record.report == "sr24" and tasks._bare(record.region) == region
    ]
    assert result.data == values(rows)
    assert {record.region for record in result.data} == printed, "the region as printed"
    assert result.meta.request == {
        "commodity": "Rice",
        "region": region,
        "month": "2026-10",
        "release_id": 796099,
        "url": XML,
    }


@pytest.mark.parametrize(
    ("printed", "bare"),
    [
        ("        European Union  5/", "European Union"),
        ("World  3/", "World"),
        ("    World Less China", "World Less China"),
        ("        Southeast Asia 5/", "Southeast Asia"),
        ("        N. Afr & Mideast  7/", "N. Afr & Mideast"),
        ("U.S.", "U.S."),
        (None, None),
    ],
)
def test_a_region_is_matched_without_its_indent_and_footnote_marker(
    printed: str | None, bare: str | None
) -> None:
    assert tasks._bare(printed) == bare


@pytest.mark.parametrize(
    ("commodity", "region", "message"),
    [
        (
            "corn",
            "United States",
            "'corn' is not a commodity in the packaged commodity list (fetched 2026-10-28). "
            "Did you mean CORN (United States sr12), Corn (World sr22, World sr23), ",
        ),
        (
            "Wheat",
            "argentina",
            "'argentina' is not a region in the packaged region list (fetched 2026-10-28). "
            "Did you mean Argentina (rows of sr18, sr19)?",
        ),
        (
            "CORN",
            "World",
            "'World' is not a region in the packaged region list (fetched 2026-10-28). "
            "'CORN' is printed for United States.",
        ),
        (
            "Wheat",
            "united states",
            "'united states' is not a region in the packaged region list (fetched 2026-10-28). "
            "Did you mean United States (sr11 matrix1)? A region of 'Wheat' is 'United "
            "States' or 'Mexico' where it has a U.S. or Mexico matrix, else one its world "
            "pages print",
        ),
        (
            "Sugar",
            "Mexco",
            "'Mexco' is not a region in the packaged region list (fetched 2026-10-28). "
            "Did you mean Mexico (sr16 matrix2)?",
        ),
    ],
)
def test_get_balance_sheet_refuses_a_near_miss_naming_the_closest(
    respx_mock: respx.MockRouter, commodity: str, region: str, message: str
) -> None:
    with pytest.raises(UnknownCode) as caught:
        tasks.get_balance_sheet(commodity, region)
    assert str(caught.value).startswith(message)
    assert respx_mock.calls.call_count == 0, "refused before anything is sent"


def test_a_balance_sheet_the_file_lacks_is_not_found(replay_fixture: ReplayFixture) -> None:
    """The replayed body holds pages 11 and 24, not the world corn pages 22 and 23."""
    replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    with pytest.raises(NotFoundError) as caught:
        tasks.get_balance_sheet("Corn", "Argentina")
    assert str(caught.value) == (
        "wasde1026.xml of release 796099 holds no record of 'Corn' for 'Argentina' in sr22 "
        "matrix1 'World Corn Supply and Use  1/'; sr22 matrix2 'World Corn Supply and Use  "
        "1/'; sr23 matrix1 \"World Corn Supply and Use  1/  (Cont'd.)\", as the packaged list "
        "read them from October 2026; get_table answers a page as that month prints it"
    )


@pytest.mark.parametrize("month", [None, "2026-10"])
def test_read_report_text_reads_the_xls_sheet(
    replay_fixture: ReplayFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    month: str | None,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    listed, release, download = replay_october(replay_fixture, "wasde1026_xls")
    before = datetime.now(UTC)
    result = tasks.read_report_text(month)
    after = datetime.now(UTC)
    assert result.data == [row.text for row in parse_wasde_xls(XLS_SAMPLE)]
    assert result.data[0] == "WASDE - 676\r"
    assert result.meta.endpoint == "wasde1026.xls", "the file read"
    assert result.meta.vintage == "October 2026", "the month Page 8 prints"
    assert (result.meta.published_at, result.meta.published_at_naive) == (OCTOBER_PRINTED, True)
    expected = {"release_id": 796099, "url": XLS} | ({"month": month} if month else {})
    assert result.meta.request == expected
    assert_time_between(result.meta.retrieved_at, before, after)
    assert (sent_urls(listed), sent_urls(release), sent_urls(download)) == (
        [PAGE_0],
        [RELEASE],
        [XLS],
    )
    assert list(tmp_path.iterdir()) == []


def july_2010() -> EsmisRelease:
    """Release 95659, 2010-07, as recorded: TXT, XML, PDF and XLS."""
    fixture = load_fixture(FIXTURES / "release_find_by_id" / "95659.json")
    body = json.loads(fixture.response.content)
    (release,) = TypeAdapter(ReleaseResults).validate_python(body).results
    return release


def leaving_out(release: EsmisRelease, format: str) -> Release:
    """The recorded release with its files of ``format`` left out, re-shaped."""
    files = [url for url in release.files if not url.endswith(f".{format}")]
    return tasks._release(release.model_copy(update={"files": files}))


@pytest.mark.anyio
async def test_a_release_without_an_xls_is_read_from_its_pdf(
    replay_fixture: ReplayFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every release before 2010-07 carries none; release 95659 read as one of them."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    release = replay_fixture("release_find_by_id", "95659")
    download = replay_fixture("download_release_file", "wasde-07-09-2010_pdf")
    july = leaving_out(july_2010(), "xls")
    assert tasks._carrying([july], ("xls", "pdf"), "no XLS or PDF").id == "95659"
    result = await tasks._narrative(july, {"month": "2010-07"})
    assert result.data == [page.text for page in parse_wasde_pdf(PDF_SAMPLE)]
    assert len(result.data) == 5, "pages 1 to 5, the narrative of July 2010"
    assert result.meta.endpoint == "wasde-07-09-2010.pdf"
    assert result.meta.vintage == "95659", "the PDF prints a date: the ESMIS release id"
    assert (result.meta.published_at, result.meta.published_at_naive) == (JULY_2010_PRINTED, True)
    assert result.meta.request == {"month": "2010-07", "release_id": 95659, "url": PDF_2010}
    assert (sent_urls(release), sent_urls(download)) == ([RELEASE_2010], [PDF_2010])
    assert list(tmp_path.iterdir()) == []


def no_narrative(path: Path) -> list[Any]:
    """``parse_wasde_xls`` on a workbook without the sheet, as its own refusal reads."""
    raise NotFoundError(
        "wasde.xls: the workbook has no sheet 'WASDE Text', which holds the narrative; its "
        "sheets: Revisions",
        source=SOURCE,
    )


@pytest.mark.anyio
async def test_an_xls_without_the_narrative_gives_way_to_the_pdf(
    replay_fixture: ReplayFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The XLS is downloaded and read first; the recorded XLS answer is served at its URL."""
    monkeypatch.setattr(tasks, "parse_wasde_xls", no_narrative)
    release = replay_fixture("release_find_by_id", "95659")
    xls = replay_fixture("download_release_file", "wasde1026_xls", url=XLS_2010)
    pdf = replay_fixture("download_release_file", "wasde-07-09-2010_pdf")
    result = await tasks._narrative(tasks._release(july_2010()), {})
    assert result.meta.endpoint == "wasde-07-09-2010.pdf"
    assert result.data == [page.text for page in parse_wasde_pdf(PDF_SAMPLE)]
    assert sent_urls(release) == [RELEASE_2010, RELEASE_2010], "one per download"
    assert (sent_urls(xls), sent_urls(pdf)) == ([XLS_2010], [PDF_2010])


@pytest.mark.anyio
async def test_an_xls_without_the_narrative_and_no_pdf_is_not_found(
    replay_fixture: ReplayFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "parse_wasde_xls", no_narrative)
    replay_fixture("release_find_by_id", "95659")
    replay_fixture("download_release_file", "wasde1026_xls", url=XLS_2010)
    pdf = replay_fixture("download_release_file", "wasde-07-09-2010_pdf")
    with pytest.raises(NotFoundError) as caught:
        await tasks._narrative(leaving_out(july_2010(), "pdf"), {})
    assert str(caught.value) == (
        "wasde-07-09-2010.xls of release 95659 holds no narrative, and the release has no PDF "
        "file (its formats: txt, xml, xls): wasde.xls: the workbook has no sheet 'WASDE "
        "Text', which holds the narrative; its sheets: Revisions"
    )
    assert sent_urls(pdf) == []


def test_a_month_without_an_xls_or_a_pdf_is_refused_naming_its_formats() -> None:
    """As 1995 to 1997 are, TXT only (layout.md); built from page 0's releases."""
    october = page_0()[0]
    txt = october.model_copy(
        update={"files": [url for url in october.files if url.endswith(".txt")]}
    )
    with pytest.raises(NotFoundError) as caught:
        tasks._carrying(
            [tasks._release(txt)], ("xls", "pdf"), tasks._lacking("1996-05", "XLS or PDF file")
        )
    assert str(caught.value) == (
        "no WASDE release of 1996-05 has an XLS or PDF file: release 796099 (2026-10-09) has txt."
    )
    assert tasks._lacking(None, "XML file") == "the latest WASDE release has no XML file"


def test_the_slices_have_caps_of_their_own() -> None:
    """Each note says how to see the rest (Johannes, 2026-10-28, G5 inside PR 5).

    Every other tool keeps the default; none of them is cut but ``list_releases`` called
    without ``since``, whose filters the default note's narrowing names.
    """
    assert dict(tasks.MCP_CAPS) == {
        "get_table": ResultCap(
            max_rows=400,
            max_bytes=131_072,
            note="call get_balance_sheet for one commodity's matrix, or one region's rows of a "
            "world page (list_commodities, list_regions); Python callers get the whole page",
        ),
        "get_balance_sheet": ResultCap(
            max_rows=300,
            max_bytes=131_072,
            note="on the world pages a region gives one region's rows (list_regions); Python "
            "callers get the whole matrix",
        ),
    }


@pytest.mark.anyio
async def test_the_bulk_task_is_no_tool_and_no_route() -> None:
    bulk = tasks.BULK_TASKS
    assert bulk == {"get_release"}
    tools = {tool.name for tool in await server.list_tools()}
    routes = {route.path for route in router.routes if isinstance(route, APIRoute)}
    for name in tasks.__all__:
        served = name not in bulk
        assert (tool_name(SOURCE, getattr(tasks, name)) in tools) is served, name
        assert (f"/{SOURCE}/{name}" in routes) is served, name
    assert tools == {
        "usda_wasde_list_releases",
        "usda_wasde_get_latest_release",
        "usda_wasde_list_tables",
        "usda_wasde_list_commodities",
        "usda_wasde_list_regions",
        "usda_wasde_get_table",
        "usda_wasde_get_balance_sheet",
        "usda_wasde_read_report_text",
    }
    assert len(routes) == 8


type McpCase = tuple[str, dict[str, Any], list[str], list[str], Callable[..., bool]]
"""A tool's task name, its arguments, the download fixture it replays beside page 0 and
release 796099 (none, or one), the URLs it sends to page 0, a check of its answer."""

SR24 = values([record for record in parse_wasde_xml(SR11_SR24) if record.report == "sr24"])
"""Page 24's values in the replayed body, world rice."""
SR11 = values([record for record in parse_wasde_xml(SR11_SR24) if record.report == "sr11"])
"""Page 11's values in the replayed body, U.S. wheat and wheat by class."""

MCP_CASES: list[McpCase] = [
    (
        "list_releases",
        {"since": "2026-01-01"},
        [],
        [PAGE_0],
        lambda payload: (
            [release["month"] for release in payload["data"]][:2] == ["2026-10", "2026-09"]
            and len(payload["data"]) == 10
            and payload["meta"]["total"] == 703
            and payload["meta"]["request"] == {"since": "2026-01-01"}
        ),
    ),
    (
        "get_latest_release",
        {},
        [],
        [PAGE_0],
        lambda payload: (
            payload["data"]["id"] == payload["meta"]["vintage"] == "796099"
            and payload["data"]["files"][3]["name"] == "wasde1026.xml"
            and payload["meta"]["published_at"] == "2026-10-09T12:00:00"
            and payload["meta"]["published_at_naive"] is True
        ),
    ),
    (
        "list_tables",
        {"search": "wheat"},
        [],
        [],
        lambda payload: (
            [table["report"] for table in payload["data"]] == ["sr11", "sr18", "sr19"]
            and payload["meta"]["vintage"] == "October 2026"
            and payload["meta"]["endpoint"] == "wasde1026.xml"
            and payload["meta"]["retrieved_at"] == "2026-10-28T16:26:51Z"
            and payload["meta"]["request"] == {"search": "wheat"}
        ),
    ),
    (
        "list_commodities",
        {"search": "sr12"},
        [],
        [],
        lambda payload: (
            [row["commodity"] for row in payload["data"]] == ["FEED GRAINS", "CORN"]
            and [row["matrix"] for row in payload["data"]] == ["matrix1", "matrix2"]
            and payload["meta"]["vintage"] == "October 2026"
        ),
    ),
    (
        "list_regions",
        {},
        [],
        [],
        lambda payload: (
            len(payload["data"]) == 70
            and payload["data"][0]
            == {
                "region": "World",
                "reports": ["sr09", "sr26", "sr27", "sr35", "sr36"],
                "report_month": "October 2026",
            }
            and "note" not in payload
        ),
    ),
    (
        "get_table",
        {"table": "sr24"},
        ["wasde1026_xml_sr11_sr24"],
        [PAGE_0],
        lambda payload: (
            payload["data"] == [record.model_dump(mode="json") for record in SR24]
            and list(payload["data"][0]) == SLICE_FIELDS
            and "note" not in payload
            and payload["meta"]["vintage"] == "October 2026"
            and payload["meta"]["request"] == {"table": "sr24", "release_id": 796099, "url": XML}
        ),
    ),
    (
        "get_balance_sheet",
        {"commodity": "Rice", "region": "Thailand"},
        ["wasde1026_xml_sr11_sr24"],
        [PAGE_0],
        lambda payload: (
            {row["region"] for row in payload["data"]} == {"        Thailand"}
            and {row["report"] for row in payload["data"]} == {"sr24"}
            and list(payload["data"][0]) == SLICE_FIELDS
            and "note" not in payload
            and payload["meta"]["endpoint"] == "wasde1026.xml"
            and payload["meta"]["request"]
            == {"commodity": "Rice", "region": "Thailand", "release_id": 796099, "url": XML}
        ),
    ),
    (
        "read_report_text",
        {},
        ["wasde1026_xls"],
        [PAGE_0],
        lambda payload: (
            payload["data"] == [row.text for row in parse_wasde_xls(XLS_SAMPLE)]
            and payload["data"][0] == "WASDE - 676\r"
            and "note" not in payload
            and payload["meta"]["endpoint"] == "wasde1026.xls"
            and payload["meta"]["vintage"] == "October 2026"
            and payload["meta"]["published_at"] == "2026-10-09T12:00:00"
        ),
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("task", "arguments", "downloads", "urls", "check"),
    MCP_CASES,
    ids=[case[0] for case in MCP_CASES],
)
async def test_every_tool_end_to_end(
    replay_fixture: ReplayFixture,
    task: str,
    arguments: dict[str, Any],
    downloads: list[str],
    urls: list[str],
    check: Callable[[Any], bool],
) -> None:
    route = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    for download in downloads:
        replay_fixture("release_find_by_id", "796099")
        replay_fixture("download_release_file", download)
    payload = await mcp_call(server, f"usda_wasde_{task}", arguments)
    assert payload["meta"]["source"] == SOURCE
    assert check(payload), payload["meta"]
    assert sent_urls(route) == urls


@pytest.mark.anyio
async def test_get_table_answers_a_page_within_its_cap_whole(
    replay_fixture: ReplayFixture,
) -> None:
    """Page 11, U.S. wheat and wheat by class, fits 400 rows and 128 KB."""
    replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    payload = await mcp_call(server, "usda_wasde_get_table", {"table": "sr11"})
    assert "note" not in payload
    assert payload["data"] == [record.model_dump(mode="json") for record in SR11]


@pytest.mark.anyio
async def test_a_refusal_reaches_the_agent_as_text(respx_mock: respx.MockRouter) -> None:
    text = await mcp_call_text(server, "usda_wasde_get_balance_sheet", {"commodity": "corn"})
    assert text.startswith("error: UnknownCode: 'corn' is not a commodity")
    assert respx_mock.calls.call_count == 0


def test_every_task_is_tested_through_the_mcp_server_or_is_bulk() -> None:
    assert {case[0] for case in MCP_CASES} | tasks.BULK_TASKS == set(tasks.__all__)


def test_the_package_re_exports_the_tasks() -> None:
    import xippios.usda.wasde as package

    for name in tasks.__all__:
        assert getattr(package, name) is getattr(tasks, name)


def test_release_keeps_the_time_as_printed() -> None:
    """``release_datetime`` stays aware at ``+00:00``, as ESMIS prints it; never converted."""
    release = tasks._release(page_0()[0])
    assert isinstance(release, Release)
    assert release.release_datetime.utcoffset() is not None
    assert release.model_dump(mode="json")["release_datetime"] == "2026-10-09T12:00:00Z"


type Packaged = tuple[str, Callable[..., Any], type[UpstreamModel], int]
"""A list task, the packaged list it answers from, its record model and its row count."""

PACKAGED: list[Packaged] = [
    ("table", tasks.list_tables, Table, 30),
    ("commodity", tasks.list_commodities, Commodity, 43),
    ("region", tasks.list_regions, Region, 70),
]


def packaged_file(name: str) -> dict[str, Any]:
    """``reference/<name>.json`` as written, read as JSON, not through ``PackagedList``."""
    text = resources.files(PACKAGE).joinpath("reference", f"{name}.json").read_text("utf-8")
    payload: dict[str, Any] = json.loads(text)
    return payload


@pytest.mark.parametrize(("name", "task", "model", "rows"), PACKAGED, ids=[p[0] for p in PACKAGED])
def test_a_list_task_answers_its_packaged_list_without_a_request(
    respx_mock: respx.MockRouter,
    name: str,
    task: Callable[..., Any],
    model: type[UpstreamModel],
    rows: int,
) -> None:
    packaged = PackagedList.load(PACKAGE, name)
    result = task()
    assert len(result.data) == len(packaged.records) == rows, "the counts the docstring names"
    assert result.data == packaged.parse(model, source=SOURCE), "the file's order"
    assert result.meta.source == SOURCE
    assert result.meta.endpoint == "wasde1026.xml", "the file the list came from"
    assert result.meta.retrieved_at == packaged.fetched == PACKAGED_FETCHED
    assert result.meta.vintage == "October 2026", "the release's Report_Month"
    assert result.meta.request == {}, "search left None is omitted"
    assert (result.meta.published_at, result.meta.total) == (None, None)
    assert not result.meta.published_at_naive
    assert respx_mock.calls.call_count == 0


def key(row: Any) -> str:
    """What names a row in the search cases: a table's report, a commodity, a region text."""
    if isinstance(row, Table):
        return row.report
    if isinstance(row, Commodity):
        return row.commodity
    assert isinstance(row, Region)
    return row.region


SEARCHES: list[tuple[Callable[..., Any], str, list[str]]] = [
    (tasks.list_tables, "wheat", ["sr11", "sr18", "sr19"]),
    (tasks.list_tables, "RELIABILITY", ["sr35", "sr36", "sr37"]),
    (tasks.list_tables, "matrix6", ["sr29", "sr30"]),
    (tasks.list_tables, "Million 480-lb", ["sr09"]),
    (tasks.list_commodities, "sr13", ["SORGHUM", "BARLEY", "OATS"]),
    (tasks.list_commodities, "mexico", ["Sugar"]),
    (tasks.list_commodities, "sr33", ["Egg", "Milk"]),
    (tasks.list_commodities, "grain rice", ["LONG-GRAIN RICE", "MEDIUM & SHORT-GRAIN RICE"]),
    (
        tasks.list_regions,
        "china",
        ["    World Less China", "        China", "       China", "    China"],
    ),
    (tasks.list_regions, "u.s.", ["U.S."]),
]


@pytest.mark.parametrize(("task", "search", "keys"), SEARCHES)
def test_search_keeps_the_rows_where_the_text_occurs_in_a_field(
    respx_mock: respx.MockRouter, task: Callable[..., Any], search: str, keys: list[str]
) -> None:
    result = task(search=search)
    assert [key(row) for row in result.data] == keys
    assert result.meta.request == {"search": search}
    assert result.meta.vintage == "October 2026"
    assert respx_mock.calls.call_count == 0


def test_search_matches_each_field_on_its_own() -> None:
    """A text spanning two fields matches neither (core's ``matches``)."""
    assert tasks.list_commodities(search="CORN United States").data == []
    assert len(tasks.list_regions(search="sr24").data) == 23, "a page among the reports"
    assert tasks.list_tables(search="12").data[0].report == "sr12", "the page number as text"


def test_the_packaged_files_hold_the_four_keys_and_a_note() -> None:
    reference = Path(tasks.__file__).parent / "reference"
    assert sorted(path.stem for path in reference.glob("*.json")) == sorted(PACKAGED_LISTS)
    models: dict[str, type[UpstreamModel]] = {
        "table": Table,
        "commodity": Commodity,
        "region": Region,
        "attribute": Attribute,
    }
    for name in PACKAGED_LISTS:
        raw = packaged_file(name)
        assert set(raw) == FILE_KEYS, name
        packaged = PackagedList.load(PACKAGE, name)
        assert (packaged.param, packaged.endpoint) == (name, "wasde1026.xml"), "named by param"
        assert packaged.fetched == PACKAGED_FETCHED
        assert packaged.note is not None
        assert "ESMIS release 796099" in packaged.note
        assert "Report_Month 'October 2026'" in packaged.note
        model = models[name]
        for row, record in zip(packaged.parse(model, source=SOURCE), raw["records"], strict=True):
            assert list(record) == list(model.model_fields), "every field, null included"
            assert row.dump_upstream() == record
        assert {record["report_month"] for record in raw["records"]} == {"October 2026"}
    assert "wasde1026.xls" in (PackagedList.load(PACKAGE, "commodity").note or "")
