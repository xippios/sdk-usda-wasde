"""Refresh the packaged reference lists from the latest WASDE release (``/refresh-reference-data``).

WASDE packages four lists, each read from the latest release's files, never typed in,
and written with core's ``PackagedList.write`` (conventions §3, ADR-0022; decided by
Johannes on 2026-10-28, G5):

- ``reference/table.json``: one record per page of the XML (``Table``);
- ``reference/commodity.json``: one record per supply-and-use matrix of pages 11 to 30
  with its commodity (``Commodity``), on pages 12 to 15 the XLS's block title by
  position;
- ``reference/region.json``: every distinct ``region`` text of the XML (``Region``);
- ``reference/attribute.json``: every distinct ``report``, ``matrix`` and ``attribute``
  of the XML (``Attribute``), for the tasks that name a table's rows.

One run downloads the latest release's XML and XLS through xippios-usda-esmis's tasks,
as ``scripts/cut_sample.py`` does: ``get_latest_release`` (one request), then
``download_release_file`` for each file (two requests each, the release and the file):
three catalog requests and two downloads, about 3.8 MB, keyless, at esmis's pace. It
parses the XML with the package's ``parse_wasde_xml``, reads the XLS's block titles with
xlrd, and builds the lists with ``xippios.usda.wasde._vocabulary``, whose docstring
gives the rules; a file they do not fit (a page of 12 to 15 whose block titles are not
as many as its report items, a title the commodity rule cannot read) is refused, and
nothing is written. Each file's ``param`` is the parameter the list serves, its file
named after it (conventions §3); ``endpoint`` is the XML's name as ESMIS catalogs it
(``wasde1026.xml``), the file every record's ``report``, ``matrix`` and labels come
from; ``fetched`` the UTC time the XML was complete; ``note`` the provenance: the
release, its ``Report_Month``, and for the commodity list the XLS and the positional
rule. Then the provenance rows of ``reference/README.md`` are rewritten and the counts
printed.

No ``enums.py`` is generated: the four lists are tables of several fields, no value
list, so the template's ``render_enums`` step and its ``--render-only`` are dropped, as
sdk-usda-esmis drops them; ``params.PACKAGED_LISTS`` names the four files. Run from the
repository root::

    uv run python scripts/refresh_reference.py

``--keep DIR`` keeps the downloaded files in ``DIR`` with ``release.json``, what the run
learnt of them (the release, each file's name, URL and UTC time); ``--from DIR`` builds
the lists from such a directory without a request, ``fetched`` the kept time: a rule
fixed after a refused run is applied to the same files.
"""

import argparse
import json
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from xippios.core import PackagedList, UpstreamModel, ValidationError, sync
from xippios.usda.esmis import tasks as esmis

from xippios.usda.wasde import _vocabulary as vocabulary
from xippios.usda.wasde.params import PACKAGED_LISTS
from xippios.usda.wasde.parse import parse_wasde_xml
from xippios.usda.wasde.tasks import PUBLICATION

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "src/xippios/usda/wasde/reference"
README = REFERENCE / "README.md"
MANIFEST = "release.json"
FORMATS = ("xml", "xls")
PROVENANCE = re.compile(r"(\| File \| Origin \| Fetched \|\n\| --- \| --- \| --- \|\n)(?:\|.*\n)*")
"""The provenance table of ``reference/README.md``: its header kept, its rows replaced."""


@dataclass(frozen=True)
class File:
    """One downloaded file of the release.

    Attributes:
        name: The file's name as ESMIS catalogs it, e.g. ``"wasde1026.xml"``.
        url: Its URL.
        path: Where it was written, relative to the kept directory, e.g. ``"wasde.xml"``.
        retrieved_at: When it was complete, UTC, ISO 8601 with ``Z``.
    """

    name: str
    url: str
    path: str
    retrieved_at: str


@dataclass(frozen=True)
class Release:
    """What the run learnt of the release: ``release.json`` in a kept directory.

    Attributes:
        release_id: ESMIS's release id, e.g. ``"796099"``.
        release_date: The release's printed date, e.g. ``"2026-10-09"``.
        files: The downloaded files by format, ``"xml"`` and ``"xls"``.
    """

    release_id: str
    release_date: str
    files: dict[str, File]


async def download(directory: Path) -> Release:
    """The latest release's XML and XLS, written to ``directory``: five requests."""
    latest = await esmis.get_latest_release_async(PUBLICATION)
    release = latest.data
    files: dict[str, File] = {}
    for format in FORMATS:
        path = f"wasde.{format}"
        answer = await esmis.download_release_file_async(int(release.id), format, directory / path)
        files[format] = File(
            name=answer.meta.endpoint,
            url=str(answer.meta.request["url"]),
            path=path,
            retrieved_at=stamp(answer.meta.retrieved_at),
        )
    return Release(
        release_id=release.id,
        release_date=f"{release.release_datetime:%Y-%m-%d}",
        files=files,
    )


def stamp(moment: datetime) -> str:
    """A UTC time to the second, ISO 8601 with ``Z``."""
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def kept(directory: Path) -> Release:
    """The release a ``--keep`` run wrote to ``directory``."""
    path = directory / MANIFEST
    if not path.is_file():
        raise SystemExit(f"{directory} holds no {MANIFEST}: keep a run's files with --keep")
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = {format: File(**file) for format, file in payload.pop("files").items()}
    return Release(files=files, **payload)


def records(models: list[UpstreamModel]) -> list[dict[str, object]]:
    """The models under upstream's field names, for a packaged file."""
    return [model.dump_upstream() for model in models]


def build(directory: Path, release: Release) -> list[PackagedList]:
    """The four lists from the release's files in ``directory``, as their packaged files.

    Raises:
        ValidationError: The files do not fit the rules of ``_vocabulary``; nothing is
            written then.
    """
    xml, xls = release.files["xml"], release.files["xls"]
    cells = parse_wasde_xml(directory / xml.path)
    month = cells[0].report_month
    titles = vocabulary.block_titles(directory / xls.path)
    lists: dict[str, list[UpstreamModel]] = {
        "table": list(vocabulary.tables(directory / xml.path)),
        "commodity": list(vocabulary.commodities(cells, titles)),
        "region": list(vocabulary.regions(cells)),
        "attribute": list(vocabulary.attributes(cells)),
    }
    source = (
        f"Read from {xml.name} of ESMIS release {release.release_id} (released "
        f"{release.release_date}, Report_Month {month!r}), downloaded through "
        f"xippios-usda-esmis's download_release_file, complete at {xml.retrieved_at}"
    )
    counts = ", ".join(f"{report} {len(found)}" for report, found in titles.items())
    notes = {
        "table": f"{source}: one record per page element of the XML, the attributes of the "
        "page's <Report> as printed (Name, Report_Month, sub_report_title to "
        "sub_report_title3, sub_report_subtitle to sub_report_subtitle3), the number that "
        "ends page_title, and the element names of the page's report items in document "
        "order.",
        "commodity": f"{source}, and from {xls.name} of the same release, complete at "
        f"{xls.retrieved_at}: one record per report item of pages 11 to 30, its table the "
        "title parse_wasde_xml gives the item, its region the region the title starts "
        "with (U.S. as 'United States', Mexico, World). The commodity on pages 12 to 15 is "
        "the XLS's block title by position: sheet 'Page N' prints a title in column 0 of "
        "each block's header row (a row whose other cells hold market years, such as '2024/25'), "
        "in the order of the XML's report items of page N, and the Nth title is the Nth "
        "item's; the script writes only when every page has as many titles as report "
        f"items ({counts}). On pages 11 and 16 to 30 the commodity is the title's words "
        "between its region and 'Supply and Use' (a 'by Class:' before it left out), as "
        "printed.",
        "region": f"{source}: every distinct region text of the XML's records as printed, "
        "in the order of its first appearance, with the pages (Name) that print it.",
        "attribute": f"{source}: one record per distinct report, matrix and attribute of "
        "the XML's records as printed, in file order; a value without an attribute gives "
        "none.",
    }
    if sorted(lists) != sorted(PACKAGED_LISTS):
        raise SystemExit(
            f"the script builds {sorted(lists)}, params.PACKAGED_LISTS names "
            f"{sorted(PACKAGED_LISTS)}"
        )
    fetched = datetime.fromisoformat(xml.retrieved_at)
    return [
        PackagedList(
            param=name, endpoint=xml.name, fetched=fetched, note=notes[name], records=records(found)
        )
        for name, found in lists.items()
    ]


def provenance(packaged: list[PackagedList], release: Release) -> None:
    """Rewrite the provenance rows of ``reference/README.md``: file, origin, fetched."""
    xml, xls = release.files["xml"], release.files["xls"]
    origin = f"ESMIS release {release.release_id} of {release.release_date}"
    origins = {
        "table": f"`{xml.name}`, {origin}, its pages' `<Report>` attributes",
        "commodity": f"`{xml.name}` and `{xls.name}`, {origin}, the XML's report items of "
        "pages 11 to 30 and the XLS's block titles of pages 12 to 15",
        "region": f"`{xml.name}`, {origin}, its `region` texts",
        "attribute": f"`{xml.name}`, {origin}, its `attribute` texts by page and item",
    }
    rows = [
        f"| `{table.param}.json` | {origins[table.param]} ({len(table.records)} records) | "
        f"{stamp(table.fetched)} |"
        for table in packaged
    ]
    text = README.read_text(encoding="utf-8")
    text = PROVENANCE.sub(lambda match: match.group(1) + "\n".join(rows) + "\n", text, count=1)
    README.write_text(text, encoding="utf-8")


def refresh(directory: Path, *, fetch: bool) -> None:
    """Download (or read the kept files), build the lists, write them and the provenance."""
    if not PROVENANCE.search(README.read_text(encoding="utf-8")):
        raise SystemExit(f"{README.name} has no provenance table to update; nothing fetched")
    if fetch:
        release = sync(download)(directory)
        (directory / MANIFEST).write_text(
            json.dumps(asdict(release), indent=2) + "\n", encoding="utf-8"
        )
        print(f"downloaded release {release.release_id}: 5 requests")  # noqa: T201
    else:
        release = kept(directory)
    try:
        packaged = build(directory, release)
    except ValidationError as refused:
        raise SystemExit(f"{refused}; nothing written") from None
    for table in packaged:
        table.write(REFERENCE / f"{table.param}.json")
        print(f"{table.param}.json: {len(table.records)} records, fetched {stamp(table.fetched)}")  # noqa: T201
    provenance(packaged, release)
    print(f"{README.name} updated")  # noqa: T201


def main() -> None:
    """Refresh the four lists from the latest release, or from a kept run's files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--keep", type=Path, help="keep the downloaded files in this directory")
    group.add_argument(
        "--from",
        dest="source",
        type=Path,
        help="build from the files a --keep run kept here, without a request",
    )
    args = parser.parse_args()
    if args.source is not None:
        refresh(args.source, fetch=False)
    elif args.keep is not None:
        args.keep.mkdir(parents=True, exist_ok=True)
        refresh(args.keep, fetch=True)
    else:
        with tempfile.TemporaryDirectory(prefix="xippios-usda-wasde-") as directory:
            refresh(Path(directory), fetch=True)


if __name__ == "__main__":
    main()
