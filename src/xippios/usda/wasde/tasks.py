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
  lists one release a month since 2010 but in 2010-12, 2014-01, 2018-12 and 2019-11; a
  month WAOB reposted is one release whose files carry ``v2`` (``wasde0626v2.xml``), so
  a revised month answers its revision (``Release.revision``).
"""

import calendar
import re
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from xippios.core import InvalidRequestError, NotFoundError, Result, ResultMeta, sync
from xippios.usda.esmis import tasks as esmis
from xippios.usda.esmis.models import Release as EsmisRelease
from xippios.usda.esmis.models import ReleaseFile

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import Release, WasdeXmlCell
from xippios.usda.wasde.parse.wasde_xml import parse_wasde_xml

__all__ = ["get_latest_release", "get_release", "list_releases"]

# A task named here is Python-only: no tool, no route; the adapters skip it (ADR-0019 decision 4).
BULK_TASKS: frozenset[str] = frozenset({"get_release"})

# MCP_CAPS, only where a tool needs a result cap of its own, keyed by the task function's
# name (conventions §8, ADR-0016). None here: both tools keep the default, 200 rows or
# 64 KB; list_releases called without since answers every WASDE release (703 on
# 2026-10-28), and its docstring tells an agent to bound it.

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


def _xml_file(release: Release) -> ReleaseFile:
    """The release's first XML file, the one esmis's download takes; none is refused."""
    xml = next((file for file in release.files if file.format == "xml"), None)
    if xml is None:
        formats = ", ".join(dict.fromkeys(file.format for file in release.files)) or "none"
        raise NotFoundError(
            f"WASDE release {release.id} of {release.month} "
            f"({release.release_datetime:%Y-%m-%d}) has no XML file; its formats: {formats}. "
            f"Of the WASDE releases ESMIS lists, {FIRST_XML_RELEASE}.",
            source=SOURCE,
        )
    return xml


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
    ``month`` is what ``get_release`` takes; its ``revision`` is ``"v2"`` where WAOB
    reposted the month (2026-06, 2026-05, 2025-05, 2025-04, 2024-12). ``meta.total`` is
    ESMIS's count of WASDE releases before the date filter, so it can exceed the rows
    returned.

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
    release time (the first ESMIS lists where several share it); its XML file is
    downloaded through xippios-usda-esmis's ``download_release_file`` into a temporary
    directory, parsed with ``parse.wasde_xml.parse_wasde_xml``, and the directory
    removed. The records are the values of printed pages 8 to 37 in page order, each
    with the labels its page prints (``WasdeXmlCell``): 6543 for October 2026, 5913
    table values and 630 reliability statistics. Requests: the latest release 1, or the
    month's pages of ``list_releases``, 25 releases a page from the newest back to the
    month (1 for a month of the last two years); then the release 1 and the file 1,
    3.4 MB for October 2026. A month without a release raises ``NotFoundError``
    naming the latest release's month, a release without an XML file (every release
    before 2010-07-09) ``NotFoundError`` naming the formats it has, and a month not
    written ``"YYYY-MM"`` ``InvalidRequestError``.

    Args:
        month: The release month, ``"YYYY-MM"``, e.g. ``"2026-10"``, or ``"2026-06"``,
            a month WAOB reposted, whose catalog entry lists the revised file
            (``wasde0626v2.xml``); ``None`` (the default) reads the latest release.
    """
    if month is None:
        release = _release((await esmis.get_latest_release_async(PUBLICATION)).data)
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
        release = _release(max(listed.data, key=lambda item: item.release_datetime))
    _xml_file(release)  # refused before anything is downloaded
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


get_latest_release = sync(get_latest_release_async)
get_release = sync(get_release_async)
list_releases = sync(list_releases_async)
