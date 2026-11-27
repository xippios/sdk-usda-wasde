"""Live smoke tests, one per task, skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

``/add-endpoint`` adds them.

The nightly run reads the latest release only, each file kind once, through one
session-scoped fixture, ``latest``, as https://github.com/xippios/sdk-usda-wasde/pull/3
and https://github.com/xippios/sdk-usda-wasde/pull/5 decided: it finds the latest
release's month by ``list_releases``, runs ``get_data`` for it once, which downloads the
XML and the XLS through xippios-usda-esmis, keeps a copy of both for the live parser
tests, which check shape, pages and fields, never values (sdk-core ADR-0020 decision 6),
and downloads the release's PDF once through esmis's ``download_release_file``. The fixed
table of pages 12 to 15 (``parse.wasde_xml.LAYOUT``) is held against the latest XLS's
block titles each night (sdk-core ADR-0061, decision 12). The three list tasks and
``get_report_text`` run live through the fixture ``served``, which hands their downloads
the session's copy of the file instead of fetching it again: each still asks ESMIS for
the month's releases and for the release, so its lookups are live, and core's
``AsyncClient.download`` copies the file of the format its URL names. Keyless requests,
paced by esmis's client at 30 a minute, counted from this module: the reachability check
1, ``list_releases`` 1 (page 0), the fixture 8 (page 0 for the month, then ``get_data``'s
page 0, the release and the XML, the release and the XLS, and the PDF's release and file),
``list_tables``, ``list_regions`` and ``get_report_text`` 2 each (page 0, the release) and
``list_commodities`` 3 (page 0, the release for the XML and for the XLS): nineteen, three
of them downloads, the XML, the XLS and the PDF. Assertions read shapes, counts and the
rows' names, never a raw payload or a value, as every live run takes ``--tb=short``.
"""

import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from os import PathLike
from pathlib import Path
from typing import Any

import httpx
import pytest
from pypdf import PdfReader
from xippios.core import AsyncClient, Downloaded, Result
from xippios.usda.esmis import tasks as esmis

from xippios.usda.wasde import tasks
from xippios.usda.wasde._client import BASE_URL, config
from xippios.usda.wasde.models import WasdeRecord
from xippios.usda.wasde.parse import (
    parse_wasde_pdf,
    parse_wasde_xls,
    parse_wasde_xml,
    read_block_titles,
)
from xippios.usda.wasde.parse.wasde_pdf import HEADING
from xippios.usda.wasde.parse.wasde_xml import LAYOUT

pytestmark = [pytest.mark.live, pytest.mark.anyio]

STATISTICS = {
    "root_mean_square_error",
    "confidence_interval",
    "average",
    "smallest",
    "largest",
    "below_final",
    "above_final",
}


@dataclass(frozen=True)
class Latest:
    """The latest release's month and files, fetched once for the session.

    Attributes:
        year: The latest release's year.
        month: Its month.
        data: What ``get_data`` answered for it.
        xml: A copy of the XML file it parsed.
        xls: A copy of the XLS file it read.
        pdf: The same release's PDF file.
    """

    year: int
    month: int
    data: Result[list[WasdeRecord]]
    xml: Path
    xls: Path
    pdf: Path


@pytest.fixture(scope="session")
def latest(tmp_path_factory: pytest.TempPathFactory) -> Latest:
    """``get_data`` once for the latest month, keeping its XML and XLS; the PDF."""
    directory = tmp_path_factory.mktemp("latest")
    newest = tasks.list_releases(since=date.today() - timedelta(days=93)).data[0]
    printed = newest.release_datetime
    kept = {"xml": directory / "wasde.xml", "xls": directory / "wasde.xls"}

    def keep_xml(path: Path, **kwargs: Any) -> list[WasdeRecord]:
        shutil.copyfile(path, kept["xml"])
        return parse_wasde_xml(path, **kwargs)

    def keep_xls(path: Path) -> dict[int, list[str]]:
        shutil.copyfile(path, kept["xls"])
        return read_block_titles(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("xippios.usda.wasde.tasks.parse_wasde_xml", keep_xml)
        patch.setattr("xippios.usda.wasde.tasks.read_block_titles", keep_xls)
        data = tasks.get_data(printed.year, printed.month)
    pdf = directory / "wasde.pdf"
    esmis.download_release_file(int(newest.id), format="pdf", dest=pdf)
    return Latest(printed.year, printed.month, data, kept["xml"], kept["xls"], pdf)


@pytest.fixture
def served(latest: Latest, monkeypatch: pytest.MonkeyPatch) -> Latest:
    """The tasks' downloads served from the session's files; their lookups stay live."""
    files = {"xml": latest.xml, "xls": latest.xls, "pdf": latest.pdf}

    async def copy(self: AsyncClient, url: str, dest: str | PathLike[str], **_: Any) -> Downloaded:
        source = files[url.rsplit(".", 1)[-1].lower()]
        shutil.copyfile(source, dest)
        return Downloaded(
            path=Path(dest),
            bytes=source.stat().st_size,
            content_type=None,
            filename=None,
            etag=None,
            last_modified=None,
            retrieved_at=datetime.now(UTC),
        )

    monkeypatch.setattr(AsyncClient, "download", copy)
    return latest


async def test_upstream_answers() -> None:
    """The base URL answers without a server error: a plain request, any answer below 500."""
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
    assert response.status_code < 500


async def test_list_releases_live() -> None:
    """Three months back, one page: WASDE releases monthly, with a gap of 63 days at most."""
    result = await tasks.list_releases_async(since=date.today() - timedelta(days=93))
    assert result.data
    for release in result.data:
        assert release.id.isdigit()
        assert release.files
        assert all(file.url.endswith(f"/{file.name}") for file in release.files)
    assert result.meta.endpoint == "esmis_api_release_findByIdentifier"
    assert result.meta.total is not None


def test_get_data_live(latest: Latest) -> None:
    """The latest month's records, pages 12 to 15 named from its XLS."""
    result = latest.data
    assert result.data
    assert result.meta.endpoint.endswith(".xml")
    assert result.meta.request["xls_url"].endswith(".xls")
    assert result.meta.vintage == str(result.meta.request["release_id"])
    assert result.meta.published_at_naive
    on_layout = [record for record in result.data if record.table_label in LAYOUT]
    assert on_layout
    assert {record.commodity_source for record in on_layout} == {"xls"}


def test_parse_wasde_xml_live(latest: Latest) -> None:
    """The current file still reads: every record its fields, the reliability statistics."""
    records = parse_wasde_xml(latest.xml)
    assert {record.report_month for record in records} == {records[0].report_month}
    assert {record.report_number for record in records} == {records[0].report_number}
    for field in ("commodity", "region", "market_year", "forecast_month", "attribute", "unit"):
        assert any(getattr(record, field) is not None for record in records), field
    assert {record.statistic for record in records} - {None} == STATISTICS
    assert sum(record.value_number is not None for record in records) > 0.9 * len(records)
    assert {record.commodity_source for record in records} >= {None, "title", "layout"}


def test_the_fixed_table_is_the_latest_xls_s_block_titles(latest: Latest) -> None:
    """sdk-core ADR-0061, decision 12: ``LAYOUT`` held against the latest XLS each night."""
    titles = read_block_titles(latest.xls)
    records = parse_wasde_xml(latest.xml)
    by_page = {record.table_label for record in records} & set(LAYOUT)
    assert by_page == set(LAYOUT), "the four titles of pages 12 to 15"
    assert sorted(tuple(texts) for texts in titles.values()) == sorted(LAYOUT.values()), (
        "the block titles changed: update parse.wasde_xml.LAYOUT"
    )


async def test_list_tables_live(served: Latest) -> None:
    result = await tasks.list_tables_async(served.year, served.month)
    assert {row.table_label for row in result.data} >= set(LAYOUT)
    assert result.meta.vintage == served.data.meta.vintage


async def test_list_commodities_live(served: Latest) -> None:
    result = await tasks.list_commodities_async(served.year, served.month)
    named = {row.commodity for row in result.data if row.commodity_source == "xls"}
    assert named == {text for texts in LAYOUT.values() for text in texts}
    assert result.meta.request["xls_url"].endswith(".xls")


async def test_list_regions_live(served: Latest) -> None:
    result = await tasks.list_regions_async(served.year, served.month, search="world")
    assert "World" in {row.region_label for row in result.data}


def test_parse_wasde_xls_live(latest: Latest) -> None:
    """The current XLS still holds its narrative sheet and the month of its first page."""
    rows = parse_wasde_xls(latest.xls)
    assert rows
    assert rows[0].text.startswith("WASDE -")
    assert {row.sheet for row in rows} == {"WASDE Text"}
    assert {row.report_month for row in rows} == {latest.data.data[0].report_month}


def test_parse_wasde_pdf_live(latest: Latest) -> None:
    """The current PDF's narrative still ends before the committees' page."""
    pages = parse_wasde_pdf(latest.pdf)
    reader = PdfReader(latest.pdf)
    assert [page.page for page in pages] == list(range(1, len(pages) + 1))
    assert len(pages) < len(reader.pages)
    assert all(page.text.strip() for page in pages), "every narrative page has a text layer"
    after = reader.pages[len(pages)].extract_text()
    assert HEADING.casefold() in [line.strip().casefold() for line in after.splitlines()]


async def test_get_report_text_live(served: Latest) -> None:
    result = await tasks.get_report_text_async(served.year, served.month)
    assert result.data
    assert result.data[0].startswith("WASDE -")
    assert result.meta.endpoint.endswith(".xls")
    assert result.meta.vintage == served.data.meta.vintage, "the ESMIS release id"
    assert result.meta.published_at_naive
