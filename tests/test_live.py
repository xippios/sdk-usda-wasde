"""Live smoke tests, one per task, skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

``/add-endpoint`` adds them.

The nightly run fetches the latest release only, each file kind once, through one
session-scoped fixture, ``latest`` (decided by Johannes on 2026-10-28): it runs
``get_release()`` once, which downloads the latest XML through xippios-usda-esmis, and
keeps a copy of the file in a temporary directory for the live parser test, which
checks shape, page names and fields, never values (ADR-0020 decision 6); then it
downloads the release's XLS and its PDF once each through esmis's
``download_release_file``, for the block titles of the commodity list and the live
parser tests of the narrative. ``get_table``, ``get_balance_sheet`` and
``read_report_text`` run live through the fixture ``served``, which hands their
downloads the session's copy of the file instead of fetching it again: each still asks
ESMIS for the latest release and for the release, so its lookups are live, and core's
``AsyncClient.download`` copies the file of the format its URL names. The three
list tasks send nothing: their live tests build the lists from the latest files with
the refresh script's rules (``_vocabulary``) and compare them with the packaged ones,
every field but ``report_month``, the month word of the reliability titles masked
(``Reliability of <Month> Projections``, pages 35 to 37), since every release names its
own month there and the lists carry the release they came from (ADR-0022 decision 1;
gap row 195); each footer of a table, ``sub_report_footer`` to ``sub_report_footer3``,
is compared only for whether it is set on both sides, never its text, which changes
every release (the projection month on page 35, the months of the estimates on pages
13 and 16; the session, 2026-10-28, rule 7; gap row 195). The packaged lists are
refreshed before each release, in the release train's refresh PR (conventions §12), so
a difference between releases is a change upstream made: it fails, naming the rows, and
the lists are refreshed
(``scripts/refresh_reference.py``). Keyless requests, paced by
esmis's client at 30 a minute: the reachability check 1, ``list_releases`` 1 (page 0),
``get_latest_release`` 1, the fixture's ``get_release`` 3 (the latest release, the
release, the file, about 3.4 MB), its XLS 2 and its PDF 2 (the release, the file, about
346 KB and 917 KB), and ``read_report_text``, ``get_table`` and ``get_balance_sheet``
2 each (the latest release, the release): sixteen, three of them downloads, about
4.7 MB. Assertions read shapes, counts and the rows' names, never a raw payload or a
value, as every live run takes ``--tb=short``.
"""

import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from os import PathLike
from pathlib import Path
from typing import Any

import httpx
import pytest
from pypdf import PdfReader
from xippios.core import AsyncClient, Downloaded, Result, UpstreamModel
from xippios.usda.esmis import tasks as esmis

from xippios.usda.wasde import _vocabulary as vocabulary
from xippios.usda.wasde import tasks
from xippios.usda.wasde._client import BASE_URL, config
from xippios.usda.wasde.models import Table, WasdeXmlCell
from xippios.usda.wasde.parse import parse_wasde_pdf, parse_wasde_xls, parse_wasde_xml
from xippios.usda.wasde.parse.wasde_pdf import HEADING
from xippios.usda.wasde.parse.wasde_xls import MONTH_NAMES

pytestmark = [pytest.mark.live, pytest.mark.anyio]

PAGES = {f"sr{number:02d}" for number in range(8, 38)}
"""The pages the October 2026 file holds, printed pages 8 to 37 (``docs/upstream/layout.md``)."""
RELIABILITY = {"sr35", "sr36", "sr37"}
STATISTICS = {
    "root_mean_square_error",
    "confidence_interval",
    "average",
    "smallest",
    "largest",
    "below_final",
    "above_final",
}
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
REPORT_MONTH = re.compile(rf"(?:{'|'.join(MONTH_NAMES)}) \d{{4}}")


@dataclass(frozen=True)
class Latest:
    """The latest release's files, fetched once for the session.

    Attributes:
        release: What ``get_release()`` answered.
        xml: A copy of the XML file it parsed.
        xls: The same release's XLS file.
        pdf: The same release's PDF file.
    """

    release: Result[list[WasdeXmlCell]]
    xml: Path
    xls: Path
    pdf: Path


@pytest.fixture(scope="session")
def latest(tmp_path_factory: pytest.TempPathFactory) -> Latest:
    """``get_release()`` once, keeping a copy of the file its parser reads; the XLS, the PDF."""
    directory = tmp_path_factory.mktemp("latest")
    kept = directory / "wasde.xml"

    def keep_and_parse(path: Path) -> list[WasdeXmlCell]:
        shutil.copyfile(path, kept)
        return parse_wasde_xml(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("xippios.usda.wasde.tasks.parse_wasde_xml", keep_and_parse)
        release = tasks.get_release()
    files = {format: directory / f"wasde.{format}" for format in ("xls", "pdf")}
    for format, path in files.items():
        esmis.download_release_file(release.meta.request["release_id"], format, path)
    return Latest(release=release, xml=kept, xls=files["xls"], pdf=files["pdf"])


@pytest.fixture
def served(latest: Latest, monkeypatch: pytest.MonkeyPatch) -> Latest:
    """The tasks' downloads served from the session's files; their lookups stay live.

    Core's ``AsyncClient.download`` copies the session's file of the format the URL's
    extension names, instead of fetching it again, and answers as the download would.
    """
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
    """The base URL answers without a server error.

    A plain request, not the package's client; any answer below 500 (a 404 at the
    root, say) shows the host is up.
    """
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
        assert MONTH.fullmatch(release.month)
        assert release.revision in (None, "v2")
        assert release.files
        assert all(file.url.endswith(f"/{file.name}") for file in release.files)
    assert result.meta.endpoint == "esmis_api_release_findByIdentifier"
    assert result.meta.total is not None
    assert result.meta.total >= len(result.data)


async def test_get_latest_release_live() -> None:
    result = await tasks.get_latest_release_async()
    assert MONTH.fullmatch(result.data.month)
    assert result.data.release_datetime.date() <= date.today()
    assert result.meta.vintage == result.data.id
    assert result.meta.published_at == result.data.release_datetime.replace(tzinfo=None)
    assert result.meta.published_at_naive
    assert "xml" in {file.format for file in result.data.files}


def test_get_release_live(latest: Latest) -> None:
    result = latest.release
    assert result.data
    assert result.meta.endpoint.endswith(".xml")
    assert result.meta.request["url"].endswith(f"/{result.meta.endpoint}")
    assert isinstance(result.meta.request["release_id"], int)
    assert "month" not in result.meta.request
    assert result.meta.vintage == result.data[0].report_month
    assert result.meta.published_at_naive


def test_parse_wasde_xml_live(latest: Latest) -> None:
    """The current file still reads: every known page has records, every record its fields."""
    records = parse_wasde_xml(latest.xml)
    reports = {record.report for record in records}
    assert reports >= PAGES, sorted(PAGES - reports)
    assert {record.report_month for record in records} == {records[0].report_month}
    for record in records:
        assert record.page_title.strip().startswith("WASDE - ")
        assert record.table
        assert record.matrix.startswith("table" if record.report in RELIABILITY else "matrix")
    on_tables = [record for record in records if record.report not in RELIABILITY]
    for field in ("commodity", "region", "market_year", "forecast_month", "attribute"):
        assert any(getattr(record, field) is not None for record in on_tables), field
    reliability = [record for record in records if record.report in RELIABILITY]
    assert {record.statistic for record in reliability} == STATISTICS
    assert {record.statistic for record in on_tables} == {None}
    numbers = sum(record.value is not None for record in records)
    assert numbers > 0.9 * len(records), "most values are numbers as printed"


def differences(
    packaged: Sequence[UpstreamModel],
    current: Sequence[UpstreamModel],
    name: Callable[[UpstreamModel], str],
) -> list[str]:
    """The rows of the packaged list that the current release's differs in, by name only.

    Every field is compared but ``report_month``, which names the release the list was
    read from; a row missing, added, changed or moved is named, never its values.
    """

    def fields(row: UpstreamModel) -> dict[str, object]:
        return row.model_dump(exclude={"report_month"})

    before = {name(row): fields(row) for row in packaged}
    after = {name(row): fields(row) for row in current}
    found = [f"missing now: {key}" for key in before if key not in after]
    found += [f"new: {key}" for key in after if key not in before]
    found += [f"changed: {key}" for key in before if key in after and before[key] != after[key]]
    shared = [key for key in before if key in after]
    if shared != [key for key in after if key in before]:
        found.append("the order of the rows changed")
    return found


RELIABILITY_TITLE = re.compile(
    rf"(Reliability of (?:United States )?)(?:{'|'.join(MONTH_NAMES)})( Projections)"
)
"""A reliability page's title, its month word the release's own: ``Reliability of October
Projections 1/`` (page 35), ``Reliability of United States October Projections  1/`` (37)."""


def month_masked(table: Table) -> Table:
    """The table with the month word of a reliability title replaced by ``<month>``."""
    titles = ("sub_report_title", "sub_report_title2", "sub_report_title3")
    return table.model_copy(
        update={
            name: RELIABILITY_TITLE.sub(r"\1<month>\2", text)
            for name in titles
            if (text := getattr(table, name)) is not None
        }
    )


FOOTERS = ("sub_report_footer", "sub_report_footer2", "sub_report_footer3")


def footers_set(table: Table) -> Table:
    """The table with each footer reduced to whether it is set: its text changes monthly."""
    return table.model_copy(
        update={name: "<set>" for name in FOOTERS if getattr(table, name) is not None}
    )


def by_report(row: UpstreamModel) -> str:
    return str(getattr(row, "report", ""))


def by_matrix(row: UpstreamModel) -> str:
    return f"{getattr(row, 'report', '')} {getattr(row, 'matrix', '')}"


def by_region(row: UpstreamModel) -> str:
    return repr(getattr(row, "region", ""))


def test_block_titles_live(latest: Latest) -> None:
    """The positional match still holds: each page of 12 to 15 has a title per matrix."""
    titles = vocabulary.block_titles(latest.xls)
    records = parse_wasde_xml(latest.xml)
    packaged = tasks.list_commodities().data
    for page in vocabulary.BLOCK_PAGES:
        report = vocabulary.report_name(page)
        matrices = list(dict.fromkeys(cell.matrix for cell in records if cell.report == report))
        assert len(titles[report]) == len(matrices), report
        assert titles[report] == [row.commodity for row in packaged if row.report == report], (
            f"{report}: the block titles changed; refresh the packaged lists"
        )


async def test_list_tables_live(latest: Latest) -> None:
    """The packaged tables are the latest release's, but for the month and the footers' text.

    The reliability titles' month word is masked, and each footer is compared only for
    whether it is set on both sides, never its text.
    """
    result = await tasks.list_tables_async()
    masked = [month_masked(table) for table in result.data]
    assert sum(table != month for table, month in zip(result.data, masked, strict=True)) == 3
    packaged = [footers_set(table) for table in masked]
    current = [footers_set(month_masked(table)) for table in vocabulary.tables(latest.xml)]
    assert not differences(packaged, current, by_report)
    assert result.meta.endpoint.endswith(".xml")


async def test_list_commodities_live(latest: Latest) -> None:
    result = await tasks.list_commodities_async()
    records = parse_wasde_xml(latest.xml)
    current = vocabulary.commodities(records, vocabulary.block_titles(latest.xls))
    assert not differences(result.data, current, by_matrix)
    assert result.meta.vintage


async def test_list_regions_live(latest: Latest) -> None:
    result = await tasks.list_regions_async()
    current = vocabulary.regions(parse_wasde_xml(latest.xml))
    assert not differences(result.data, current, by_region)
    assert result.meta.vintage


def test_parse_wasde_xls_live(latest: Latest) -> None:
    """The current XLS still holds its narrative sheet and the month of its first page."""
    rows = parse_wasde_xls(latest.xls)
    assert rows
    assert rows[0].text.startswith("WASDE -")
    assert [row.row for row in rows] == sorted({row.row for row in rows})
    assert {row.sheet for row in rows} == {"WASDE Text"}
    assert {row.report_month for row in rows} == {latest.release.data[0].report_month}


def test_parse_wasde_pdf_live(latest: Latest) -> None:
    """The current PDF's narrative still ends before the committees' page."""
    pages = parse_wasde_pdf(latest.pdf)
    reader = PdfReader(latest.pdf)
    assert [page.page for page in pages] == list(range(1, len(pages) + 1))
    assert len(pages) < len(reader.pages)
    assert all(page.text.strip() for page in pages), "every narrative page has a text layer"
    after = reader.pages[len(pages)].extract_text()
    assert HEADING.casefold() in [line.strip().casefold() for line in after.splitlines()]


async def test_read_report_text_live(served: Latest) -> None:
    result = await tasks.read_report_text_async()
    assert result.data
    assert result.data[0].startswith("WASDE -")
    assert result.meta.endpoint.endswith(".xls")
    assert result.meta.request["url"].endswith(f"/{result.meta.endpoint}")
    assert result.meta.vintage is not None
    assert REPORT_MONTH.fullmatch(result.meta.vintage)
    assert result.meta.vintage == served.release.meta.vintage, "the XML's Report_Month"
    assert result.meta.published_at_naive


async def test_get_table_live(served: Latest) -> None:
    result = await tasks.get_table_async("sr12")
    packaged = {table.report: table for table in tasks.list_tables().data}
    assert result.data
    assert {record.report for record in result.data} == {"sr12"}
    assert list(dict.fromkeys(record.matrix for record in result.data)) == (
        packaged["sr12"].matrices
    )
    for field in ("attribute", "market_year", "forecast_month"):
        assert any(getattr(record, field) is not None for record in result.data), field
    assert result.meta.endpoint.endswith(".xml")
    assert result.meta.request["table"] == "sr12"


async def test_get_balance_sheet_live(served: Latest) -> None:
    result = await tasks.get_balance_sheet_async("CORN")
    assert result.data
    assert {(record.report, record.matrix) for record in result.data} == {("sr12", "matrix2")}
    for field in ("attribute", "market_year", "cell_value"):
        assert all(getattr(record, field) is not None for record in result.data), field
    assert result.meta.request["commodity"] == "CORN"
    assert result.meta.vintage == served.release.meta.vintage
