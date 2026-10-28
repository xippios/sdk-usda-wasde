"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them.

This package sends no request of its own: ESMIS's catalog and the download are
``xippios-usda-esmis``'s tasks, which it imports with their models and nothing else, never
``api/`` or ``_client`` (ADR-0021), for the publication whose ESMIS identifier is
``"wasde"``. The pace is esmis's client's, 30 requests a minute.

What every task follows:

- ``meta.source`` is this package's, ``"usda-wasde"``; ``meta.retrieved_at`` is the time
  esmis's answer arrived, for the tasks that read a file the time the file was complete.
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
- ``get_table`` and ``get_balance_sheet`` read the month's XML as ``get_release`` does,
  one download per call and nothing kept between calls, and answer a slice of its
  records with ``get_release``'s ``meta``, ``meta.request`` holding the arguments given,
  the release id and the file's URL; they are tools, ``get_table`` with a cap of its own
  (``MCP_CAPS``). The slice is checked against the packaged lists before anything is
  sent: a page ``list_tables`` lacks, a commodity ``list_commodities`` lacks, or a region
  the commodity's pages do not print, raises core's ``UnknownCode``, an
  ``InvalidRequestError``, naming the closest (core's ``closest`` on the texts, whatever
  their case). A region is matched as printed with its indent and footnote marker left
  out (gap, row 195). A slice the month's file does not hold raises ``NotFoundError``.
- ``read_report_text`` reads the narrative (ADR-0020 decision 4): the release's XLS,
  sheet ``WASDE Text`` (``parse.wasde_xls``), else its PDF's narrative pages
  (``parse.wasde_pdf``), text only. ``meta.endpoint`` is the file read,
  ``meta.vintage`` the report month the XLS prints (``"October 2026"``), ``None`` for a
  PDF, ``meta.published_at`` the release time as for ``get_release``.
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
from collections.abc import Callable, Iterable, Mapping
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from xippios.core import (
    Downloaded,
    InvalidRequestError,
    NotFoundError,
    PackagedList,
    Result,
    ResultCap,
    ResultMeta,
    UnknownCode,
    closest,
    matches,
    sync,
)
from xippios.usda.esmis import tasks as esmis
from xippios.usda.esmis.models import Release as EsmisRelease
from xippios.usda.esmis.models import ReleaseFile

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import Commodity, Region, Release, Table, WasdeXmlCell
from xippios.usda.wasde.params import PACKAGE
from xippios.usda.wasde.parse.wasde_pdf import parse_wasde_pdf
from xippios.usda.wasde.parse.wasde_xls import parse_wasde_xls
from xippios.usda.wasde.parse.wasde_xml import parse_wasde_xml

__all__ = [
    "get_balance_sheet",
    "get_latest_release",
    "get_release",
    "get_table",
    "list_commodities",
    "list_regions",
    "list_releases",
    "list_tables",
    "read_report_text",
]

# A task named here is Python-only: no tool, no route; the adapters skip it (ADR-0019 decision 4).
BULK_TASKS: frozenset[str] = frozenset({"get_release"})

# MCP_CAPS, only where a tool needs a result cap of its own, keyed by the task function's
# name (conventions §8, ADR-0016). get_table answers a whole page, and its cap is 400 rows
# or 128 KB with a note of its own (Johannes, 2026-10-28, G5). Measured on the October 2026
# XML as the tool serialises it (compact JSON, UTF-8): a WasdeXmlCell is about 1 KB, its
# page's titles and footnotes repeated on every record, so 8 of the 30 pages fit whole
# (pages 9 to 12, 17, 31, 33 and 34, at most 130,369 bytes) and the others are cut with
# the note; the most records, page 28's 364, measure 340,655 bytes, the most bytes, page
# 19's 322 records, 438,621. Every other tool keeps the default, 200 rows or 64 KB.
# get_balance_sheet's answers measured up to 245,130 bytes: of the 23 U.S. and Mexico
# matrices, U.S. Sugar (88 records, 106,826 bytes), Meats (280, 245,130) and the three U.S.
# rice matrices (40 to 60, 67,838 to 101,457) are cut, CORN's 60 records measure 65,329
# bytes; a world region's rows, 24 to 28 records, at most 38,726. read_report_text's
# answer measured 16,436 bytes. list_releases called without since answers every WASDE
# release (703 on 2026-10-28), and its docstring tells an agent to bound it; the three
# packaged lists fit whole, list_tables 30 rows, list_commodities 43 and list_regions 70,
# the largest result list_tables's 29,639 bytes of compact JSON, its footnotes included
# (October 2026).
MCP_CAPS: Mapping[str, ResultCap] = {
    "get_table": ResultCap(
        max_rows=400,
        max_bytes=131_072,
        note="get_balance_sheet answers one commodity's matrix, sliced by region on the "
        "world pages (list_commodities, list_regions); Python callers get the whole page",
    ),
}

PUBLICATION = "wasde"
"""WASDE's publication identifier in ESMIS, which esmis's release tasks take."""

FIRST_XML_RELEASE = "the first with an XML file is that of 2010-07-09 (release 95659)"
"""The earliest WASDE release ESMIS lists with an XML file, as observed on 2026-10-28
(``docs/upstream/layout.md``), for the refusal of a release without one."""

WORLD = "World"
"""The ``region`` of the world pages' matrices in the packaged commodity list."""

BY_CLASS = " by Class:"
"""What the title of a by-class table holds (page 11's ``U.S. Wheat by Class: Supply and
Use``): a breakdown of a commodity's balance sheet by class, which ``get_table``
answers, not the balance sheet itself."""

_MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
_MARKER = re.compile(r"(?:\s+\d+/)+$")
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


def _bare(region: str | None) -> str | None:
    """A region text without its indent and footnote marker, as a region slice matches it.

    ``"        European Union  5/"`` gives ``"European Union"``, ``"World  3/"`` gives
    ``"World"``; the case and the inner spaces are kept (gap, row 195).
    """
    return None if region is None else _MARKER.sub("", region.strip())


def _closest(value: str, described: Mapping[str, str]) -> list[tuple[str, str]]:
    """Up to three of ``described``'s texts close to ``value``, each with its description.

    Core's ``closest`` with each text as its own code and name: its first pass, ``value``
    upper-cased against the texts, and its second, lower-cased against the texts
    lower-cased, find a text whatever its case, ``"corn"`` giving ``CORN`` and ``Corn``,
    ``"SR12"`` giving ``sr12``.
    """
    found = closest(value, {text: text for text in described})
    return [(text, described[text]) for text, _ in found]


def _formats(release: Release) -> str:
    """The release's formats in ESMIS's order, each once, e.g. ``"pdf, txt"``."""
    return ", ".join(dict.fromkeys(file.format for file in release.files)) or "none"


def _lacking(month: str | None, what: str) -> str:
    """How a refusal opens: what was checked lacks ``what``, e.g. ``"XML file"``."""
    if month is None:
        return f"the latest WASDE release has no {what}"
    return f"no WASDE release of {month} has an {what}"


def _carrying(
    releases: list[Release], formats: tuple[str, ...], refusal: str, after: str = ""
) -> Release:
    """Of the releases checked, the latest that carries a file in one of ``formats``.

    The latest by release time, the first ESMIS lists where several share it. None is
    refused with ``NotFoundError``: ``refusal`` opens the message by what was checked
    (``_lacking``), then every release checked with its formats, then ``after``.
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


def _with_xml(releases: list[Release], refusal: str) -> Release:
    """Of the releases checked, the latest that carries an XML file; none is refused.

    The latest by release time, the first ESMIS lists where several share it (Johannes,
    2026-10-28, G5 inside PR 3): in 2010-12 and 2014-01 a later release carries a TXT or
    an ASC file only, and the month answers the earlier release's XML. ``refusal`` opens
    the message by what was checked, e.g. ``"no WASDE release of 2009-06 has an XML
    file"`` or ``"the latest WASDE release has no XML file"``.
    """
    return _carrying(
        releases, ("xml",), refusal, f" Of the WASDE releases ESMIS lists, {FIRST_XML_RELEASE}."
    )


async def _releases(month: str | None) -> list[Release]:
    """The latest release, or every release of ``month``; a month without one is refused.

    Requests: the latest release 1, or the pages of ``list_releases`` from the newest back
    to the month. ``month`` is checked before anything is sent.
    """
    if month is None:
        return [_release((await esmis.get_latest_release_async(PUBLICATION)).data)]
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
    return [_release(item) for item in listed.data]


def _file_meta(
    downloaded: Result[Downloaded],
    release: Release,
    request: dict[str, object],
    vintage: str | None,
) -> ResultMeta:
    """The meta of a task that reads a release's file (conventions §4, ADR-0020 decision 5).

    ``endpoint`` the file's name as ESMIS catalogs it, ``retrieved_at`` when it was
    complete, ``published_at`` the release time as printed, naive, ``request`` the
    arguments the task was given with the release id and the file's URL.
    """
    return ResultMeta(
        source=SOURCE,
        endpoint=downloaded.meta.endpoint,
        retrieved_at=downloaded.meta.retrieved_at,
        published_at=downloaded.meta.published_at,
        published_at_naive=downloaded.meta.published_at_naive,
        vintage=vintage,
        request={
            **request,
            "release_id": int(release.id),
            "url": downloaded.meta.request["url"],
        },
    )


async def _read_xml(month: str | None, request: dict[str, object]) -> Result[list[WasdeXmlCell]]:
    """Every record of the XML of the latest release or of ``month``'s, with its meta.

    The release is the latest, or the month's latest that carries an XML file; its XML,
    the release's first file in that format, is downloaded through esmis's
    ``download_release_file`` into a temporary directory, parsed and the directory
    removed. ``meta.vintage`` is the file's ``Report_Month``; ``request`` holds the
    arguments the task was given.
    """
    release = _with_xml(await _releases(month), _lacking(month, "XML file"))
    with tempfile.TemporaryDirectory(prefix="xippios-usda-wasde-") as directory:
        dest = Path(directory) / "release.xml"
        downloaded = await esmis.download_release_file_async(int(release.id), "xml", dest)
        records = parse_wasde_xml(dest)
    vintage = records[0].report_month if records else None
    return Result(data=records, meta=_file_meta(downloaded, release, request, vintage))


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
    return await _read_xml(month, {"month": month})


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
    and ``"    China"``. ``get_balance_sheet`` matches a region against the text
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


async def get_table_async(table: str, month: str | None = None) -> Result[list[WasdeXmlCell]]:
    """Every value of one WASDE table page, one record each, read from the release's XML file.

    ``table`` is the page as the XML names it and ``list_tables`` lists it: ``"sr12"`` is
    printed page 12, U.S. feed grains and corn, ``"sr18"`` page 18, world wheat. The
    records are ``get_release``'s for that page (``WasdeXmlCell``): each value with the
    labels its page prints, as printed, its titles and footnotes repeated on every record;
    112 on page 12 of October 2026, 364 on page 28, the most. The release is the latest,
    or the one of ``month`` with the latest release time that carries an XML file, read
    as ``get_release`` reads it: every call downloads the XML (3.4 MB for October 2026)
    through xippios-usda-esmis into a temporary directory, parses it and removes it, and
    nothing is kept between calls, so a Python caller wanting several pages of one month
    calls ``get_release`` once and keeps the records of each ``report``. The MCP tool
    returns at most 400 rows or 128 KB: a record runs to about 1 KB, so 8 of October
    2026's 30 pages come whole (pages 9 to 12, 17, 31, 33 and 34) and the others are cut,
    with a note, the world pages after about 100 rows; ``get_balance_sheet`` answers one
    commodity's matrix, sliced by region on the world pages. ``meta`` is
    ``get_release``'s: ``endpoint`` the file's name (``"wasde1026.xml"``), ``vintage`` its
    ``Report_Month`` (``"October 2026"``), ``published_at`` the release time as ESMIS
    prints it, naive, ``request`` the arguments given with the release id and the file's
    URL. Requests: as ``get_release``'s, the latest release 1 or the month's pages of
    ``list_releases``, then the release 1 and the file 1. A ``table`` ``list_tables`` does
    not name raises ``InvalidRequestError`` naming the closest pages, before anything is
    sent; a month without a release or whose releases carry no XML file raises
    ``NotFoundError``, a month not written ``"YYYY-MM"`` ``InvalidRequestError``, a file
    without the page ``NotFoundError`` and a file the parser cannot read
    ``ValidationError``.

    Args:
        table: The page as the XML names it, ``"sr"`` and its two-digit number, e.g.
            ``"sr12"`` (U.S. feed grains and corn), ``"sr24"`` (world rice), ``"sr08"``
            (world and U.S. grains); ``list_tables`` lists the 30 pages, ``"sr08"`` to
            ``"sr37"``.
        month: The release month, ``"YYYY-MM"``, e.g. ``"2026-10"``; ``None`` (the
            default) reads the latest release.
    """
    tables = PackagedList.load(PACKAGE, "table")
    pages = {row.report: row for row in tables.parse(Table, source=SOURCE)}
    if table not in pages:
        raise UnknownCode(
            "table",
            table,
            list_name="table",
            fetched=tables.fetched,
            closest=_closest(
                table,
                {
                    report: f"page {row.page}: {row.sub_report_title}"
                    for report, row in pages.items()
                },
            ),
            reason="A page is named as the XML names it, 'sr' and its two-digit printed "
            "number: page 12 is 'sr12'; list_tables lists the pages.",
            source=SOURCE,
        )
    result = await _read_xml(month, {"table": table, "month": month})
    records = [record for record in result.data if record.report == table]
    if not records:
        held = ", ".join(dict.fromkeys(record.report for record in result.data)) or "none"
        raise NotFoundError(
            f"{result.meta.endpoint} of release {result.meta.request['release_id']} holds no "
            f"page {table}; its pages: {held}",
            source=SOURCE,
        )
    return Result(data=records, meta=result.meta)


def _balance_sheet(commodity: str, region: str) -> tuple[list[Commodity], bool]:
    """The packaged matrices of ``commodity``'s balance sheet for ``region``, and the slice.

    The second value says whether the records are sliced by region, as on the world pages.
    The rule is ``get_balance_sheet``'s docstring.

    Raises:
        UnknownCode: The commodity list lacks ``commodity``, or its pages print no
            ``region``; the message names the closest.
    """
    listed = PackagedList.load(PACKAGE, "commodity")
    rows = listed.parse(Commodity, source=SOURCE)
    mine = [row for row in rows if row.commodity == commodity]
    if not mine:
        pages: dict[str, list[str]] = {}
        for row in rows:
            named = pages.setdefault(row.commodity, [])
            if f"{row.region} {row.report}" not in named:
                named.append(f"{row.region} {row.report}")
        raise UnknownCode(
            "commodity",
            commodity,
            list_name="commodity",
            fetched=listed.fetched,
            closest=_closest(commodity, {name: ", ".join(on) for name, on in pages.items()}),
            reason="A commodity is named as list_commodities prints it, its case kept: "
            "'CORN' is page 12's U.S. corn, 'Corn' the world corn of pages 22 and 23.",
            source=SOURCE,
        )
    national = [
        row
        for row in mine
        if row.region == region and row.region != WORLD and BY_CLASS not in row.table
    ]
    if national:
        return national, False
    world = [row for row in mine if row.region == WORLD]
    printed: dict[str, list[str]] = {}
    if world:
        reports = [row.report for row in world]
        regions = PackagedList.load(PACKAGE, "region")
        for text in regions.parse(Region, source=SOURCE):
            bare = _bare(text.region)
            on = printed.setdefault(bare, []) if bare else []
            on += [report for report in text.reports if report in reports and report not in on]
        printed = {bare: on for bare, on in printed.items() if on}
        if region in printed:
            return world, True
    choices = {bare: f"rows of {', '.join(on)}" for bare, on in printed.items()}
    for row in mine:
        if row.region != WORLD:
            choices[row.region] = f"{row.report} {row.matrix}"
    found = _closest(region, choices)
    raise UnknownCode(
        "region",
        region,
        list_name="region",
        fetched=listed.fetched,
        closest=found,
        hint=None if found else f"{commodity!r} is printed for {', '.join(choices)}.",
        reason=f"A region of {commodity!r} is 'United States' or 'Mexico' where it has a U.S. "
        "or Mexico matrix, else one its world pages print, as list_regions lists it, matched "
        "without its indent and footnote marker, its case kept.",
        source=SOURCE,
    )


async def get_balance_sheet_async(
    commodity: str, region: str = "United States", month: str | None = None
) -> Result[list[WasdeXmlCell]]:
    """One commodity's supply-and-use balance sheet in a WASDE release, from its XML file.

    ``commodity`` is named as ``list_commodities`` prints it, its case kept: ``"CORN"`` is
    page 12's U.S. corn, ``"Corn"`` the world corn of pages 22 and 23, ``"Wheat"`` both
    page 11 and pages 18 and 19. Where the packaged commodity list has a matrix of the
    commodity for ``region`` ``"United States"`` (the default) or ``"Mexico"``, the answer
    is every value of that matrix: page 11's ``U.S. Wheat Supply and Use`` for ``"Wheat"``
    (the matrices are told apart by their title: page 11's by-class table, ``U.S. Wheat
    by Class: Supply and Use``, a breakdown, is ``get_table("sr11")``'s), page 16's
    Mexico matrix for ``"Sugar"`` with ``"Mexico"``. Otherwise the answer is the rows of
    the commodity's world matrices, pages 18 to 30 (two pages for wheat, coarse grain,
    corn, rice and cotton, one page of three matrices for soybean, soybean meal and
    soybean oil), whose region, its indent and footnote marker left out, is ``region``
    as given, its case kept: ``"Argentina"`` matches ``"        Argentina"``, ``"World"``
    matches ``"World  3/"``. So ``"United States"`` answers the world table's United
    States rows for the commodities without a U.S. matrix under their name,
    ``"Coarse Grain"``, ``"Corn"``, ``"Rice"``, ``"Soybean"``, ``"Soybean Meal"`` and
    ``"Soybean Oil"``, and the U.S. page for ``"Wheat"`` and ``"Cotton"``. Nothing is
    mapped onto another source's names. The matrices are the packaged list's, read from
    the October 2026 release: a record is kept where its page, matrix and title are a
    matrix's. The records are ``get_release``'s (``WasdeXmlCell``), each value with the
    labels its page prints, as printed: 60 for ``"CORN"``, 280 for ``"Meats"``, 28 for
    wheat's rows of one region in October 2026. Every call downloads the month's XML (3.4
    MB for October 2026) as ``get_release`` does and keeps nothing, so a Python caller
    wanting several balance sheets of one month calls ``get_release`` once. The MCP tool
    returns at most 200 rows or 64 KB, which cut five of October 2026's U.S. matrices,
    ``"Meats"``, ``"Sugar"``, ``"TOTAL RICE"``, ``"LONG-GRAIN RICE"`` and ``"MEDIUM &
    SHORT-GRAIN RICE"``, with a note; Python callers get them whole. ``meta`` is
    ``get_release``'s, ``meta.request`` the arguments given with the release id and the
    file's URL; the requests are ``get_release``'s. A commodity ``list_commodities`` does
    not name, or a region its pages do not print, raises ``InvalidRequestError`` naming
    the closest, before anything is sent; a month without a release or without an XML
    file ``NotFoundError``, a month not written ``"YYYY-MM"`` ``InvalidRequestError``, a
    file that holds none of the matrices under the packaged titles ``NotFoundError``
    (``get_table`` answers the page as that month prints it).

    Args:
        commodity: The commodity as ``list_commodities`` prints it, e.g. ``"CORN"``,
            ``"Corn"``, ``"Wheat"``, ``"SOYBEAN MEAL"``, ``"Soybean Meal"``, ``"Sugar"``,
            ``"Meats"``.
        region: ``"United States"`` (the default) or ``"Mexico"`` for a U.S. or Mexico
            matrix, or a region of the commodity's world pages as ``list_regions`` prints
            it without its indent and footnote marker, e.g. ``"Argentina"``, ``"World"``,
            ``"European Union"``, ``"World Less China"``.
        month: The release month, ``"YYYY-MM"``, e.g. ``"2026-10"``; ``None`` (the
            default) reads the latest release.
    """
    matrices, sliced = _balance_sheet(commodity, region)
    result = await _read_xml(month, {"commodity": commodity, "region": region, "month": month})
    keys = {(row.report, row.matrix, row.table) for row in matrices}
    records = [
        record
        for record in result.data
        if (record.report, record.matrix, record.table) in keys
        and (not sliced or _bare(record.region) == region)
    ]
    if not records:
        named = "; ".join(f"{row.report} {row.matrix} {row.table!r}" for row in matrices)
        raise NotFoundError(
            f"{result.meta.endpoint} of release {result.meta.request['release_id']} holds no "
            f"record of {commodity!r}{f' for {region!r}' if sliced else ''} in {named}, as "
            f"the packaged list read them from {matrices[0].report_month}; get_table answers "
            "a page as that month prints it",
            source=SOURCE,
        )
    return Result(data=records, meta=result.meta)


async def _narrative(release: Release, request: dict[str, object]) -> Result[list[str]]:
    """The release's narrative: its XLS's sheet ``WASDE Text``, else its PDF's pages.

    The XLS where the release has one; its PDF where it has none, or where its XLS holds no
    narrative and it has a PDF. Each file is downloaded into a temporary directory, which
    is removed.
    """
    formats = {file.format for file in release.files}
    with tempfile.TemporaryDirectory(prefix="xippios-usda-wasde-") as directory:
        if "xls" in formats:
            dest = Path(directory) / "release.xls"
            downloaded = await esmis.download_release_file_async(int(release.id), "xls", dest)
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
                meta = _file_meta(downloaded, release, request, rows[0].report_month)
                return Result(data=[row.text for row in rows], meta=meta)
        dest = Path(directory) / "release.pdf"
        downloaded = await esmis.download_release_file_async(int(release.id), "pdf", dest)
        pages = parse_wasde_pdf(dest)
    meta = _file_meta(downloaded, release, request, None)
    return Result(data=[page.text for page in pages], meta=meta)


async def read_report_text_async(month: str | None = None) -> Result[list[str]]:
    r"""The narrative of a WASDE release, WAOB's commodity paragraphs, as text.

    Read from the release's XLS file, sheet ``WASDE Text``: one string per row that holds
    text, as printed, the first the report's number (``"WASDE - 676\r"``), then the
    paragraphs from ``WHEAT:`` to cotton, 25 strings and 16,004 characters for October
    2026. A release without an XLS file, or whose XLS holds no such sheet while it has a
    PDF, is read from its PDF instead: one string per narrative page, the pages before
    the one headed Interagency Commodity Estimates Committees (pages 1 to 5 in July 2010
    and October 2026), their text as pypdf extracts it; no page after that one is read,
    and no figure ever comes from a PDF. ``meta.endpoint`` is the file read
    (``"wasde1026.xls"``, ``"wasde-07-09-2010.pdf"``); ``meta.vintage`` for an XLS the
    report month its first table sheet prints in its first cell (``"October 2026"``), for
    a PDF ``None``, whose narrative prints a date only; ``meta.published_at`` the release
    time as ESMIS prints it, naive; ``meta.request`` the month given, the release id and
    the file's URL. The release is the latest, or the one of ``month`` with the latest
    release time that carries an XLS or a PDF file; every release since 2011 but
    2014-01-23 carries an XLS. Every call downloads the file and keeps nothing. Requests:
    the latest release 1, or the month's pages of ``list_releases``, 25 releases a page
    from the newest back to the month; then the release 1 and the file 1 (346 KB for
    October 2026's XLS), and 2 more where a PDF is read after an XLS without the sheet. A
    month without a release, or whose releases carry neither file (those of 1995 to 1997
    carry TXT files), raises ``NotFoundError`` naming their formats; a month not written
    ``"YYYY-MM"`` ``InvalidRequestError``; a PDF whose narrative's end cannot be told (no
    page headed Interagency Commodity Estimates Committees, as in a scan without text)
    ``ValidationError``.

    Args:
        month: The release month, ``"YYYY-MM"``, e.g. ``"2026-10"``, ``"2010-07"``;
            ``None`` (the default) reads the latest release.
    """
    lacking = _lacking(month, "XLS or PDF file")
    release = _carrying(await _releases(month), ("xls", "pdf"), lacking)
    return await _narrative(release, {"month": month})


get_balance_sheet = sync(get_balance_sheet_async)
get_latest_release = sync(get_latest_release_async)
get_release = sync(get_release_async)
get_table = sync(get_table_async)
list_commodities = sync(list_commodities_async)
list_regions = sync(list_regions_async)
list_releases = sync(list_releases_async)
list_tables = sync(list_tables_async)
read_report_text = sync(read_report_text_async)
