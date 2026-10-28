"""Live smoke tests, one per task, skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

``/add-endpoint`` adds them.

The nightly run fetches the latest release only, each file kind once, through one
session-scoped fixture, ``latest`` (decided by Johannes on 2026-10-28): it runs
``get_release()`` once, which downloads the latest XML through xippios-usda-esmis, and
keeps a copy of the file in a temporary directory for the live parser test, which
checks shape, page names and fields, never values (ADR-0020 decision 6); later file
kinds join the same fixture. Keyless requests, paced by esmis's client at 30 a minute:
the reachability check 1, ``list_releases`` 1 (page 0), ``get_latest_release`` 1, and
the fixture's ``get_release`` 3 (the latest release, the release, the file, about
3.4 MB). Assertions read shapes and counts, never a raw payload, as every live run
takes ``--tb=short``.
"""

import re
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from xippios.core import Result

from xippios.usda.wasde import tasks
from xippios.usda.wasde._client import BASE_URL, config
from xippios.usda.wasde.models import WasdeXmlCell
from xippios.usda.wasde.parse import parse_wasde_xml

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


@dataclass(frozen=True)
class Latest:
    """The latest release's files, fetched once for the session.

    Attributes:
        release: What ``get_release()`` answered.
        xml: A copy of the XML file it parsed.
    """

    release: Result[list[WasdeXmlCell]]
    xml: Path


@pytest.fixture(scope="session")
def latest(tmp_path_factory: pytest.TempPathFactory) -> Latest:
    """``get_release()`` once, keeping a copy of the file its parser reads."""
    kept = tmp_path_factory.mktemp("latest") / "wasde.xml"

    def keep_and_parse(path: Path) -> list[WasdeXmlCell]:
        shutil.copyfile(path, kept)
        return parse_wasde_xml(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("xippios.usda.wasde.tasks.parse_wasde_xml", keep_and_parse)
        release = tasks.get_release()
    return Latest(release=release, xml=kept)


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
