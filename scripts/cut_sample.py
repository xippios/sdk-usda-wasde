r"""Cut samples from one WASDE release's file and record its download fixture.

The parser tests read samples of a release's files under
``tests/fixtures/files/<file_kind>/<case>.<ext>``, each under 256 KiB (ADR-0019 decision
5, ADR-0020 decision 6). One run reads one file of one release, ``--format``:

- ``xml`` (the default): ``wasde_xml/<case>.xml``, a verbatim cut of the file, byte for
  byte, that keeps whole pages. A cut is the file's leading bytes up to and including the
  root's opening tag, then each page kept (``<srNN>`` to ``</srNN>``) with the bytes that
  precede it in the file, a line break and an indent, then the bytes after the file's last
  page, the root's closing tag: a well-formed document of the pages kept. Each ``--keep``
  writes one sample, named after the pages it keeps in file order (``--keep sr12,sr37``
  writes ``sr12_sr37.xml``).
- ``xls``: ``wasde_xls/<case>.xls``, the sheets ``--sheet`` names, in that order, copied
  cell by cell into a new workbook written with xlwt: every cell that holds a value, at
  its row and column, with its type (text, number, boolean) and its value as xlrd reads
  them; no formatting, no merged cells, no other sheet. A cut-off binary file cannot be
  read (conventions §10), so the sample is rewritten; before anything is written the copy
  is read back with xlrd and compared with the original, cell for cell. It is named after
  the sheets kept, snake_cased (``--sheet "WASDE Text" --sheet "Page 8"`` writes
  ``wasde_text_page_8.xls``).
- ``pdf``: ``wasde_pdf/<name>``, the file kept whole, named as ESMIS names it
  (``wasde-07-09-2010.pdf``).

Each sample's provenance row for ``tests/fixtures/files/README.md`` is printed: the release
id, the URL, the bytes and sha256 of the whole file, what was kept and the UTC time it was
fetched.

One run downloads the file once, through xippios-usda-esmis: the release's catalog entry
with its ``list_release_files`` task (one request), then the first of its files in the
format, the one esmis's ``download_release_file`` picks, with one GET through esmis's
configured client, retried never, as core's recorder sends it (one request, the whole
file); a recording script may use esmis's client, the package never does (ADR-0021).

``--fixture <case>`` also writes the download's replay fixture,
``tests/fixtures/download_release_file/<file>_<ext>.json`` (``wasde1026_xml.json``), or the
case ``--case`` names, the exchange esmis's ``download_release_file`` task sends, recorded
by core's ``fixture_from_response`` (a binary body stored base64, ``allow_binary``). Where
the sample ``<case>`` is not the whole file, the script rewrites the fixture in its own
step before the write (ADR-0024, decision 4): the response body becomes the sample and
the response is marked ``truncated`` with the whole file's ``original_bytes`` and
``sha256``, as a fixture whose body is not the whole answer is (ADR-0019 decision 5).
Everything else is the recorded exchange as core keeps it. The fixture file escapes its
body, so an XML sample of about 240 KB or less, or a binary one of about 190 KB or less
in base64, keeps it under 256 KiB; a larger one is refused.

``--sha256`` refuses to write anything when the downloaded file is not the one expected,
e.g. when WAOB reposted the release. Run from the repository root::

    uv run python scripts/cut_sample.py --release 796099 --keep sr12,sr37 \
        --keep sr08,sr35,sr36 --fixture sr08_sr35_sr36 --sha256 85e67ec8...
    uv run python scripts/cut_sample.py --release 796099 --keep sr11,sr24 \
        --fixture sr11_sr24 --case wasde1026_xml_sr11_sr24 --sha256 85e67ec8...
    uv run python scripts/cut_sample.py --release 796099 --format xls \
        --sheet "WASDE Text" --sheet "Page 8" --fixture wasde_text_page_8 --sha256 5beb5732...
    uv run python scripts/cut_sample.py --release 95659 --format pdf \
        --fixture wasde-07-09-2010
"""

import argparse
import base64
import dataclasses
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import xlrd
import xlwt
from xippios.core import AsyncClient, RetryPolicy, sync
from xippios.core.testing import Scrub, fixture_from_response, fixture_path
from xippios.usda.esmis import tasks as esmis
from xippios.usda.esmis._client import config

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "tests" / "fixtures" / "files"
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE_DIRECTORY = "download_release_file"
"""The download fixture's directory: the task whose exchange it is (conventions §10)."""
KINDS = {"xml": "wasde_xml", "xls": "wasde_xls", "pdf": "wasde_pdf"}
"""Each format's file kind, the directory of its samples under ``tests/fixtures/files/``."""
CAP = 256 * 1024
"""The size every sample and fixture file stays under (ADR-0019)."""
OPENING = b'<Report Name="wasde">'
PAGE = re.compile(rb"<(sr\d+)>.*?</\1>", re.DOTALL)
COPIED = {xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_BOOLEAN}
"""The cell types the XLS copy keeps. An empty or blank cell holds no value to copy, nor
does a text cell holding no character, which xlwt writes as a blank one; a date or an
error cell is refused, since xlwt would write neither back as read."""

type Cells = dict[tuple[int, int], tuple[int, object]]
"""A sheet's cells that hold a value: type and value by row and column, from 0."""


@dataclasses.dataclass(frozen=True)
class Page:
    """One page of the file: its name and where its element and its lead-in sit.

    Attributes:
        name: The page's element name, e.g. ``"sr12"``.
        lead: Where the bytes before the element start: the end of the previous page,
            or of the root's opening tag for the first.
        start: Where the element starts, at ``<srNN>``.
        end: Where it ends, after ``</srNN>``.
    """

    name: str
    lead: int
    start: int
    end: int


@dataclasses.dataclass(frozen=True)
class Sample:
    """One sample to write: its case, its bytes and what it keeps of the file.

    Attributes:
        case: The sample's name without its extension, e.g. ``"sr12_sr37"``.
        content: The sample's bytes.
        kept: What it keeps, for the provenance row, e.g. ``"sr12, sr37"``.
    """

    case: str
    content: bytes
    kept: str


def pages(content: bytes) -> tuple[int, list[Page]]:
    """The end of the root's opening tag and the file's pages, in file order."""
    head = content.index(OPENING) + len(OPENING)
    found, lead = [], head
    for match in PAGE.finditer(content, head):
        found.append(Page(match.group(1).decode("ascii"), lead, match.start(), match.end()))
        lead = match.end()
    return head, found


def cut(content: bytes, keep: Sequence[str]) -> Sample:
    """The XML sample keeping the pages ``keep``, named after them in file order.

    Raises:
        SystemExit: A page the file does not hold, or a cut that is not well-formed.
    """
    head, found = pages(content)
    by_name = {page.name: page for page in found}
    unknown = [name for name in keep if name not in by_name]
    if unknown:
        raise SystemExit(f"the file holds no page {unknown}; it holds {list(by_name)}")
    kept = [page for page in found if page.name in keep]
    sample = content[:head]
    sample += b"".join(content[page.lead : page.end] for page in kept)
    sample += content[found[-1].end :]
    ET.fromstring(sample)  # well-formed, or ParseError
    names = [page.name for page in kept]
    return Sample("_".join(names), sample, ", ".join(names))


def cells(sheet: xlrd.sheet.Sheet) -> Cells:
    """Every cell of ``sheet`` that holds a value, by row and column.

    Raises:
        SystemExit: A cell of a type the copy does not keep (a date, an error).
    """
    found: Cells = {}
    for row in range(sheet.nrows):
        for column, cell in enumerate(sheet.row(row)):
            if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) or cell.value == "":
                continue
            if cell.ctype not in COPIED:
                kind = xlrd.sheet.ctype_text.get(cell.ctype, cell.ctype)
                raise SystemExit(
                    f"sheet {sheet.name!r}, row {row}, column {column}: a {kind} cell, which "
                    "the copy does not keep; nothing written"
                )
            found[(row, column)] = (cell.ctype, cell.value)
    return found


def snake(name: str) -> str:
    """A sheet's name as a case's words, e.g. ``"WASDE Text"`` gives ``"wasde_text"``."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def copy_sheets(content: bytes, names: Sequence[str]) -> Sample:
    """The XLS sample: the sheets ``names`` copied cell by cell into a workbook of xlwt's.

    Raises:
        SystemExit: A sheet the workbook lacks, a cell the copy does not keep, or a copy
            that reads back other than the original.
    """
    originals: dict[str, Cells] = {}
    workbook = xlwt.Workbook()
    with xlrd.open_workbook(file_contents=content, logfile=io.StringIO(), on_demand=True) as book:
        missing = [name for name in names if name not in book.sheet_names()]
        if missing:
            raise SystemExit(f"the workbook has no sheet {missing}; it has {book.sheet_names()}")
        for name in names:
            originals[name] = cells(book.sheet_by_name(name))
            target = workbook.add_sheet(name)
            for (row, column), (ctype, value) in originals[name].items():
                target.write(row, column, bool(value) if ctype == xlrd.XL_CELL_BOOLEAN else value)
    buffer = io.BytesIO()
    workbook.save(buffer)
    sample = buffer.getvalue()
    with xlrd.open_workbook(file_contents=sample, logfile=io.StringIO()) as copy:
        if copy.sheet_names() != list(names):
            raise SystemExit(f"the copy has the sheets {copy.sheet_names()}, not {list(names)}")
        for name in names:
            copied = cells(copy.sheet_by_name(name))
            differ = sorted(
                place
                for place in originals[name].keys() | copied.keys()
                if originals[name].get(place) != copied.get(place)
            )
            if differ:
                raise SystemExit(
                    f"the copy of sheet {name!r} reads back other than the original in "
                    f"{len(differ)} cells, the first at (row, column) {differ[:5]}; nothing written"
                )
    kept = ", ".join(names)
    return Sample(
        "_".join(snake(name) for name in names),
        sample,
        f"sheets {kept}, copied cell by cell (values and types, no formatting) into a workbook "
        "written with xlwt",
    )


async def fetch(release_id: int, format: str) -> tuple[str, httpx.Response, datetime]:
    """The release's first file in ``format``: its URL, the response and when it arrived."""
    files = await esmis.list_release_files_async(release_id)
    chosen = next((file for file in files.data if file.format == format), None)
    if chosen is None:
        formats = ", ".join(dict.fromkeys(file.format for file in files.data)) or "none"
        raise SystemExit(f"release {release_id} has no {format} file; its formats: {formats}")
    client = AsyncClient(dataclasses.replace(config, retry=RetryPolicy(max_attempts=1)))
    response = await client.request("GET", chosen.url, raise_on_error=False)
    fetched = datetime.now(UTC).replace(microsecond=0)
    if response.status_code != 200:
        raise SystemExit(f"GET {chosen.name} answered HTTP {response.status_code}")
    return chosen.url, response, fetched


def write_fixture(response: httpx.Response, sample: bytes, case: str, *, binary: bool) -> Path:
    """The download's replay fixture: the recorded exchange, its body the sample.

    A sample that is the whole file leaves the exchange as recorded; another becomes the
    body, marked as the cut it is, with the whole file's size and sha256.
    """
    recorded = fixture_from_response(response, scrub=Scrub(allow_binary=binary))
    content = response.content
    fixture = recorded
    if sample != content:
        body = base64.b64encode(sample).decode("ascii") if binary else sample.decode("utf-8")
        rewritten = recorded.response.model_copy(
            update={
                "body": body,
                "body_base64": binary,
                "truncated": True,
                "original_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        fixture = recorded.model_copy(update={"response": rewritten})
    path = fixture_path(FIXTURES, FIXTURE_DIRECTORY, case)
    text = json.dumps(fixture.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if len(text.encode()) >= CAP:
        raise SystemExit(f"the fixture would be {len(text.encode())} bytes, over 256 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Download the release's file once, write the samples and, if asked, the fixture."""
    parser = argparse.ArgumentParser(description="Cut WASDE samples from one release's file.")
    parser.add_argument("--release", type=int, required=True, help="ESMIS release id")
    parser.add_argument("--format", choices=sorted(KINDS), default="xml", help="the file read")
    parser.add_argument(
        "--keep",
        action="append",
        help="xml: pages to keep in one sample, comma-separated, e.g. sr12,sr37; repeatable",
    )
    parser.add_argument(
        "--sheet", action="append", help="xls: a sheet to keep, e.g. 'WASDE Text'; repeatable"
    )
    parser.add_argument("--fixture", help="the sample to record the download fixture with")
    parser.add_argument("--case", help="the fixture's case; <file>_<ext> by default")
    parser.add_argument("--sha256", help="refuse to write unless the file has this sha256")
    args = parser.parse_args(argv)
    if bool(args.keep) != (args.format == "xml"):
        parser.error("--keep goes with --format xml, which needs it")
    if bool(args.sheet) != (args.format == "xls"):
        parser.error("--sheet goes with --format xls, which needs it")

    url, response, fetched = sync(fetch)(args.release, args.format)
    content = response.content
    digest = hashlib.sha256(content).hexdigest()
    if args.sha256 and digest != args.sha256:
        raise SystemExit(f"the file's sha256 is {digest}, not {args.sha256}; nothing written")
    name = url.rsplit("/", 1)[-1]
    stem, _, extension = name.rpartition(".")
    if args.format == "xml":
        samples = [cut(content, keep.split(",")) for keep in args.keep]
    elif args.format == "xls":
        samples = [copy_sheets(content, args.sheet)]
    else:
        samples = [Sample(stem, content, "the whole file")]
    by_case = {sample.case: sample for sample in samples}
    oversized = {
        sample.case: len(sample.content) for sample in samples if len(sample.content) >= CAP
    }
    if oversized:
        raise SystemExit(f"samples over 256 KiB: {oversized}; nothing written")
    if args.fixture and args.fixture not in by_case:
        raise SystemExit(f"--fixture {args.fixture} names no sample of {list(by_case)}")
    directory = FILES / KINDS[args.format]
    directory.mkdir(parents=True, exist_ok=True)
    stamp = fetched.isoformat().replace("+00:00", "Z")
    for sample in samples:
        file = f"{sample.case}.{extension.lower()}"
        (directory / file).write_bytes(sample.content)
        row = f"| `{KINDS[args.format]}/{file}` | {args.release} | {url} | {len(content)} "
        print(f"{row}| {digest} | {sample.kept} | {stamp} |")  # noqa: T201
    if args.fixture:
        case = args.case or f"{stem}_{extension.lower()}"
        binary = args.format != "xml"
        path = write_fixture(response, by_case[args.fixture].content, case, binary=binary)
        print(f"fixture: {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
