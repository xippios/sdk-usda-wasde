"""``scripts/refresh_upstream.py``'s ``FETCHED.md`` and its writing, offline.

Nothing here sends a request: ``render_fetched`` and ``write_snapshot`` take what a capture
run fetched, here one row made up for the test alone, written under ``tmp_path``, never to
``docs/upstream/``. ``OBSERVED.md`` is the one file under ``docs/upstream/`` written by hand
(conventions §3, sdk-core ADR-0028): the script lists it in a row of its own where it
exists, and never writes it. A page that the snapshot's pages link and the snapshot does not
request has a row with its reason in the table ``Not fetched`` (conventions §3, sdk-core
ADR-0028 decision 6), which the script writes from ``NOT_FETCHED``. The committed
``FETCHED.md`` and the committed pages are read as they stand: the table and the prose are
the renderer's, and every page a page links is fetched or a row of ``Not fetched``.
"""

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
UPSTREAM = ROOT / "docs" / "upstream"
FETCHED = "2026-11-20T09:00:00Z"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"
CAPTURED = "## How this is captured"
FILES = "## Files and pages"
LEFT_OUT = "## Not fetched"
KINDS = ("no API documentation", "no documentation", "cited, not snapshotted", "a feed")
"""The reasons a page is not requested, as the template's ``NotFetched`` names them."""
LINK = re.compile(r"\]\(([^)]*)\)")
SOURCE = re.compile(r"^Converted by `scripts/refresh_upstream\.py` from (\S+?)[,;] ")
NOTED_URL = re.compile(r"https?://[^\s;,]+")
NOTED_PATH = re.compile(r"(?<=\s)/[\w./-]+")
CALENDAR = "https://esmis.nal.usda.gov/release-calendar"
"""The one row that no page of the snapshot links: ESMIS's release calendar, which the
snapshot names for WASDE's release dates."""


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def a_row() -> object:
    """A row of a converted ESMIS page, as a capture run makes one."""
    page = script.Page(script.DOCS_URL, "pages/page.md", note="a note")
    response = script.Response(
        url=script.DOCS_URL,
        status=200,
        body=b"<html></html>",
        etag=None,
        last_modified=None,
        redirects=(),
    )
    return script.Row(page, response, b"# Page\n")


def render(*, observed: bool) -> str:
    text: str = script.render_fetched([a_row()], FETCHED, observed)
    return text


def test_the_notes_written_by_hand_are_observed_md() -> None:
    assert script.OBSERVED == "OBSERVED.md"


def test_fetched_md_lists_observed_md_in_a_row_of_its_own() -> None:
    """Where ``OBSERVED.md`` exists, the table lists it as written by hand, fetched never."""
    text = render(observed=True)
    assert f"| OBSERVED.md | - | - | - | - | - | - | - | {HAND} |" in text.splitlines()
    joined = " ".join(text.split())
    assert "nothing here is edited by hand but `OBSERVED.md`, where it exists" in joined
    assert "layout.md" not in text


def test_fetched_md_names_no_observed_md_while_there_is_none() -> None:
    text = render(observed=False)
    assert "| OBSERVED.md |" not in text
    assert "layout.md" not in text


def test_a_snapshot_leaves_observed_md_as_written(tmp_path: Path) -> None:
    """The run writes its files and ``FETCHED.md`` and never touches the notes."""
    notes = tmp_path / "OBSERVED.md"
    notes.write_text("# What WASDE's files hold\n", encoding="utf-8")
    (tmp_path / "FETCHED.md").write_text("old\n", encoding="utf-8")
    script.write_snapshot(tmp_path, [a_row()], render(observed=True))
    assert notes.read_text(encoding="utf-8") == "# What WASDE's files hold\n"
    assert (tmp_path / "pages" / "page.md").read_bytes() == b"# Page\n"
    assert "| OBSERVED.md |" in (tmp_path / "FETCHED.md").read_text(encoding="utf-8")


def test_a_page_left_out_has_a_row_in_not_fetched() -> None:
    """The table ``Not fetched`` follows the files' table: a row per page the snapshot does
    not request, with its reason (conventions §3)."""
    lines = render(observed=True).splitlines()
    start = lines.index(LEFT_OUT)
    assert lines[start + 2 : start + 4] == [
        "| URL | HTTP | Redirects to | Reason |",
        "| --- | --- | --- | --- |",
    ]
    rows = [f"| {page.url} | (not requested) | - | {page.reason} |" for page in script.NOT_FETCHED]
    assert rows
    assert lines[start + 4 :] == [*rows, "", f"Regenerate: `{script.COMMAND}`"]
    assert lines.index(f"| OBSERVED.md | - | - | - | - | - | - | - | {HAND} |") < start


def test_fetched_md_lists_no_page_left_out_in_prose() -> None:
    """The pages left out are the table's; the prose keeps what no upstream page documents."""
    text = " ".join(render(observed=True).split())
    assert "Not snapshotted" not in text
    assert "No upstream page documents the layout of the XML, XLS or TXT files" in text


def test_every_row_of_not_fetched_gives_its_reason() -> None:
    urls = [page.url for page in script.NOT_FETCHED]
    assert len(urls) == len(set(urls))
    for page in script.NOT_FETCHED:
        assert any(kind in page.reason for kind in KINDS), page.url


def page_of(url: str) -> str:
    """The page a URL names: its fragment, which is never sent, and a trailing slash dropped,
    an escape such as ``%20`` read as its character, and USDA's CDN origin named as
    www.usda.gov, whose site it serves at the same paths."""
    url = unquote(urldefrag(url).url).rstrip("/")
    origin: str = script.ORIGIN
    usda: str = script.USDA
    return usda + url.removeprefix(origin) if url.startswith(f"{origin}/") else url


def test_no_url_of_not_fetched_holds_a_space() -> None:
    """A table cell's URL is no Markdown link, and GitHub links it only up to a space, so a
    space in a page's address is written ``%20``, which ``page_of`` reads back."""
    lines = render(observed=True).splitlines()
    rows = [line for line in lines[lines.index(LEFT_OUT) + 4 :] if line.startswith("| ")]
    urls = [row.removeprefix("| ").split(" | ")[0] for row in rows]
    assert len(urls) == len(script.NOT_FETCHED)
    assert [url for url in urls if " " in url] == []
    documents = f"{script.USDA}/sites/default/files/documents"
    assert page_of(f"{documents}/Egg%20SU%20Table.xlsx") == f"{documents}/Egg SU Table.xlsx"


def linked() -> set[str]:
    """Every page that a Markdown page of the snapshot links.

    A link starting with ``/`` is read against the site the page was served from, which its
    first line names (``CONVERSION``); a ``mailto:`` link names no page.
    """
    pages: set[str] = set()
    for path in sorted((UPSTREAM / "pages").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        source = SOURCE.match(text)
        assert source, path.name
        for link in LINK.findall(text):
            url = urljoin(source.group(1), link)
            if urlsplit(url).scheme in ("http", "https"):
                pages.add(page_of(url))
    return pages


def recorded() -> set[str]:
    """Every page the committed table of files records.

    A row's URL, and in its note each redirect's target and each address it gives for the
    same page, such as the address WAOB's pages link for the historical data page.
    """
    text = (UPSTREAM / "FETCHED.md").read_text(encoding="utf-8")
    table = text.split(FILES)[1].split(LEFT_OUT)[0]
    pages: set[str] = set()
    for line in table.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) != 9 or cells[1] in ("URL", "---", "-"):
            continue
        url, note = cells[1], cells[8]
        pages.add(page_of(url))
        pages |= {page_of(found) for found in NOTED_URL.findall(note)}
        pages |= {page_of(urljoin(url, found)) for found in NOTED_PATH.findall(note)}
    return pages


def test_every_page_the_snapshot_links_is_fetched_or_not_fetched() -> None:
    """Each page that a page of the snapshot links is recorded in the table of files or has a
    row of ``Not fetched``, never both. A folder that ``FOLDERS`` names is the row of the files
    under it; every other row is its own page's alone (conventions §3)."""
    left_out = {page_of(page.url) for page in script.NOT_FETCHED}
    folders: tuple[str, ...] = script.FOLDERS
    assert folders
    assert set(folders) <= {page.url for page in script.NOT_FETCHED}
    fetched = recorded()
    found = linked()
    assert len(found) >= 150
    assert sorted(left_out & fetched) == []
    unlisted = found - fetched - left_out
    assert sorted(url for url in unlisted if not url.startswith(folders)) == []


def still_linked(url: str, found: set[str]) -> bool:
    """Whether a row's page is linked: a folder's by a linked file under it."""
    if url in script.FOLDERS:
        return any(page.startswith(url) for page in found)
    return page_of(url) in found


def test_every_row_of_not_fetched_is_a_page_the_snapshot_links() -> None:
    """A row whose page no page of the snapshot links any more is stale, as after a release
    that drops the oldest of the release list: every row's page is linked, but the release
    calendar's (conventions §3)."""
    found = linked()
    urls = [page.url for page in script.NOT_FETCHED]
    assert CALENDAR in urls
    stale = [url for url in urls if url != CALENDAR and not still_linked(url, found)]
    assert stale == []


def captured(text: str) -> list[str]:
    """The paragraphs of ``How this is captured`` after its first, which names what
    www.usda.gov served and refused in the run."""
    section = text.split(CAPTURED)[1].split(FILES)[0]
    return section.strip("\n").split("\n\n")[1:]


def test_the_committed_fetched_md_carries_the_renderers_table_and_prose() -> None:
    """What the renderer writes from the script alone is the committed text: the table ``Not
    fetched``, the prose above the files' table but the run's answers, and the heading and
    the attribution; the rows are the capture's."""
    committed = (UPSTREAM / "FETCHED.md").read_text(encoding="utf-8")
    rendered = render(observed=True)
    assert committed[committed.index(LEFT_OUT) :] == rendered[rendered.index(LEFT_OUT) :]
    assert committed.split(CAPTURED)[0] == rendered.split(CAPTURED)[0]
    assert captured(committed) == captured(rendered)
    assert f"| OBSERVED.md | - | - | - | - | - | - | - | {HAND} |" in committed.splitlines()
