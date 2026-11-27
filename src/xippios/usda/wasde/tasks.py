"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them.

This package sends no request of its own: ESMIS's catalog and the download are
``xippios-usda-esmis``'s tasks, which it imports with their models and nothing else, never
``api/`` or ``_client`` (sdk-core ADR-0021), for the publication whose ESMIS identifier is
``"wasde"``. Every argument after the first is passed to them by name. The pace is
esmis's client's, 30 requests a minute.

What every task follows:

- ``meta.source`` is this package's, ``"usda-wasde"``; ``meta.retrieved_at`` is the time
  esmis's answer arrived, for the tasks that read a file the time the XML or the narrative's
  file was complete.
- A report is named by its year and its month, two integers, positional and first
  (https://github.com/xippios/sdk-usda-esr/issues/60, part 1), and is the month's latest
  release by ESMIS's printed date of ``release_datetime`` that carries the file read; every
  other argument is keyword-only. A month from 1 to 12 is checked before anything is sent.
- ``get_data``, ``list_tables``, ``list_commodities`` and ``list_regions`` read the release's
  XML (``parse.wasde_xml``), and the first two its XLS too where a record of pages 12 to 15
  is answered, for the block titles that name those tables' commodities
  (``parse.wasde_xls.read_block_titles``). They refuse a month before July 2010, the first
  with an XML file, before anything is sent (the maintainer's decision of 2026-11-27).
- A task that reads a file answers ``meta.endpoint`` the file's name as ESMIS catalogs it
  (``"wasde1026.xml"``), ``meta.vintage`` the ESMIS release id (``"796099"``; sdk-core
  ADR-0060, decision 8), ``meta.published_at`` the release time as ESMIS prints it with
  its ``+0000`` dropped, flagged ``published_at_naive`` (sdk-core ADR-0041), and
  ``meta.request`` the arguments given, none left ``None``, with the release id and the
  file's URL, and ``xls_url`` where the XLS was read.
- A month in which ESMIS lists no WASDE raises ``NotFoundError`` naming the latest
  release, the first row of ESMIS's first page of WASDE's releases.
- ``list_releases`` keeps esmis's ``meta.endpoint`` (``esmis_api_release_findByIdentifier``)
  and its ``meta.total``.
"""

import calendar
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path

from xippios.core import (
    Downloaded,
    InvalidRequestError,
    NotFoundError,
    Result,
    ResultCap,
    ResultMeta,
    XippiosError,
    matches,
    sync,
)
from xippios.usda.esmis import tasks as esmis
from xippios.usda.esmis.models import Release as EsmisRelease

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import (
    Release,
    WasdeCommodity,
    WasdeRecord,
    WasdeRegion,
    WasdeTable,
)
from xippios.usda.wasde.parse.wasde_pdf import parse_wasde_pdf
from xippios.usda.wasde.parse.wasde_xls import parse_wasde_xls, read_block_titles
from xippios.usda.wasde.parse.wasde_xml import parse_wasde_xml

__all__ = [
    "get_data",
    "get_report_text",
    "list_commodities",
    "list_regions",
    "list_releases",
    "list_tables",
]

# A task named here is Python-only: no tool, no route; the adapters skip it (sdk-core ADR-0040
# decision 4). None is.
BULK_TASKS: frozenset[str] = frozenset()

# MCP_CAPS, only where a tool needs a result cap of its own (conventions §8, sdk-core
# ADR-0038). None does: every tool keeps the default, 200 rows or 64 KB, whose note names
# the narrowing; get_data's filters narrow a month's records.
MCP_CAPS: Mapping[str, ResultCap] = {}

PUBLICATION = "wasde"
"""WASDE's publication identifier in ESMIS, which esmis's release tasks take."""

FIRST_XML = (2010, 7)
"""The year and month of the first WASDE release with an XML file, that of 2010-07-09
(release 95659), as observed on 2026-10-28 (``docs/upstream/OBSERVED.md``)."""

TXT_TABLES = "https://github.com/xippios/sdk-usda-wasde/issues/31"
"""The issue that asks for the TXT tables of the releases before July 2010."""

_FIRST_XML_RELEASE = "the first with an XML file is that of 2010-07-09 (release 95659)"


def _month(year: int, month: int) -> tuple[date, date]:
    """The first and the last day of the month; a month outside 1 to 12 is refused."""
    if not 1 <= month <= 12:
        raise InvalidRequestError(
            f"month must be 1 to 12, e.g. 10 for October; got {month}. Nothing was sent.",
            source=SOURCE,
        )
    if not 1 <= year <= 9999:
        raise InvalidRequestError(
            f"year must be a year such as 2026; got {year}. Nothing was sent.", source=SOURCE
        )
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _with_tables(year: int, month: int) -> tuple[date, date]:
    """The month's first and last day; a month before July 2010 is refused as well."""
    bounds = _month(year, month)
    if (year, month) < FIRST_XML:
        raise InvalidRequestError(
            f"{year}-{month:02d} is before July 2010, the first month whose WASDE has an XML "
            "file, from which this package reads the tables; the releases before it carry "
            f"them as TXT files, which it does not read ({TXT_TABLES}). Nothing was sent.",
            source=SOURCE,
        )
    return bounds


def _release(release: EsmisRelease) -> Release:
    """ESMIS's release projected: its id and time copied, its files as esmis reads them."""
    return Release.project(release, files=release.release_files())


def _formats(release: Release) -> str:
    """The release's formats in ESMIS's order, each once, e.g. ``"pdf, txt"``."""
    return ", ".join(dict.fromkeys(file.format for file in release.files)) or "none"


def _carrying(
    releases: list[Release], formats: tuple[str, ...], refusal: str, after: str = ""
) -> Release:
    """Of the releases checked, the latest that carries a file in one of ``formats``.

    The latest by release time, the first ESMIS lists where several share it (in 2010-12
    and 2014-01 a later release carries a TXT or an ASC file only). None is refused with
    ``NotFoundError``: ``refusal`` opens the message, then every release checked with its
    formats, then ``after``.
    """
    carrying = [
        release for release in releases if any(file.format in formats for file in release.files)
    ]
    if carrying:
        return max(carrying, key=lambda release: release.release_datetime)
    listed = "; ".join(
        f"release {release.id} ({release.release_datetime:%Y-%m-%d}) has {_formats(release)}"
        for release in releases
    )
    raise NotFoundError(f"{refusal}: {listed}.{after}", source=SOURCE)


async def _releases(year: int, month: int, bounds: tuple[date, date]) -> list[Release]:
    """Every release of the month; a month without one is refused, naming the latest.

    Requests: the pages of esmis's ``list_releases`` from the newest back to the month,
    then, for a month without a release, ESMIS's first page once more for the latest.
    """
    since, until = bounds
    listed = await esmis.list_releases_async(PUBLICATION, since=since, until=until)
    if listed.data:
        return [_release(item) for item in listed.data]
    first = await esmis.list_releases_async(PUBLICATION, page=0)
    if not first.data:
        raise NotFoundError("ESMIS lists no WASDE release", source=SOURCE)
    latest = first.data[0]
    raise NotFoundError(
        f"ESMIS lists no WASDE release in {year}-{month:02d}; the latest is that of "
        f"{latest.release_datetime:%Y-%m} (release {latest.id}, "
        f"{latest.release_datetime:%Y-%m-%d})",
        source=SOURCE,
    )


def _meta(
    downloaded: Result[Downloaded], release: Release, request: dict[str, object]
) -> ResultMeta:
    """The meta of a task that reads a release's file (conventions §4)."""
    return ResultMeta(
        source=SOURCE,
        endpoint=downloaded.meta.endpoint,
        retrieved_at=downloaded.meta.retrieved_at,
        published_at=downloaded.meta.published_at,
        published_at_naive=downloaded.meta.published_at_naive,
        vintage=release.id,
        request={
            **{name: value for name, value in request.items() if value is not None},
            "release_id": int(release.id),
            "url": downloaded.meta.request["url"],
        },
    )


async def _read(
    year: int,
    month: int,
    request: dict[str, object],
    needs_xls: Callable[[list[WasdeRecord]], bool],
) -> Result[list[WasdeRecord]]:
    """The records of the month's XML, the XLS's block titles read where ``needs_xls`` asks.

    The release is the month's latest that carries an XML file. Its XML is downloaded into a
    temporary directory and parsed, its records of pages 12 to 15 taking their commodity from
    the fixed table of the layout; where ``needs_xls`` asks it of those records and the
    release has an XLS, the XLS is downloaded and the XML read again with its block titles.
    An XLS that cannot be read, its download refused or its workbook one xlrd cannot read,
    leaves the layout's, and the answer names no ``xls_url``. The directory is removed.
    """
    bounds = _with_tables(year, month)
    release = _carrying(
        await _releases(year, month, bounds),
        ("xml",),
        f"no WASDE release of {year}-{month:02d} has an XML file",
        f" Of the WASDE releases ESMIS lists, {_FIRST_XML_RELEASE}.",
    )
    xls_url: str | None = None
    with tempfile.TemporaryDirectory(prefix="xippios-usda-wasde-") as directory:
        xml = Path(directory) / "release.xml"
        downloaded = await esmis.download_release_file_async(
            int(release.id), format="xml", dest=xml
        )
        records = parse_wasde_xml(xml)
        if needs_xls(records) and "xls" in {file.format for file in release.files}:
            xls = Path(directory) / "release.xls"
            try:
                workbook = await esmis.download_release_file_async(
                    int(release.id), format="xls", dest=xls
                )
                titles = read_block_titles(xls)
            except XippiosError:
                titles = {}
            else:
                xls_url = str(workbook.meta.request["url"])
            if titles:
                records = parse_wasde_xml(xml, block_titles=titles)
    meta = _meta(downloaded, release, request)
    if xls_url is not None:
        meta.request["xls_url"] = xls_url
    return Result(data=records, meta=meta)


def _on_layout(records: Sequence[WasdeRecord]) -> bool:
    """Whether a record takes its commodity from the fixed table of the layout."""
    return any(record.commodity_source == "layout" for record in records)


def _kept(record: WasdeRecord, table: str | None, region: str | None) -> bool:
    """Whether ``get_data``'s table and region filters keep the record."""
    return (table is None or record.table_label == table) and (
        region is None or record.region_label == region
    )


async def get_data_async(
    year: int,
    month: int,
    *,
    commodity: str | None = None,
    region: str | None = None,
    table: str | None = None,
) -> Result[list[WasdeRecord]]:
    """Every value of a month's WASDE tables, one record each, complete in itself.

    Read from the release's XML, pages 8 to 37: 6543 values for October 2026. A record
    holds the report's number and month, the table, commodity, region, market year with
    its status, forecast month, row label, class, statistic, unit, the value as printed
    with its number, and its footnotes' texts, each label beside its ``_label``. On pages
    12 to 15 the commodity is the block title of the release's XLS, else the report's
    layout (``commodity_source``). The filters keep the records whose ``_label`` equals
    them, else answer the empty list. Requests, each tried up to 4 times: the pages of
    ESMIS's list from the newest back to the month, 25 releases a page (1 for the last two
    years), the release and the XML, 2, and where a record of pages 12 to 15 is kept the
    release and the XLS, 2 more. A month before July 2010 raises ``InvalidRequestError``
    before anything is sent; a month without a release ``NotFoundError``.

    Args:
        year: The report's year, e.g. ``2026``.
        month: The report's month, 1 to 12, e.g. ``10``; from July 2010 on.
        commodity: Keep the records whose ``commodity_label`` is this, e.g. ``"CORN"``
            (page 12, U.S.), ``"Corn"`` (world pages), ``"Total Grains"``;
            ``list_commodities`` lists them.
        region: Keep the records whose ``region_label`` is this, e.g. ``"Argentina"``,
            ``"World"``, ``"U.S."``; ``list_regions`` lists them.
        table: Keep the records whose ``table_label`` is this, e.g. ``"World Wheat Supply
            and Use"``; ``list_tables`` lists them.
    """
    request: dict[str, object] = {
        "year": year,
        "month": month,
        "commodity": commodity,
        "region": region,
        "table": table,
    }
    result = await _read(
        year,
        month,
        request,
        lambda records: _on_layout([r for r in records if _kept(r, table, region)]),
    )
    kept = [
        record
        for record in result.data
        if _kept(record, table, region)
        and (commodity is None or record.commodity_label == commodity)
    ]
    return Result(data=kept, meta=result.meta)


async def list_tables_async(
    year: int, month: int, *, search: str | None = None
) -> Result[list[WasdeTable]]:
    """The tables of a month's WASDE release, their titles as printed and as read.

    One row per distinct title of the month's records in the order of the file, read from
    the release's XML: 35 for October 2026, from ``"World and U.S. Supply and Use for
    Grains  1/"`` to the reliability tables. A row's ``table_label`` is what ``get_data``'s
    ``table`` compares. Requests, each tried up to 4 times: the pages of ESMIS's list from
    the newest back to the month, 25 releases a page (1 for the last two years), then the
    release and the XML, 2. A month before July 2010 raises ``InvalidRequestError`` before
    anything is sent; a month without a release ``NotFoundError``.

    Args:
        year: The report's year, e.g. ``2026``.
        month: The report's month, 1 to 12, e.g. ``10``; from July 2010 on.
        search: Keep the rows where this text occurs, ignoring case, in the title as
            printed or as read, e.g. ``"wheat"``, ``"reliability"``; ``None`` (the
            default) keeps every row.
    """
    result = await _read(year, month, {"year": year, "month": month, "search": search}, _never)
    rows: dict[str, WasdeTable] = {}
    for record in result.data:
        rows.setdefault(
            record.table, WasdeTable(table=record.table, table_label=record.table_label)
        )
    kept = [row for row in rows.values() if matches(search, row.table, row.table_label)]
    return Result(data=kept, meta=result.meta)


def _never(records: Sequence[WasdeRecord]) -> bool:
    """A task that reads no commodity needs no XLS."""
    return False


async def list_commodities_async(
    year: int, month: int, *, search: str | None = None
) -> Result[list[WasdeCommodity]]:
    """The commodities of a month's WASDE release, as printed and as read, with their tables.

    One row per distinct commodity and source of the month's records in the order of the
    file, read from the release's XML, and for pages 12 to 15 the block titles of its XLS
    (``commodity_source`` ``"xls"``, else ``"layout"``): ``"CORN"`` is page 12's U.S. corn,
    ``"Corn"`` the world corn pages. A row's ``commodity_label`` is what ``get_data``'s
    ``commodity`` compares, and its ``tables`` the tables that print it. Requests, each tried
    up to 4 times: the pages of ESMIS's list from the newest back to the month, 25 releases
    a page (1 for the last two years), the release and the XML, 2, and the release and the
    XLS, 2. A month before July 2010 raises ``InvalidRequestError`` before anything is
    sent; a month without a release ``NotFoundError``.

    Args:
        year: The report's year, e.g. ``2026``.
        month: The report's month, 1 to 12, e.g. ``10``; from July 2010 on.
        search: Keep the rows where this text occurs, ignoring case, in the commodity as
            printed or as read or in one of its tables, e.g. ``"rice"``, ``"soybean"``;
            ``None`` (the default) keeps every row.
    """
    request: dict[str, object] = {"year": year, "month": month, "search": search}
    result = await _read(year, month, request, _on_layout)
    rows: dict[tuple[str, str | None], WasdeCommodity] = {}
    for record in result.data:
        if record.commodity is None or record.commodity_label is None:
            continue
        row = rows.setdefault(
            (record.commodity, record.commodity_source),
            WasdeCommodity(
                commodity=record.commodity,
                commodity_label=record.commodity_label,
                commodity_source=record.commodity_source,
                tables=[],
            ),
        )
        if record.table_label not in row.tables:
            row.tables.append(record.table_label)
    kept = [
        row
        for row in rows.values()
        if matches(search, row.commodity, row.commodity_label, *row.tables)
    ]
    return Result(data=kept, meta=result.meta)


async def list_regions_async(
    year: int, month: int, *, search: str | None = None
) -> Result[list[WasdeRegion]]:
    """The regions of a month's WASDE release, as printed and as read, with their tables.

    One row per distinct region text of the month's records in the order of the file,
    read from the release's XML, so a region printed with several indents or marks has a
    row for each: ``"World"``, ``"World  2/"`` and ``"World  3/"`` all read ``"World"``. A
    row's ``region_label`` is what ``get_data``'s ``region`` compares, and its ``tables``
    the tables that print it. Requests, each tried up to 4 times: the pages of ESMIS's list
    from the newest back to the month, 25 releases a page (1 for the last two years), then
    the release and the XML, 2. A month before July 2010 raises ``InvalidRequestError``
    before anything is sent; a month without a release ``NotFoundError``.

    Args:
        year: The report's year, e.g. ``2026``.
        month: The report's month, 1 to 12, e.g. ``10``; from July 2010 on.
        search: Keep the rows where this text occurs, ignoring case, in the region as
            printed or as read or in one of its tables, e.g. ``"china"``, ``"european
            union"``; ``None`` (the default) keeps every row.
    """
    result = await _read(year, month, {"year": year, "month": month, "search": search}, _never)
    rows: dict[str, WasdeRegion] = {}
    for record in result.data:
        if record.region is None or record.region_label is None:
            continue
        row = rows.setdefault(
            record.region,
            WasdeRegion(region=record.region, region_label=record.region_label, tables=[]),
        )
        if record.table_label not in row.tables:
            row.tables.append(record.table_label)
    kept = [
        row for row in rows.values() if matches(search, row.region, row.region_label, *row.tables)
    ]
    return Result(data=kept, meta=result.meta)


async def list_releases_async(
    *, since: date | None = None, until: date | None = None
) -> Result[list[Release]]:
    """WASDE's releases in ESMIS, newest first, each with its id, release time and files.

    Read through xippios-usda-esmis's ``list_releases`` for ``"wasde"``
    (``esmis_api_release_findByIdentifier``). Requests, each tried up to 4 times: one per
    page of 25 releases. ``since`` and ``until`` keep the releases whose printed release
    date lies between them, both included, and ``since`` ends the walk of the pages.
    Without ``since`` every page is walked, 29 requests for the 704 releases of
    2026-11-27, about a minute: bound the call with ``since``. A file name ending in
    ``v2`` (``wasde0626v2.xml``) marks a month WAOB reposted. ``meta.total`` is ESMIS's
    count before the date filter. A ``since`` after ``until`` raises
    ``InvalidRequestError``, refused by xippios-usda-esmis before anything is sent.

    Args:
        since: The earliest release date to keep, e.g. ``2026-01-01`` (a date); ``None``
            (the default) keeps every release and walks every page.
        until: The latest release date to keep, e.g. ``2026-06-30`` (a date); ``None``
            (the default) keeps every release up to the latest.
    """
    answer = await esmis.list_releases_async(PUBLICATION, since=since, until=until)
    meta = ResultMeta(
        source=SOURCE,
        endpoint=answer.meta.endpoint,
        retrieved_at=answer.meta.retrieved_at,
        request={name: value for name, value in (("since", since), ("until", until)) if value},
        total=answer.meta.total,
    )
    return Result(data=[_release(release) for release in answer.data], meta=meta)


async def _narrative(release: Release, request: dict[str, object]) -> Result[list[str]]:
    """The release's narrative: its XLS's sheet ``WASDE Text``, else its PDF's pages.

    The XLS where the release has one; its PDF where it has none, or where its XLS holds no
    narrative and it has a PDF (https://github.com/xippios/sdk-usda-wasde/pull/5; sdk-core
    ADR-0020 decision 4). Each file is downloaded into a temporary directory, which is
    removed.
    """
    formats = {file.format for file in release.files}
    with tempfile.TemporaryDirectory(prefix="xippios-usda-wasde-") as directory:
        if "xls" in formats:
            dest = Path(directory) / "release.xls"
            downloaded = await esmis.download_release_file_async(
                int(release.id), format="xls", dest=dest
            )
            try:
                rows = parse_wasde_xls(dest)
            except NotFoundError as error:
                if "pdf" not in formats:
                    raise NotFoundError(
                        f"{downloaded.meta.endpoint} of release {release.id} holds no "
                        f"narrative, and the release has no PDF file (its formats: "
                        f"{_formats(release)}): {error}",
                        source=SOURCE,
                    ) from None
            else:
                return Result(
                    data=[row.text for row in rows], meta=_meta(downloaded, release, request)
                )
        dest = Path(directory) / "release.pdf"
        downloaded = await esmis.download_release_file_async(
            int(release.id), format="pdf", dest=dest
        )
        pages = parse_wasde_pdf(dest)
    return Result(data=[page.text for page in pages], meta=_meta(downloaded, release, request))


async def get_report_text_async(year: int, month: int) -> Result[list[str]]:
    r"""The narrative of a month's WASDE release, WAOB's commodity paragraphs, as text.

    Read from the release's XLS, sheet ``WASDE Text``: one string per row that holds text,
    as printed, the first the report's number (``"WASDE - 676\r"``), 25 for October 2026.
    A release without an XLS, or whose XLS holds no such sheet while it has a PDF, is read
    from its PDF: one string per page before the one headed Interagency Commodity
    Estimates Committees, as pypdf extracts it; no figure ever comes from a PDF. The
    release is the month's latest that carries an XLS or a PDF, a month before July 2010
    among them. Requests, each tried up to 4 times: the pages of ESMIS's list from the
    newest back to the month, 25 releases a page (1 for the last two years), then the
    release and the file, 2, and 2 more where the PDF is read after an XLS without the
    sheet. A month without a release, or whose releases carry neither file, raises
    ``NotFoundError``.

    Args:
        year: The report's year, e.g. ``2026``, ``2010``.
        month: The report's month, 1 to 12, e.g. ``10``.
    """
    bounds = _month(year, month)
    release = _carrying(
        await _releases(year, month, bounds),
        ("xls", "pdf"),
        f"no WASDE release of {year}-{month:02d} has an XLS or PDF file",
    )
    return await _narrative(release, {"year": year, "month": month})


get_data = sync(get_data_async)
get_report_text = sync(get_report_text_async)
list_commodities = sync(list_commodities_async)
list_regions = sync(list_regions_async)
list_releases = sync(list_releases_async)
list_tables = sync(list_tables_async)
