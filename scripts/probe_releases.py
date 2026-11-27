"""Read older and revised WASDE files with the package's readers and print what each gives.

https://github.com/xippios/sdk-usda-wasde/issues/18 asks which releases the readers read:
this probe reads one file of each release in ``PROBES``, an XML with
``parse.wasde_xml.parse_wasde_xml``, an XLS with ``parse.wasde_xls.read_block_titles``
and ``parse_wasde_xls``, and prints one line a file: the month, the file and the count of
records or the refusal. Its findings stand in ``docs/upstream/OBSERVED.md``, dated; the
parser of each older layout is https://github.com/xippios/sdk-usda-wasde/issues/19.

Requests, counted from this code: for each of the eight files, the release
(``GET /api/v1/release/findById/<id>``) and the file, 2 each, 16 in all, without a key,
sent once each through a client of this package's configuration with retries off
(``RetryPolicy(max_attempts=1)``), at ESMIS's pace of 30 a minute. The run stops at the
first request that fails, and is not sent again. ``--keep DIR`` keeps each file with a
line of ``manifest.tsv`` (the release, the URL, the bytes, the sha256 and the UTC time it
was complete); ``--from DIR`` reads the kept files again without a request. Run from the
repository root::

    uv run python scripts/probe_releases.py --keep .local/probe
    uv run python scripts/probe_releases.py --from .local/probe
"""

import argparse
import dataclasses
import hashlib
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter
from xippios.core import AsyncClient, RetryPolicy, XippiosError, sync
from xippios.usda.esmis.models import ReleaseResults

from xippios.usda.wasde._client import config
from xippios.usda.wasde.parse.wasde_xls import parse_wasde_xls, read_block_titles
from xippios.usda.wasde.parse.wasde_xml import parse_wasde_xml


@dataclasses.dataclass(frozen=True)
class Probe:
    """One file to read: its release, its format or name, and why it is read.

    Attributes:
        release: The ESMIS release id, e.g. ``95659``.
        month: The release's month as its printed date reads, e.g. ``"2010-07"``.
        format: The file's format, ``"xml"`` or ``"xls"``.
        name: The file's name where the release lists several of the format, else ``None``.
        why: What the file tells, for the printed line.
    """

    release: int
    month: str
    format: str
    name: str | None
    why: str


PROBES = (
    Probe(95659, "2010-07", "xml", None, "the first XML"),
    Probe(95659, "2010-07", "xls", None, "the first XML's workbook"),
    Probe(95646, "2011-07", "xml", None, "a year the sampling did not read"),
    Probe(95621, "2013-08", "xml", "ORIGwasde-08-12-2013.xml", "the original of a revised month"),
    Probe(95607, "2014-10", "xml", None, "a year the sampling did not read"),
    Probe(95533, "2020-10", "xml", None, "a latest.* name, a year the sampling did not read"),
    Probe(95483, "2024-12", "xml", None, "the first reposted month, v2"),
    Probe(96165, "2025-05", "xml", None, "a reposted month, v2"),
)
"""The files read, eight, two requests each: 16, the maintainer's count of 2026-11-27."""

REQUESTS = 2 * len(PROBES)
"""The requests one run sends: the release and the file for each probe."""


def _file(probe: Probe) -> str:
    """The name a kept file goes under: the release, then the format."""
    return f"{probe.release}_{probe.format}.{probe.format}"


async def _fetch(probe: Probe, directory: Path, client: AsyncClient) -> str:
    """The release's file, written to ``directory``; its manifest line."""
    answer = await client.request("GET", f"/api/v1/release/findById/{probe.release}")
    (release,) = TypeAdapter(ReleaseResults).validate_python(answer.json()).results
    files = release.release_files()
    chosen = next(
        file
        for file in files
        if file.format == probe.format and (probe.name is None or file.name == probe.name)
    )
    dest = directory / _file(probe)
    await client.download(chosen.url, dest)
    complete = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content = dest.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    return f"{probe.release}\t{chosen.name}\t{chosen.url}\t{len(content)}\t{digest}\t{complete}"


def _read(probe: Probe, path: Path) -> str:
    """The probe's line: the month, the file and what the reader gives or refuses."""
    head = f"{probe.month} {probe.release} {probe.format} ({probe.why}):"
    try:
        if probe.format == "xml":
            records = parse_wasde_xml(path)
            sources = Counter(record.commodity_source for record in records)
            return f"{head} {len(records)} records, commodity sources {dict(sources)}"
        titles = read_block_titles(path)
        try:
            narrative = f"{len(parse_wasde_xls(path))} narrative rows"
        except XippiosError as error:
            narrative = f"no narrative: {error}"
        return f"{head} block titles {titles}; {narrative}"
    except XippiosError as error:
        return f"{head} refused: {type(error).__name__}: {error}"


async def _fetch_all(directory: Path) -> tuple[list[str], str | None]:
    """Every probe's file fetched once into ``directory``, the run's lines and its stop.

    The manifest's lines, and the refusal that stopped the run, if one did.
    """
    client = AsyncClient(dataclasses.replace(config, retry=RetryPolicy(max_attempts=1)))
    lines: list[str] = []
    for probe in PROBES:
        try:
            lines.append(await _fetch(probe, directory, client))
        except XippiosError as error:
            return lines, f"stopped at release {probe.release}: {type(error).__name__}: {error}"
    return lines, None


def main(argv: Sequence[str] | None = None) -> int:
    """Fetch the files once (``--keep``) or read kept ones (``--from``); print a line each."""
    parser = argparse.ArgumentParser(description="Read older and revised WASDE files.")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--keep", type=Path, help="fetch the files into this directory")
    where.add_argument("--from", dest="source", type=Path, help="read files kept before")
    args = parser.parse_args(argv)
    directory: Path = args.keep or args.source
    if args.keep:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"sending {REQUESTS} requests, each once")  # noqa: T201
        lines, stopped = sync(_fetch_all)(directory)
        (directory / "manifest.tsv").write_text("".join(f"{line}\n" for line in lines))
        if stopped:
            print(stopped)  # noqa: T201
            return 1
    for probe in PROBES:
        print(_read(probe, directory / _file(probe)))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
