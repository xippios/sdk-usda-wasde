"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.

The tasks send through xippios-usda-esmis's tasks, so the fixtures are esmis's answers,
recorded here on 2026-10-28 under esmis's wrapper names (ADR-0021 decision 4): WASDE's
release page 0 (``release_find_by_identifier/wasde_page0.json``), release 796099
(``release_find_by_id/796099.json``), and the download of its XML
(``download_release_file/wasde1026_xml.json``), whose body is the sample
``files/wasde_xml/sr08_sr35_sr36.xml``, so ``get_release`` replays as the parser reads
that sample. The three list tasks answer from the packaged lists in ``reference/`` and
send nothing. Every tool is called end to end through the MCP server; the bulk task is
neither a tool nor a route.
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
from xippios.core import InvalidRequestError, NotFoundError, PackagedList, UpstreamModel
from xippios.core.mcp import tool_name
from xippios.core.testing import (
    ReplayFixture,
    assert_projection,
    assert_time_between,
    load_fixture,
    mcp_call,
    sent_urls,
)
from xippios.usda.esmis.models import Release as EsmisRelease
from xippios.usda.esmis.models import ReleaseFile, ReleaseResults

from xippios.usda.wasde import tasks
from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.http import router
from xippios.usda.wasde.mcp import server
from xippios.usda.wasde.models import Attribute, Commodity, Region, Release, Table
from xippios.usda.wasde.params import PACKAGE, PACKAGED_LISTS
from xippios.usda.wasde.parse import parse_wasde_xml

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "files" / "wasde_xml" / "sr08_sr35_sr36.xml"
ESMIS = "https://esmis.nal.usda.gov"
PAGE_0 = f"{ESMIS}/api/v1/release/findByIdentifier/wasde?page=0"
RELEASE = f"{ESMIS}/api/v1/release/findById/796099"
XML = f"{ESMIS}/sites/default/release-files/796099/wasde1026.xml"
RELEASES = "esmis_api_release_findByIdentifier"
OCTOBER_PRINTED = datetime(2026, 10, 9, 12, 0)
"""The October 2026 release's ``release_datetime`` as printed, its ``+0000`` dropped."""
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
    }
    assert len(routes) == 5


type McpCase = tuple[str, dict[str, Any], list[str], Callable[..., bool]]
"""A tool's task name, its arguments, the URLs it sends, a check of its answer."""

MCP_CASES: list[McpCase] = [
    (
        "list_releases",
        {"since": "2026-01-01"},
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
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("task", "arguments", "urls", "check"), MCP_CASES, ids=[case[0] for case in MCP_CASES]
)
async def test_every_tool_end_to_end(
    replay_fixture: ReplayFixture,
    task: str,
    arguments: dict[str, Any],
    urls: list[str],
    check: Callable[[Any], bool],
) -> None:
    route = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    payload = await mcp_call(server, f"usda_wasde_{task}", arguments)
    assert payload["meta"]["source"] == SOURCE
    assert check(payload), payload["meta"]
    assert sent_urls(route) == urls


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
    ("commodity", tasks.list_commodities, Commodity, 40),
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
