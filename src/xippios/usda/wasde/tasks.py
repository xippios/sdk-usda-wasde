"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them.

This package sends no request of its own: ESMIS's catalog and the download are
``xippios-usda-esmis``'s tasks, which it imports with their models and nothing else, never
``api/`` or ``_client`` (ADR-0021), for the publication whose ESMIS identifier is
``"wasde"``. The pace is esmis's client's, 30 requests a minute.

What every task follows:

- ``meta.source`` is this package's, ``"usda-wasde"``; ``meta.retrieved_at`` is the time
  esmis's answer arrived, for ``get_release`` the time the file was complete.
- The catalog tasks, ``list_releases`` and ``get_latest_release``, keep esmis's
  ``meta.endpoint``, the operationId they rest on (``esmis_api_release_findByIdentifier``),
  its ``meta.total`` and, for one release, its release time: ``meta.published_at`` is
  ``release_datetime`` as ESMIS prints it with its ``+0000`` dropped, flagged
  ``published_at_naive`` (ADR-0022), and ``meta.vintage`` the release id, as esmis's
  release tasks set them. ``meta.request`` holds the parameters the caller gave, none
  left ``None``.
- ``get_release`` reads a file (conventions §4, ADR-0020 decision 5):
  ``meta.endpoint`` is the file's name as ESMIS catalogs it (``"wasde1026.xml"``),
  ``meta.vintage`` the file's ``Report_Month`` as printed (``"October 2026"``),
  ``meta.published_at`` the release time as above, ``meta.request`` the month given, the
  release id and the file's URL. It is a bulk task, Python only (``BULK_TASKS``).
- A month is ``"YYYY-MM"``, matched on the printed date of ``release_datetime``. ESMIS
  lists one release a month since 2010 but in 2010-12, 2014-01, 2018-12 and 2019-11.
  Since 2024-12 a month WAOB reposted is one release whose files carry ``v2``
  (``wasde0626v2.xml``; ``Release.revision``) and no file of the original, so such a
  month answers its revision. Release 95621 (2013-08) lists the original's XML,
  ``ORIGwasde-08-12-2013.xml``, before the revision's, ``wasde-08-12-2013.xml``, and
  esmis's ``download_release_file`` takes the first file of a format, so
  ``get_release("2013-08")`` reads the original.
- The packaged answers: ``list_tables``, ``list_commodities`` and ``list_regions`` answer
  from ``reference/table.json``, ``commodity.json`` and ``region.json``, the lists
  ``scripts/refresh_reference.py`` read from the latest release's files, through core's
  ``PackagedList``, without a request. Their ``meta`` is ``PackagedList.meta``'s
  (ADR-0022, rule 1): ``retrieved_at`` the list's ``fetched``, ``endpoint`` the file it
  came from as catalogued (``"wasde1026.xml"``), ``vintage`` the release's
  ``Report_Month`` as printed (``"October 2026"``), which every record carries,
  ``published_at`` and ``total`` empty; ``meta.request`` holds ``search`` when given.
  ``search`` keeps a record where the text occurs in one of its fields, ignoring case
  (core's ``matches``).
"""

import calendar
import re
import tempfile
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from xippios.core import (
    InvalidRequestError,
    NotFoundError,
    PackagedList,
    Result,
    ResultMeta,
    matches,
    sync,
)
from xippios.usda.esmis import tasks as esmis
from xippios.usda.esmis.models import Release as EsmisRelease
from xippios.usda.esmis.models import ReleaseFile

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import Commodity, Region, Release, Table, WasdeXmlCell
from xippios.usda.wasde.params import PACKAGE
from xippios.usda.wasde.parse.wasde_xml import parse_wasde_xml

__all__ = [
    "get_latest_release",
    "get_release",
    "list_commodities",
    "list_regions",
    "list_releases",
    "list_tables",
]

# A task named here is Python-only: no tool, no route; the adapters skip it (ADR-0019 decision 4).
BULK_TASKS: frozenset[str] = frozenset({"get_release"})

# MCP_CAPS, only where a tool needs a result cap of its own, keyed by the task function's
# name (conventions §8, ADR-0016). None here: every tool keeps the default, 200 rows or
# 64 KB. list_releases called without since answers every WASDE release (703 on
# 2026-10-28), and its docstring tells an agent to bound it; the three packaged lists fit
# whole, list_tables 30 rows, list_commodities 43 and list_regions 70, the largest
# result list_tables's 29,639 bytes of compact JSON, its footnotes included (October 2026).

PUBLICATION = "wasde"
"""WASDE's publication identifier in ESMIS, which esmis's release tasks take."""

FIRST_XML_RELEASE = "the first with an XML file is that of 2010-07-09 (release 95659)"
"""The earliest WASDE release ESMIS lists with an XML file, as observed on 2026-10-28
(``docs/upstream/layout.md``), for the refusal of a release without one."""

_MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
_REVISION = re.compile(r"v\d+$")


def _files(release: EsmisRelease) -> list[ReleaseFile]:
    """The release's files in ESMIS's order, read from each URL as esmis's tasks read it.

    The name is the URL path's last segment as printed, the format its extension after
    the last dot, lowercased, ``""`` without one (``list_release_files``).
    """
    files = []
    for url in release.files:
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        _, dot, extension = name.rpartition(".")
        files.append(ReleaseFile(url=url, name=name, format=extension.lower() if dot else ""))
    return files


def _revision(files: list[ReleaseFile]) -> str | None:
    """The ``vN`` suffix every file name's stem carries, ``None`` when not all carry one."""
    suffixes = {
        match.group(0) if (match := _REVISION.search(file.name.rpartition(".")[0])) else None
        for file in files
    }
    return suffixes.pop() if len(suffixes) == 1 else None


def _release(release: EsmisRelease) -> Release:
    """ESMIS's release re-shaped: its id and time copied, files, revision and month parsed."""
    files = _files(release)
    return Release.project(
        release,
        files=files,
        revision=_revision(files),
        month=f"{release.release_datetime:%Y-%m}",
    )


def _month_bounds(month: str) -> tuple[date, date]:
    """The first and the last day of ``month``, ``"YYYY-MM"``; anything else is refused."""
    match = _MONTH.fullmatch(month)
    if match is None:
        raise InvalidRequestError(
            f"month must be 'YYYY-MM', a year and a month from 01 to 12, e.g. '2026-10'; "
            f"got {month!r}",
            source=SOURCE,
        )
    year, number = int(match.group(1)), int(match.group(2))
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


def _formats(release: Release) -> str:
    """The release's formats in ESMIS's order, each once, e.g. ``"pdf, txt"``."""
    return ", ".join(dict.fromkeys(file.format for file in release.files)) or "none"


def _with_xml(releases: list[Release], refusal: str) -> Release:
    """Of the releases checked, the latest that carries an XML file; none is refused.

    The latest by release time, the first ESMIS lists where several share it (Johannes,
    2026-10-28, G5 inside PR 3): in 2010-12 and 2014-01 a later release carries a TXT or
    an ASC file only, and the month answers the earlier release's XML. ``refusal`` opens
    the message by what was checked, e.g. ``"no WASDE release of 2009-06 has an XML
    file"`` or ``"the latest WASDE release has no XML file"``.
    """
    carrying = [
        release for release in releases if any(file.format == "xml" for file in release.files)
    ]
    if carrying:
        return max(carrying, key=lambda release: release.release_datetime)
    listed = "; ".join(
        f"release {release.id} ({release.release_datetime:%Y-%m-%d}) has {_formats(release)}"
        for release in releases
    )
    raise NotFoundError(
        f"{refusal}: {listed}. Of the WASDE releases ESMIS lists, {FIRST_XML_RELEASE}.",
        source=SOURCE,
    )


async def list_releases_async(
    since: date | None = None, until: date | None = None
) -> Result[list[Release]]:
    """WASDE's releases in ESMIS, newest first, each with its month, revision and files.

    Read through xippios-usda-esmis's ``list_releases`` for the publication ``"wasde"``
    (``esmis_api_release_findByIdentifier``), one request per page of 25 releases.
    ``since`` and ``until`` keep the releases whose printed release date lies between
    them, both included, and the walk of the pages stops after the first page older than
    ``since``. Without ``since`` every page is walked, 29 requests for the 703 releases
    listed on 2026-10-28 at 30 requests a minute, about a minute, and the MCP tool
    returns at most 200 rows or 64 KB: bound the call with ``since``. A release's
    ``month`` is what Python callers pass to ``get_release``; its ``revision`` is
    ``"v2"`` where WAOB reposted the month (2026-06, 2026-05, 2025-05, 2025-04, 2024-12).
    ``meta.total`` is ESMIS's count of WASDE releases before the date filter, so it can
    exceed the rows returned. A ``since`` after ``until`` raises ``InvalidRequestError``,
    refused by xippios-usda-esmis before anything is sent (its ``source`` is
    ``"usda-esmis"``).

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
        request={"since": since, "until": until},
        total=answer.meta.total,
    )
    return Result(data=[_release(release) for release in answer.data], meta=meta)


async def get_latest_release_async() -> Result[Release]:
    """The latest WASDE release in ESMIS: its id, release time, month, revision and files.

    One request through xippios-usda-esmis's ``get_latest_release`` for the publication
    ``"wasde"`` (``esmis_api_release_findByIdentifier``, page 0): the release with the
    latest ``release_datetime``, e.g. ``"796099"`` of 2026-10-09 (month ``"2026-10"``).
    ``meta.vintage`` is the release id; ``meta.published_at`` the release time as ESMIS
    prints it with its ``+0000`` dropped, flagged ``published_at_naive``: WAOB releases
    at noon Eastern while ESMIS labels the time ``+0000``, so the time is upstream's text,
    never converted.
    """
    answer = await esmis.get_latest_release_async(PUBLICATION)
    meta = ResultMeta(
        source=SOURCE,
        endpoint=answer.meta.endpoint,
        retrieved_at=answer.meta.retrieved_at,
        published_at=answer.meta.published_at,
        published_at_naive=answer.meta.published_at_naive,
        vintage=answer.meta.vintage,
    )
    return Result(data=_release(answer.data), meta=meta)


async def get_release_async(month: str | None = None) -> Result[list[WasdeXmlCell]]:
    """Every value of a WASDE release's tables, one record each, read from its XML file.

    A bulk task, Python only: neither the MCP server nor the HTTP router serves it
    (``BULK_TASKS``). The release is the latest, or the one of ``month`` with the latest
    release time that carries an XML file, the first ESMIS lists where several share it
    (in 2010-12 and 2014-01 a later release carries a TXT or an ASC file only). Its XML
    file, the release's first file in that format, is downloaded through
    xippios-usda-esmis's ``download_release_file`` into a temporary directory, parsed with
    ``parse.wasde_xml.parse_wasde_xml``, and the directory removed. A month reposted
    since 2024-12 answers its revision (``wasde0626v2.xml``); 2013-08 lists the
    original's XML first and answers the original (``ORIGwasde-08-12-2013.xml``). The
    records are the values of printed pages 8 to 37 in page order, each with the labels
    its page prints (``WasdeXmlCell``): 6543 for October 2026, 5913 table values and 630
    reliability statistics. The parser knows the layout of the October 2026 file, and
    the live test checks it against the current release nightly; an older file that
    holds an attribute or a structure the parser does not know raises
    ``ValidationError``. Requests: the latest release 1, or the
    month's pages of ``list_releases``, 25 releases a page from the newest back to the
    month (1 for a month of the last two years; all 29 for a month before 1973-09,
    which is then refused); then the release 1 and the file 1, 3.4 MB for October 2026.
    A month without a release raises ``NotFoundError`` naming the latest release's
    month, a month whose releases carry no XML file (every month before 2010-07)
    ``NotFoundError`` naming the formats they have and the first release with one, a
    month not written ``"YYYY-MM"`` ``InvalidRequestError``, and a file the parser
    cannot read ``ValidationError``.

    Args:
        month: The release month, ``"YYYY-MM"``, e.g. ``"2026-10"``, or ``"2026-06"``,
            a month WAOB reposted, whose catalog entry lists the revised file
            (``wasde0626v2.xml``); ``None`` (the default) reads the latest release.
    """
    if month is None:
        latest = _release((await esmis.get_latest_release_async(PUBLICATION)).data)
        release = _with_xml([latest], "the latest WASDE release has no XML file")
    else:
        since, until = _month_bounds(month)
        listed = await esmis.list_releases_async(PUBLICATION, since=since, until=until)
        if not listed.data:
            latest = _release((await esmis.get_latest_release_async(PUBLICATION)).data)
            raise NotFoundError(
                f"ESMIS lists no WASDE release in {month}; the latest is that of "
                f"{latest.month} (release {latest.id}, "
                f"{latest.release_datetime:%Y-%m-%d})",
                source=SOURCE,
            )
        releases = [_release(item) for item in listed.data]
        release = _with_xml(releases, f"no WASDE release of {month} has an XML file")
    with tempfile.TemporaryDirectory(prefix="xippios-usda-wasde-") as directory:
        dest = Path(directory) / "release.xml"
        downloaded = await esmis.download_release_file_async(int(release.id), "xml", dest)
        records = parse_wasde_xml(dest)
    meta = ResultMeta(
        source=SOURCE,
        endpoint=downloaded.meta.endpoint,
        retrieved_at=downloaded.meta.retrieved_at,
        published_at=downloaded.meta.published_at,
        published_at_naive=downloaded.meta.published_at_naive,
        vintage=records[0].report_month if records else None,
        request={
            "month": month,
            "release_id": int(release.id),
            "url": downloaded.meta.request["url"],
        },
    )
    return Result(data=records, meta=meta)


def _packaged[M: (Table, Commodity, Region)](
    name: str, model: type[M], search: str | None, fields: Callable[[M], Iterable[object]]
) -> Result[list[M]]:
    """The packaged list ``name``'s records that ``search`` matches, with the list's meta.

    ``meta.vintage`` is the ``report_month`` the records carry, read from the first, as
    the refresh script writes one release's month on every record.
    """
    packaged = PackagedList.load(PACKAGE, name)
    rows = packaged.parse(model, source=SOURCE)
    vintage = rows[0].report_month if rows else None
    kept = [row for row in rows if matches(search, *fields(row))]
    return Result(
        data=kept, meta=packaged.meta(SOURCE, request={"search": search}, vintage=vintage)
    )


async def list_tables_async(search: str | None = None) -> Result[list[Table]]:
    """WASDE's table pages with their titles, subtitles, footnotes and matrices, from the package.

    Answered without a request from the list the package read from the October 2026
    release's XML (``wasde1026.xml``, ``reference/table.json``): 30 pages, printed pages
    8 to 37, each with its ``report`` (``"sr12"``, the page as a ``WasdeXmlCell``'s
    ``report`` names it), its printed ``page`` number, its titles, subtitles and
    footnotes (``sub_report_footer`` to ``sub_report_footer3``) as printed, stated once
    here for the page, and its ``matrices``, the report items in document order, the
    values a ``WasdeXmlCell``'s ``matrix`` takes there (``["matrix3", "matrix4"]`` on
    page 26).
    Pages 8 to 10 hold the world and U.S. aggregates, 11 to 17 the U.S. supply and use,
    18 to 30 the world supply and use by region, 31 to 34 U.S. animal products, eggs,
    milk and dairy prices, 35 to 37 the reliability of the month's projections. A page
    WAOB changed since is as it was until the package's next refresh. ``meta.vintage``
    is the release's ``Report_Month`` (``"October 2026"``), ``meta.retrieved_at`` when
    the file was downloaded and ``meta.endpoint`` the file.

    Args:
        search: Keep the pages where this text occurs, ignoring case, in the report, the
            page number, a title, a subtitle or a matrix name, each on its own, never in
            a footnote, e.g. ``"wheat"`` (pages 11, 18 and 19), ``"sr24"``,
            ``"reliability"`` (pages 35 to 37). ``None`` (the default) keeps every page.
    """
    return _packaged(
        "table",
        Table,
        search,
        lambda row: (
            row.report,
            row.page,
            row.sub_report_title,
            row.sub_report_title2,
            row.sub_report_title3,
            row.sub_report_subtitle,
            row.sub_report_subtitle2,
            row.sub_report_subtitle3,
            *row.matrices,
        ),
    )


async def list_commodities_async(search: str | None = None) -> Result[list[Commodity]]:
    """WASDE's supply-and-use matrices with their commodities, from the packaged list.

    Answered without a request from the list the package read from the October 2026
    release's XML and XLS (``reference/commodity.json``): 43 matrices of 23 commodities,
    each with its ``commodity`` as the files print it, its ``region`` (``"United
    States"`` on the U.S. pages 11 to 17, 32 and 33, ``"Mexico"`` for page 16's second matrix,
    ``"World"`` on the world pages 18 to 30, whose matrices hold the world and its
    regions), its ``report`` and ``matrix``, which together name the matrix's
    ``WasdeXmlCell`` records, and its ``table``, the title. The XML names none of these
    matrices' commodities as a whole: only page 32's records carry a ``commodity``, one
    per row (e.g. ``"Beef"``, ``"Pork"``, ``"Broiler"``, ``"Turkey"``, ``"Red Meat &
    Poultry"``), while this list names its matrix ``"Meats"``, so ``search="beef"``
    answers nothing here: read page 32's records for its rows. On pages 12 to 15 the
    commodities are the XLS's block titles, upper case as
    printed (``"FEED GRAINS"``, ``"CORN"``, ``"SOYBEAN MEAL"``), matched to the matrices
    by position; elsewhere the title's words (``"Wheat"``, ``"Coarse Grain"``,
    ``"Meats"``, ``"Egg"``, ``"Milk"``). A world commodity spans two pages, the past
    years and the projection by month (wheat, coarse grain, corn, rice, cotton), or one
    page of three matrices (soybean, soybean meal, soybean oil). Pages 8 to 10 (the
    aggregates), 31 (quarterly production and prices), 34 (dairy prices) and 35 to 37
    (reliability) are not in the list. ``meta.vintage`` is the release's
    ``Report_Month`` (``"October 2026"``), ``meta.retrieved_at`` when the XML was
    downloaded and ``meta.endpoint`` the XML.

    Args:
        search: Keep the matrices where this text occurs, ignoring case, in the
            commodity, the region, the report, the matrix or the title, each on its own,
            e.g. ``"soybean"`` (pages 15 and 28 to 30), ``"rice"``, ``"sr13"``,
            ``"mexico"``. ``None`` (the default) keeps every matrix.
    """
    return _packaged(
        "commodity",
        Commodity,
        search,
        lambda row: (row.commodity, row.region, row.report, row.matrix, row.table),
    )


async def list_regions_async(search: str | None = None) -> Result[list[Region]]:
    """The regions WASDE's tables print, as printed, with their pages, from the packaged list.

    Answered without a request from the list the package read from the October 2026
    release's XML (``reference/region.json``): 70 distinct ``region`` texts of the world
    pages 18 to 30, page 9's cotton table and the reliability pages 35 and 36, in the
    order of their first appearance, each with its ``reports``, the pages that print it.
    A text is kept as printed, with its indent, spacing and footnote marker, as a
    ``WasdeXmlCell``'s ``region`` holds it, so a region can have several texts:
    ``"World"``, ``"World  2/"`` and ``"World  3/"``; ``"        China"``, ``"       China"``
    and ``"    China"``. A task that slices a table by region, to come, matches the text
    stripped of its indent and its footnote marker, so an agent passes ``"Argentina"`` or
    ``"World"``. The U.S. pages 11 to 17 and 31 to 34 print none. ``meta.vintage``
    is the release's ``Report_Month`` (``"October 2026"``), ``meta.retrieved_at`` when
    the XML was downloaded and ``meta.endpoint`` the XML.

    Args:
        search: Keep the regions where this text occurs, ignoring case, in the text or
            one of its pages, each on its own, e.g. ``"china"`` (four texts, World Less
            China among them), ``"european union"``, ``"sr24"`` (the regions of page 24).
            ``None`` (the default) keeps every region.
    """
    return _packaged("region", Region, search, lambda row: (row.region, *row.reports))


get_latest_release = sync(get_latest_release_async)
get_release = sync(get_release_async)
list_commodities = sync(list_commodities_async)
list_regions = sync(list_regions_async)
list_releases = sync(list_releases_async)
list_tables = sync(list_tables_async)
