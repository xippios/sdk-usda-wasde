"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.

The tasks send through xippios-usda-esmis's tasks, so the fixtures are esmis's answers,
recorded here on 2026-10-28 under esmis's wrapper names (ADR-0021 decision 4): WASDE's
release page 0 (``release_find_by_identifier/wasde_page0.json``), release 796099
(``release_find_by_id/796099.json``), and the download of its XML
(``download_release_file/wasde1026_xml.json``), whose body is the sample
``files/wasde_xml/sr08_sr35_sr36.xml``, so ``get_release`` replays as the parser reads
that sample. Both tools are called end to end through the MCP server; the bulk task is
neither a tool nor a route.
"""

import json
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from pydantic import TypeAdapter
from xippios.core import InvalidRequestError, NotFoundError
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
from xippios.usda.wasde.models import Release
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


def test_a_release_without_an_xml_file_is_refused_naming_its_formats() -> None:
    """Every release before 2010-07-09 has none (layout.md); one is built from page 0's."""
    october = page_0()[0]
    pdf_only = october.model_copy(update={"files": [october.files[0], october.files[1]]})
    with pytest.raises(NotFoundError) as caught:
        tasks._xml_file(tasks._release(pdf_only))
    assert str(caught.value) == (
        "WASDE release 796099 of 2026-10 (2026-10-09) has no XML file; its formats: pdf, "
        "txt. Of the WASDE releases ESMIS lists, the first with an XML file is that of "
        "2010-07-09 (release 95659)."
    )


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
    assert tools == {"usda_wasde_list_releases", "usda_wasde_get_latest_release"}
    assert len(routes) == 2


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
