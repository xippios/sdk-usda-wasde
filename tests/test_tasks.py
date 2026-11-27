"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.

The tasks send through xippios-usda-esmis's tasks, so the fixtures are esmis's answers,
recorded here under esmis's wrapper names (sdk-core ADR-0021 decision 4): WASDE's release
page 0 (``release_find_by_identifier/wasde_page0.json``, 2026-10-28), release 796099
(``release_find_by_id/796099.json``) and the downloads of its XML and its XLS. Three
fixtures of the XML, whose bodies are samples of whole pages
(``download_release_file/wasde1026_xml.json``, ``files/wasde_xml/sr08_sr35_sr36.xml``;
``wasde1026_xml_sr11_sr24.json``, ``sr11_sr24.xml``; ``wasde1026_xml_sr14.json``,
``sr14.xml``, cut on 2026-11-27), so a task replays as the parser reads that sample, and
one of the XLS (``wasde1026_xls.json``), whose body is the six-sheet sample
``files/wasde_xls/wasde_text_page_8_page_12_page_13_page_14_page_15.xls``. The PDF path of
``get_report_text`` replays release 95659 of 2010-07 (``release_find_by_id/95659.json``)
and the download of its PDF, whole (``download_release_file/wasde-07-09-2010_pdf.json``).
Every tool is called end to end through the MCP server.
"""

import inspect
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from xippios.core import InvalidRequestError, NotFoundError
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

from xippios.usda.wasde import _client, tasks
from xippios.usda.wasde import mcp as wasde_mcp
from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.http import router
from xippios.usda.wasde.mcp import server
from xippios.usda.wasde.models import Release, WasdeCommodity, WasdeRegion, WasdeTable
from xippios.usda.wasde.parse import (
    parse_wasde_pdf,
    parse_wasde_xls,
    parse_wasde_xml,
    read_block_titles,
)

FIXTURES = Path(__file__).parent / "fixtures"
FILES = FIXTURES / "files"
SAMPLE = FILES / "wasde_xml" / "sr08_sr35_sr36.xml"
SR11_SR24 = FILES / "wasde_xml" / "sr11_sr24.xml"
SR14 = FILES / "wasde_xml" / "sr14.xml"
XLS_SAMPLE = FILES / "wasde_xls" / "wasde_text_page_8_page_12_page_13_page_14_page_15.xls"
PDF_SAMPLE = FILES / "wasde_pdf" / "wasde-07-09-2010.pdf"
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
RICE = "U.S. Rice Supply and Use"


def page_0() -> list[EsmisRelease]:
    """ESMIS's releases on the recorded page 0, parsed as esmis parses them."""
    fixture = load_fixture(FIXTURES / "release_find_by_identifier" / "wasde_page0.json")
    body = json.loads(fixture.response.content)
    return TypeAdapter(ReleaseResults).validate_python(body).results


def replay_october(replay_fixture: ReplayFixture, *downloads: str) -> list[respx.Route]:
    """Page 0, release 796099 and the downloads named, each at its recorded URL."""
    return [
        replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"]),
        replay_fixture("release_find_by_id", "796099"),
        *(replay_fixture("download_release_file", download) for download in downloads),
    ]


def test_the_package_answers_six_tasks_and_no_bulk_one() -> None:
    assert tasks.__all__ == [
        "get_data",
        "get_report_text",
        "list_commodities",
        "list_regions",
        "list_releases",
        "list_tables",
    ]
    assert not tasks.BULK_TASKS
    assert dict(tasks.MCP_CAPS) == {}


def test_the_tasks_take_year_and_month_first_and_the_rest_by_keyword() -> None:
    """https://github.com/xippios/sdk-usda-esr/issues/60, part 1."""

    def arguments(name: str) -> str:
        signature = inspect.signature(getattr(tasks, name))
        return str(signature.replace(return_annotation=inspect.Signature.empty))

    lists = "(year: int, month: int, *, search: str | None = None)"
    assert {name: arguments(name) for name in tasks.__all__} == {
        "get_data": "(year: int, month: int, *, commodity: str | None = None, "
        "region: str | None = None, table: str | None = None)",
        "get_report_text": "(year: int, month: int)",
        "list_commodities": lists,
        "list_regions": lists,
        "list_releases": "(*, since: datetime.date | None = None, "
        "until: datetime.date | None = None)",
        "list_tables": lists,
    }


@pytest.mark.parametrize("name", tasks.__all__)
def test_a_tool_s_description_stays_under_1000_characters(name: str) -> None:
    """The docstring before ``Args:`` (https://github.com/xippios/sdk-core/issues/485)."""
    description = (inspect.getdoc(getattr(tasks, name)) or "").split("Args:")[0].strip()
    assert len(description) < 1000
    assert "Requests" in description, "each states the most requests one call spends"


def test_list_releases_projects_esmis_releases(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    since = date(2026, 1, 1)
    before = datetime.now(UTC)
    result = tasks.list_releases(since=since)
    after = datetime.now(UTC)
    assert [release.release_datetime.month for release in result.data] == list(range(10, 0, -1))
    assert [release.id for release in result.data][:2] == ["796099", "796054"]
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
    assert list(Release.model_fields) == ["id", "release_datetime", "files"]
    assert result.meta.source == SOURCE
    assert result.meta.endpoint == RELEASES
    assert result.meta.total == 703, "ESMIS's count before the date filter"
    assert result.meta.request == {"since": since}, "until left None is omitted"
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert_time_between(result.meta.retrieved_at, before, after)
    assert sent_urls(route) == [PAGE_0]


def test_a_release_is_a_projection_of_esmis_release() -> None:
    """Every release of page 0: id and time copied, files as esmis reads them."""
    for upstream in page_0():
        release = tasks._release(upstream)
        assert_projection(release, upstream, files=upstream.release_files())
        assert [file.url for file in release.files] == upstream.files


def test_release_keeps_the_time_as_printed() -> None:
    """``release_datetime`` stays aware at ``+00:00``, as ESMIS prints it; never converted."""
    release = tasks._release(page_0()[0])
    assert release.release_datetime.utcoffset() is not None
    assert release.model_dump(mode="json")["release_datetime"] == "2026-10-09T12:00:00Z"


def test_get_data_reads_the_month_s_xml(
    replay_fixture: ReplayFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages 8, 35 and 36: no record of pages 12 to 15, so no XLS is read."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    listed, release, download = replay_october(replay_fixture, "wasde1026_xml")
    xls = replay_fixture("download_release_file", "wasde1026_xls")
    before = datetime.now(UTC)
    result = tasks.get_data(2026, 10)
    after = datetime.now(UTC)
    assert result.data == parse_wasde_xml(SAMPLE), "the records of the replayed body"
    assert result.meta.source == SOURCE
    assert result.meta.endpoint == "wasde1026.xml", "the file's name as catalogued"
    assert result.meta.vintage == "796099", "the ESMIS release id (sdk-core ADR-0060, decision 8)"
    assert (result.meta.published_at, result.meta.published_at_naive) == (OCTOBER_PRINTED, True)
    assert result.meta.request == {"year": 2026, "month": 10, "release_id": 796099, "url": XML}
    assert result.meta.total is None
    assert_time_between(result.meta.retrieved_at, before, after)
    assert (sent_urls(listed), sent_urls(release), sent_urls(download)) == (
        [PAGE_0],
        [RELEASE],
        [XML],
    )
    assert sent_urls(xls) == []
    assert list(tmp_path.iterdir()) == [], "the temporary directory is removed"


def test_get_data_names_pages_12_to_15_from_the_xls(replay_fixture: ReplayFixture) -> None:
    """Page 14's record says ``xls`` where the replay serves the XLS sample."""
    _, release, download, xls = replay_october(
        replay_fixture, "wasde1026_xml_sr14", "wasde1026_xls"
    )
    result = tasks.get_data(2026, 10)
    titles = read_block_titles(XLS_SAMPLE)
    assert result.data == parse_wasde_xml(SR14, block_titles=titles)
    assert list(dict.fromkeys((r.commodity, r.commodity_source) for r in result.data)) == [
        ("TOTAL RICE", "xls"),
        ("LONG-GRAIN RICE", "xls"),
        ("MEDIUM & SHORT-GRAIN RICE", "xls"),
    ]
    assert result.meta.endpoint == "wasde1026.xml"
    assert result.meta.request["xls_url"] == XLS
    assert sent_urls(release) == [RELEASE, RELEASE], "one per download"
    assert (sent_urls(download), sent_urls(xls)) == ([XML], [XLS])


def without_xls(respx_mock: respx.MockRouter) -> respx.Route:
    """NOT RECORDED: release 796099's recorded answer with its XLS file left out
    (conventions §10, kind 4), as a release whose workbook ESMIS does not list."""
    fixture = load_fixture(FIXTURES / "release_find_by_id" / "796099.json")
    body = json.loads(fixture.response.content)
    body["results"][0]["files"] = [
        url for url in body["results"][0]["files"] if not url.endswith(".xls")
    ]
    return respx_mock.get(RELEASE).mock(return_value=httpx.Response(200, json=body))


def test_get_data_names_pages_12_to_15_from_the_layout_without_an_xls(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """Page 14's record says ``layout`` where the replay serves no XLS.

    Page 0 lists the release's XLS, the release's own entry, at the download, no more.
    """
    replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    release = without_xls(respx_mock)
    download = replay_fixture("download_release_file", "wasde1026_xml_sr14")
    result = tasks.get_data(2026, 10)
    assert {record.commodity_source for record in result.data} == {"layout"}
    assert "xls_url" not in result.meta.request
    assert sent_urls(release) == [RELEASE, RELEASE], "the XML's, then the XLS's, which lacks it"
    assert sent_urls(download) == [XML]


@pytest.mark.parametrize(
    ("filters", "count", "xls_read"),
    [
        ({"table": RICE}, 148, True),
        ({"commodity": "LONG-GRAIN RICE"}, 40, True),
        ({"region": "U.S."}, 148, True),
        ({"table": "World Wheat Supply and Use"}, 0, False),
        ({"commodity": "Long-Grain Rice"}, 0, True),
    ],
)
def test_get_data_s_filters_compare_the_labels(
    replay_fixture: ReplayFixture, filters: dict[str, str], count: int, xls_read: bool
) -> None:
    """Equality with the record's ``_label``, after the fetch; a filter nothing matches is []."""
    *_, xls = replay_october(replay_fixture, "wasde1026_xml_sr14", "wasde1026_xls")
    result = tasks.get_data(2026, 10, **filters)
    assert len(result.data) == count
    assert result.meta.request == {
        "year": 2026,
        "month": 10,
        **filters,
        "release_id": 796099,
        "url": XML,
        **({"xls_url": XLS} if xls_read else {}),
    }
    assert sent_urls(xls) == ([XLS] if xls_read else [])


@pytest.mark.parametrize(
    "task", [tasks.get_data, tasks.list_tables, tasks.list_commodities, tasks.list_regions]
)
def test_a_month_before_july_2010_is_refused_before_anything_is_sent(
    respx_mock: respx.MockRouter, task: Callable[..., Any]
) -> None:
    """The maintainer's decision of 2026-11-27: the TXT tables are #31's."""
    with pytest.raises(InvalidRequestError) as caught:
        task(2010, 6)
    assert str(caught.value) == (
        "2010-06 is before July 2010, the first month whose WASDE has an XML file, from which "
        "this package reads the tables; the releases before it carry them as TXT files, which "
        "it does not read (https://github.com/xippios/sdk-usda-wasde/issues/31). Nothing was "
        "sent."
    )
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize("month", [0, 13, -1])
def test_a_month_outside_1_to_12_is_refused_before_anything_is_sent(
    respx_mock: respx.MockRouter, month: int
) -> None:
    for task in (tasks.get_data, tasks.get_report_text):
        with pytest.raises(InvalidRequestError, match=r"month must be 1 to 12.*Nothing was sent"):
            task(2026, month)
    assert respx_mock.calls.call_count == 0


def test_a_month_without_a_wasde_names_the_latest(replay_fixture: ReplayFixture) -> None:
    """October 2025 has no WASDE (OBSERVED.md): the month's pages, then page 0 for the latest.

    As v0.2.0 answers it; the empty list with a note waits for the adoption of
    xippios-core 0.5.0.
    """
    listed = replay_fixture("release_find_by_identifier", "wasde_page0", match_params=["page"])
    with pytest.raises(NotFoundError) as caught:
        tasks.get_data(2025, 10)
    assert str(caught.value) == (
        "ESMIS lists no WASDE release in 2025-10; the latest is that of 2026-10 "
        "(release 796099, 2026-10-09)"
    )
    assert sent_urls(listed) == [PAGE_0, PAGE_0]


def test_list_tables_answers_the_month_s_titles(replay_fixture: ReplayFixture) -> None:
    *_, xls = replay_october(replay_fixture, "wasde1026_xml_sr11_sr24", "wasde1026_xls")
    result = tasks.list_tables(2026, 10)
    assert result.data == [
        WasdeTable(table="U.S. Wheat Supply and Use  1/", table_label="U.S. Wheat Supply and Use"),
        WasdeTable(
            table="U.S. Wheat by Class: Supply and Use",
            table_label="U.S. Wheat by Class: Supply and Use",
        ),
        WasdeTable(
            table="World Rice Supply and Use  (Milled Basis)  1/",
            table_label="World Rice Supply and Use (Milled Basis)",
        ),
    ]
    assert result.meta.vintage == "796099"
    assert result.meta.request == {"year": 2026, "month": 10, "release_id": 796099, "url": XML}
    assert sent_urls(xls) == [], "no commodity is answered, so no XLS is read"
    assert [row.table for row in tasks.list_tables(2026, 10, search="class").data] == [
        "U.S. Wheat by Class: Supply and Use"
    ]


def test_list_commodities_answers_the_month_s_commodities(replay_fixture: ReplayFixture) -> None:
    *_, xls = replay_october(replay_fixture, "wasde1026_xml_sr14", "wasde1026_xls")
    result = tasks.list_commodities(2026, 10)
    assert result.data == [
        WasdeCommodity(commodity=name, commodity_label=name, commodity_source="xls", tables=[RICE])
        for name in ("TOTAL RICE", "LONG-GRAIN RICE", "MEDIUM & SHORT-GRAIN RICE")
    ]
    assert result.meta.request["xls_url"] == XLS
    assert sent_urls(xls) == [XLS]


def test_list_regions_answers_the_month_s_regions(replay_fixture: ReplayFixture) -> None:
    replay_october(replay_fixture, "wasde1026_xml_sr11_sr24")
    result = tasks.list_regions(2026, 10, search="china")
    rice = ["World Rice Supply and Use (Milled Basis)"]
    assert result.data == [
        WasdeRegion(region="    World Less China", region_label="World Less China", tables=rice),
        WasdeRegion(region="        China", region_label="China", tables=rice),
    ]
    assert result.meta.request["search"] == "china"


def test_get_report_text_reads_the_xls_sheet(
    replay_fixture: ReplayFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    listed, release, download = replay_october(replay_fixture, "wasde1026_xls")
    before = datetime.now(UTC)
    result = tasks.get_report_text(2026, 10)
    after = datetime.now(UTC)
    assert result.data == [row.text for row in parse_wasde_xls(XLS_SAMPLE)]
    assert result.data[0] == "WASDE - 676\r"
    assert result.meta.endpoint == "wasde1026.xls", "the file read"
    assert result.meta.vintage == "796099", "the ESMIS release id"
    assert (result.meta.published_at, result.meta.published_at_naive) == (OCTOBER_PRINTED, True)
    assert result.meta.request == {"year": 2026, "month": 10, "release_id": 796099, "url": XLS}
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
    """NOT RECORDED: the recorded release with its files of ``format`` left out
    (conventions §10, kind 4), projected, as a release without that file."""
    files = [url for url in release.files if not url.endswith(f".{format}")]
    return tasks._release(release.model_copy(update={"files": files}))


@pytest.mark.anyio
async def test_a_release_without_an_xls_is_read_from_its_pdf(
    replay_fixture: ReplayFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release 95659 read as one without an XLS: its PDF's narrative, pages 1 to 5."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    release = replay_fixture("release_find_by_id", "95659")
    download = replay_fixture("download_release_file", "wasde-07-09-2010_pdf")
    july = leaving_out(july_2010(), "xls")
    assert tasks._carrying([july], ("xls", "pdf"), "no XLS or PDF").id == "95659"
    result = await tasks._narrative(july, {"year": 2010, "month": 7})
    assert result.data == [page.text for page in parse_wasde_pdf(PDF_SAMPLE)]
    assert len(result.data) == 5
    assert result.meta.endpoint == "wasde-07-09-2010.pdf"
    assert result.meta.vintage == "95659", "the ESMIS release id"
    assert (result.meta.published_at, result.meta.published_at_naive) == (JULY_2010_PRINTED, True)
    assert result.meta.request == {"year": 2010, "month": 7, "release_id": 95659, "url": PDF_2010}
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
    """The recorded XLS answer served at 2010's URL (conventions §10, kind 3); the test
    asserts what was sent and what the PDF gives."""
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
    """The recorded XLS answer served at 2010's URL (conventions §10, kind 3)."""
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
    """As 1995 to 1997 are, TXT only (OBSERVED.md).

    NOT RECORDED: page 0's first release with its TXT file alone (conventions §10, kind 4).
    """
    october = page_0()[0]
    txt = october.model_copy(
        update={"files": [url for url in october.files if url.endswith(".txt")]}
    )
    with pytest.raises(NotFoundError) as caught:
        tasks._carrying(
            [tasks._release(txt)],
            ("xls", "pdf"),
            "no WASDE release of 1996-05 has an XLS or PDF file",
        )
    assert str(caught.value) == (
        "no WASDE release of 1996-05 has an XLS or PDF file: release 796099 (2026-10-09) has txt."
    )


type McpCase = tuple[str, dict[str, Any], list[str], Callable[[Any], bool]]
"""A tool's task name, its arguments, the downloads it replays beside page 0 and release
796099, and a check of its answer."""

MCP_CASES: list[McpCase] = [
    (
        "list_releases",
        {"since": "2026-01-01"},
        [],
        lambda payload: (
            len(payload["data"]) == 10
            and payload["data"][0]["id"] == "796099"
            and payload["meta"]["total"] == 703
            and payload["meta"]["request"] == {"since": "2026-01-01"}
        ),
    ),
    (
        "get_data",
        {"year": 2026, "month": 10, "commodity": "TOTAL RICE"},
        ["wasde1026_xml_sr14", "wasde1026_xls"],
        lambda payload: (
            len(payload["data"]) == 60
            and payload["data"][0]["commodity_source"] == "xls"
            and payload["data"][0]["value_number"] == 2.92
            and payload["meta"]["vintage"] == "796099"
            and payload["meta"]["published_at"] == "2026-10-09T12:00:00"
        ),
    ),
    (
        "list_tables",
        {"year": 2026, "month": 10, "search": "wheat"},
        ["wasde1026_xml_sr11_sr24"],
        lambda payload: (
            [row["table_label"] for row in payload["data"]]
            == ["U.S. Wheat Supply and Use", "U.S. Wheat by Class: Supply and Use"]
        ),
    ),
    (
        "list_commodities",
        {"year": 2026, "month": 10},
        ["wasde1026_xml_sr14", "wasde1026_xls"],
        lambda payload: (
            [row["commodity"] for row in payload["data"]]
            == ["TOTAL RICE", "LONG-GRAIN RICE", "MEDIUM & SHORT-GRAIN RICE"]
        ),
    ),
    (
        "list_regions",
        {"year": 2026, "month": 10, "search": "thailand"},
        ["wasde1026_xml_sr11_sr24"],
        lambda payload: {row["region_label"] for row in payload["data"]} == {"Thailand"},
    ),
    (
        "get_report_text",
        {"year": 2026, "month": 10},
        ["wasde1026_xls"],
        lambda payload: (
            payload["data"] == [row.text for row in parse_wasde_xls(XLS_SAMPLE)]
            and payload["meta"]["endpoint"] == "wasde1026.xls"
            and payload["meta"]["vintage"] == "796099"
        ),
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("task", "arguments", "downloads", "check"), MCP_CASES, ids=[case[0] for case in MCP_CASES]
)
async def test_every_tool_end_to_end(
    replay_fixture: ReplayFixture,
    task: str,
    arguments: dict[str, Any],
    downloads: list[str],
    check: Callable[[Any], bool],
) -> None:
    route, *_ = replay_october(replay_fixture, *downloads)
    payload = await mcp_call(server, f"usda_wasde_{task}", arguments)
    assert payload["meta"]["source"] == SOURCE
    assert check(payload), payload["meta"]
    assert sent_urls(route) == [PAGE_0]


def test_every_task_is_tested_through_the_mcp_server() -> None:
    assert {case[0] for case in MCP_CASES} == set(tasks.__all__)


@pytest.mark.anyio
async def test_a_refusal_reaches_the_agent_as_text(respx_mock: respx.MockRouter) -> None:
    text = await mcp_call_text(server, "usda_wasde_get_data", {"year": 2009, "month": 5})
    assert text.startswith("error: InvalidRequestError: 2009-05 is before July 2010")
    assert respx_mock.calls.call_count == 0


def test_a_route_refuses_a_missing_month_as_problem_details(respx_mock: respx.MockRouter) -> None:
    """HTTP 422 as problem details before the task runs."""
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.get("/usda-wasde/get_data?year=2026")
    assert answer.status_code == 422
    assert answer.json()["detail"] == "month: Field required"
    assert respx_mock.calls.call_count == 0


def test_the_package_reads_no_variable() -> None:
    """``ENV_VARS``, the list a host reads beside ``SOURCE``, is empty: the API is keyless."""
    assert _client.ENV_VARS == ()
    assert wasde_mcp.ENV_VARS is _client.ENV_VARS


def test_build_is_the_tool_set_the_server_serves() -> None:
    tools = wasde_mcp.build()
    assert [task.__name__ for task in tools.tasks] == tasks.__all__
    assert tools.source == SOURCE


ENTRY_POINT = Path(sys.executable).parent / "xippios-usda-wasde-mcp"
"""The installed entry point, ``[project.scripts]`` of ``pyproject.toml``."""
PLAIN = {"PYTHON_COLORS": "0", "COLUMNS": "100"}
"""The terminal the entry point's text is compared in: no colors, which Python 3.14's
argparse adds under ``FORCE_COLOR``, and a width that keeps the usage line whole."""


def test_the_entry_point_names_itself_in_its_usage_and_errors() -> None:
    run = subprocess.run(
        [str(ENTRY_POINT), "--bogus"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, **PLAIN},
    )
    assert run.returncode == 2
    assert run.stderr.startswith("usage: xippios-usda-wasde-mcp [-h]")
    assert run.stderr.splitlines()[-1] == (
        "xippios-usda-wasde-mcp: error: unrecognized arguments: --bogus"
    )


SAMPLED = [
    ("wasde1026_xml", SAMPLE),
    ("wasde1026_xml_sr11_sr24", SR11_SR24),
    ("wasde1026_xml_sr14", SR14),
    ("wasde1026_xls", XLS_SAMPLE),
]
"""The download fixtures whose body is a sample of the file, with that sample."""


@pytest.mark.parametrize(("case", "sample"), SAMPLED, ids=[case for case, _ in SAMPLED])
def test_a_download_fixture_carries_its_sample_marked_sample(case: str, sample: Path) -> None:
    """The body is the sample the parser tests read, marked ``sample``, never ``truncated``."""
    response = load_fixture(FIXTURES / "download_release_file" / f"{case}.json").response
    assert (response.sample, response.truncated) == (True, False)
    assert response.content == sample.read_bytes()
    assert response.original_bytes is not None
    assert response.original_bytes > len(response.content)


def test_the_pdf_download_fixture_is_the_whole_file() -> None:
    response = load_fixture(
        FIXTURES / "download_release_file" / "wasde-07-09-2010_pdf.json"
    ).response
    assert (response.sample, response.truncated) == (False, False)
    assert response.content == PDF_SAMPLE.read_bytes()


def test_the_package_re_exports_the_tasks() -> None:
    import xippios.usda.wasde as package

    for name in tasks.__all__:
        assert getattr(package, name) is getattr(tasks, name)
