r"""Cut XML samples from one WASDE release's file and record its download fixture.

The parser tests read samples of the release's XML under
``tests/fixtures/files/wasde_xml/<case>.xml``: each a verbatim cut of the file, byte for
byte, that keeps whole pages (ADR-0019 decision 5, ADR-0020 decision 6). A cut is the
file's leading bytes up to and including the root's opening tag, then each page kept
(``<srNN>`` to ``</srNN>``) with the bytes that precede it in the file, a line break and
an indent, then the bytes after the file's last page, the root's closing tag: a
well-formed document of the pages kept. Each sample stays under 256 KiB.

One run downloads the file once, through xippios-usda-esmis: the release's catalog entry
with its ``list_release_files`` task (one request), then the file's URL with one GET
through esmis's configured client, retried never, as core's recorder sends it (one
request, the whole file); a recording script may use esmis's client, the package never
does (ADR-0021). Each ``--keep`` writes one sample, named after the pages it
keeps in file order (``--keep sr12,sr37`` writes ``sr12_sr37.xml``), and prints its
provenance row for ``tests/fixtures/files/README.md``: the release id, the URL, the
bytes and sha256 of the whole file, the pages kept and the UTC time it was fetched.

``--fixture <case>`` also writes the download's replay fixture,
``tests/fixtures/download_release_file/<file>_xml.json`` (``wasde1026_xml.json``), the
exchange esmis's ``download_release_file`` task sends, recorded by core's
``fixture_from_response`` and rewritten in this script's own step before the write
(ADR-0024, decision 4): the response body becomes the sample ``<case>`` and the response
is marked ``truncated`` with the whole file's ``original_bytes`` and ``sha256``, as a
fixture whose body is not the whole answer is (ADR-0019 decision 5). Everything else is
the recorded exchange as core keeps it. The sample's escaped body keeps the fixture under
256 KiB only for a sample of about 240 KB or less.

``--sha256`` refuses to write anything when the downloaded file is not the one expected,
e.g. when WAOB reposted the release. Run from the repository root::

    uv run python scripts/cut_sample.py --release 796099 --keep sr12,sr37 \
        --keep sr08,sr35,sr36 --fixture sr08_sr35_sr36 --sha256 85e67ec8...
"""

import argparse
import dataclasses
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
from xippios.core import AsyncClient, RetryPolicy, sync
from xippios.core.testing import fixture_from_response, fixture_path
from xippios.usda.esmis import tasks as esmis
from xippios.usda.esmis._client import config

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests" / "fixtures" / "files" / "wasde_xml"
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE_DIRECTORY = "download_release_file"
"""The download fixture's directory: the task whose exchange it is (conventions §10)."""
CAP = 256 * 1024
"""The size every sample and fixture file stays under (ADR-0019)."""
OPENING = b'<Report Name="wasde">'
PAGE = re.compile(rb"<(sr\d+)>.*?</\1>", re.DOTALL)


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


def pages(content: bytes) -> tuple[int, list[Page]]:
    """The end of the root's opening tag and the file's pages, in file order."""
    head = content.index(OPENING) + len(OPENING)
    found, lead = [], head
    for match in PAGE.finditer(content, head):
        found.append(Page(match.group(1).decode("ascii"), lead, match.start(), match.end()))
        lead = match.end()
    return head, found


def cut(content: bytes, keep: Sequence[str]) -> tuple[str, bytes]:
    """The sample keeping the pages ``keep``, and its case name, the pages in file order.

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
    return "_".join(page.name for page in kept), sample


async def fetch(release_id: int) -> tuple[str, httpx.Response, datetime]:
    """The release's XML file: its URL, the response and the UTC time it arrived."""
    files = await esmis.list_release_files_async(release_id)
    xml = next((file for file in files.data if file.format == "xml"), None)
    if xml is None:
        raise SystemExit(f"release {release_id} has no XML file")
    client = AsyncClient(dataclasses.replace(config, retry=RetryPolicy(max_attempts=1)))
    response = await client.request("GET", xml.url, raise_on_error=False)
    fetched = datetime.now(UTC).replace(microsecond=0)
    if response.status_code != 200:
        raise SystemExit(f"GET {xml.name} answered HTTP {response.status_code}")
    return xml.url, response, fetched


def write_fixture(response: httpx.Response, sample: bytes, name: str) -> Path:
    """The download's replay fixture, its body the sample, marked as the cut it is."""
    recorded = fixture_from_response(response)
    content = response.content
    body = recorded.response.model_copy(
        update={
            "body": sample.decode("utf-8"),
            "body_base64": False,
            "truncated": True,
            "original_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    )
    fixture = recorded.model_copy(update={"response": body})
    stem, _, extension = name.rpartition(".")
    path = fixture_path(FIXTURES, FIXTURE_DIRECTORY, f"{stem}_{extension.lower()}")
    text = json.dumps(fixture.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if len(text.encode()) >= CAP:
        raise SystemExit(f"the fixture would be {len(text.encode())} bytes, over 256 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Download the release's XML once, write the samples and, if asked, the fixture."""
    parser = argparse.ArgumentParser(description="Cut WASDE XML samples from one release.")
    parser.add_argument("--release", type=int, required=True, help="ESMIS release id")
    parser.add_argument(
        "--keep",
        action="append",
        required=True,
        help="pages to keep in one sample, comma-separated, e.g. sr12,sr37; repeatable",
    )
    parser.add_argument("--fixture", help="the sample to record the download fixture with")
    parser.add_argument("--sha256", help="refuse to write unless the file has this sha256")
    args = parser.parse_args(argv)

    url, response, fetched = sync(fetch)(args.release)
    content = response.content
    digest = hashlib.sha256(content).hexdigest()
    if args.sha256 and digest != args.sha256:
        raise SystemExit(f"the file's sha256 is {digest}, not {args.sha256}; nothing written")
    samples = dict(cut(content, keep.split(",")) for keep in args.keep)
    oversized = {case: len(sample) for case, sample in samples.items() if len(sample) >= CAP}
    if oversized:
        raise SystemExit(f"samples over 256 KiB: {oversized}; nothing written")
    if args.fixture and args.fixture not in samples:
        raise SystemExit(f"--fixture {args.fixture} names no sample of {list(samples)}")
    SAMPLES.mkdir(parents=True, exist_ok=True)
    stamp = fetched.isoformat().replace("+00:00", "Z")
    for case, sample in samples.items():
        (SAMPLES / f"{case}.xml").write_bytes(sample)
        kept = ", ".join(case.split("_"))
        row = f"| `wasde_xml/{case}.xml` | {args.release} | {url} | {len(content)} | {digest} "
        print(f"{row}| {kept} | {stamp} |")  # noqa: T201
    if args.fixture:
        name = url.rsplit("/", 1)[-1]
        path = write_fixture(response, samples[args.fixture], name)
        print(f"fixture: {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
