# /// script
# requires-python = ">=3.12"
# dependencies = ["markdownify==1.2.3"]
# ///
"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

The World Agricultural Supply and Demand Estimates (WASDE) are documented on two sites:
ESMIS, the National Agricultural Library's catalog of USDA reports, which publishes the
release files, and the World Agricultural Outlook Board's pages on www.usda.gov, which
describe the report, its release dates, its changes and its historical data. www.usda.gov
answers 403 at its CDN edge to an automated request for some of its pages; such a page is
recorded by its status and kept from USDA's CDN origin, usda.azureedge.us, which serves
the same Drupal site (``UsdaPage``). The script writes:

- ``pages/publication-wasde.md``: the ESMIS publication page, converted to Markdown;
- ``pages/release-wasde.md``: the ESMIS page of the newest release, the first row of the
  publication page's release list, converted to Markdown;
- ``pages/wasde-report.md``, ``pages/about-wasde.md``, ``pages/wasde-faqs.md``,
  ``pages/historical-changes-revisions.md`` and ``pages/historical-wasde-report-data.md``:
  WAOB's WASDE page and the four pages its menu links, converted to Markdown;
- ``New_WASDE_Filename_Format.pdf``: WAOB's 2018 notice of the file names, byte for byte;
- ``FETCHED.md``: regenerated whole, one row per file and per page recorded without a
  file, and a row for ``layout.md``, which is written by hand from release files, not
  fetched, and which this script neither writes nor checks.

Everything is fetched before anything is written, one request at a time after a pause,
each URL retried at most once after a network error or a 5xx. ``FETCHED.md`` records the
UTC time of the run with an explicit ``Z``, the attribution, and one row per page with its
HTTP status, the size and sha256 of the body as fetched, and its ETag and Last-Modified
where sent; a page recorded by its status only (a 403 or a 404) has a row without them.
Files under ``pages/`` the run does not produce are removed; nothing else under
``docs/upstream/`` is touched. Every run stops, before writing, when the visible text of
an HTML page states a copyright, a licence or terms of use that ``ATTRIBUTION`` does not
record, and on a page the converter does not recognise. No key is needed or read. Run from
the repository root::

    uv run scripts/refresh_upstream.py            # fetch, then write the snapshot
    uv run scripts/refresh_upstream.py --check    # fetch and compare; write nothing

``--check`` exits 1 when the snapshot differs from what upstream serves now, ``Fetched``
aside. HTML is converted to Markdown with ``markdownify``, the one converter a capture
script may declare: in the ``# /// script`` block above, and at the same pin in the dev
group of ``pyproject.toml``, so that ``mypy --strict`` reads its types.
"""

import argparse
import hashlib
import http.client
import json
import re
import textwrap
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlsplit

from markdownify import ATX, BACKSLASH, MarkdownConverter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs/upstream"
COMMAND = "uv run scripts/refresh_upstream.py"
SOURCE_NAME = "USDA WAOB World Agricultural Supply and Demand Estimates"
DOCS_URL = "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"
"""Where the documentation lives: ``upstream_docs_url`` in ``.copier-answers.yml``."""
USER_AGENT = "xippios-usda-wasde refresh_upstream (+https://github.com/xippios)"
TIMEOUT = 60.0
PAUSE = 2.0
"""Seconds before every request; requests never run in parallel."""
RETRY_PAUSE = 10.0
"""Seconds before the one retry after a network error or a 5xx."""

USDA = "https://www.usda.gov"
"""The canonical site of WAOB's pages; its CDN edge answers 403 to this script."""
ORIGIN = "https://usda.azureedge.us"
"""USDA's CDN origin: the Drupal site that www.usda.gov fronts, served without the edge."""
RELEASE_FILE = "pages/release-wasde.md"
LAYOUT_FILE = "layout.md"
"""Written by hand from release files (ADR-0020 decision 2); listed, never written here."""


@dataclass(frozen=True)
class Page:
    """One page the snapshot records, and the file it is kept as, if any.

    Attributes:
        url: Where the page is fetched from.
        file: Its path under ``docs/upstream/`` (``pages/wasde-faqs.md``), or ``None`` for
            a page recorded without a file.
        status: The HTTP status it must answer with: 200, or the 403 or 404 of a page
            recorded by its status.
        note: The row's note in ``FETCHED.md``: how the file was made, or why there is none.
        stable: ``False`` for a page recorded by its status only: its row records no
            size, sha256 or validators, and its note says why.
        excerpt: The file is this source's part of a shared document (conventions §3);
            the row keeps the whole document's size and sha256, and its note says so.
        title: The text of the page's one ``<h1>``, for a page converted to Markdown; the
            run stops when the page serves another.
        canonical: For a page kept from USDA's CDN origin, the www.usda.gov URL it is
            the copy of; the Markdown file names both.
    """

    url: str
    file: str | None = None
    status: int = 200
    note: str = ""
    stable: bool = True
    excerpt: bool = False
    title: str | None = None
    canonical: str | None = None


@dataclass(frozen=True)
class UsdaPage:
    """A WAOB page on www.usda.gov, whose CDN edge refuses this script some pages.

    The run asks www.usda.gov first. Where it answers 200, the page is kept from there and
    has one row. Where it answers 403, that URL gets a row by its status and the page is
    kept from the same path on USDA's CDN origin, the row after it (Johannes, 2026-10-28).

    Attributes:
        path: The page's path, the same on www.usda.gov and on USDA's CDN origin.
        file: Its path under ``docs/upstream/``: Markdown for a page, the original for a PDF.
        what: What it is, for the notes (``WAOB's WASDE page``).
        title: The text of its one ``<h1>``, for a page converted to Markdown.
        more: Added to the note of the row that keeps the file.
    """

    path: str
    file: str
    what: str
    title: str | None = None
    more: str = ""

    @property
    def url(self) -> str:
        """The page's canonical URL, on www.usda.gov."""
        return f"{USDA}{self.path}"


_CONVERTED = "converted to Markdown; Bytes and sha256 are the HTML page's"
_DENIED = (
    "403 Access Denied at the CDN edge; the body carries a per-request reference, so "
    "status only; kept from USDA's CDN origin in the next row"
)
_WASDE_REPORT = (
    "/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets"
    "/wasde-report"
)

PAGES: tuple[Page | UsdaPage, ...] = (
    Page(
        DOCS_URL,
        "pages/publication-wasde.md",
        note=f"{_CONVERTED}; the first page of the release list, which changes with "
        "every release; the next row is its first row's View link",
        title="World Agricultural Supply and Demand Estimates",
    ),
    UsdaPage("/oce/commodity/wasde", "pages/wasde-report.md", "WAOB's WASDE page", "WASDE Report"),
    UsdaPage(
        f"{_WASDE_REPORT}/about-wasde",
        "pages/about-wasde.md",
        "About WASDE, from the WASDE page's menu",
        "About WASDE",
    ),
    UsdaPage("/node/33540", "pages/wasde-faqs.md", "WAOB's WASDE FAQ", "FAQs and Resources"),
    UsdaPage(
        f"{_WASDE_REPORT}/historical-changes-revisions",
        "pages/historical-changes-revisions.md",
        "Historical Changes & Revisions, from the WASDE page's menu",
        "Historical Changes & Revisions",
        more="; the files it links are not fetched",
    ),
    UsdaPage(
        "/node/42884",
        "pages/historical-wasde-report-data.md",
        "WAOB's historical data page",
        "Historical WASDE Report Data",
        more="; the address WAOB's pages link, /oce/commodity-markets/wasde/"
        "historical-wasde-report-data, led to the same page on USDA's CDN origin on "
        "2026-10-28; the data files it links are not fetched",
    ),
    UsdaPage(
        "/sites/default/files/documents/New_WASDE_Filename_Format.pdf",
        "New_WASDE_Filename_Format.pdf",
        "WAOB's notice of the file names (2018)",
    ),
    Page(
        "http://www.usda.gov/oce/commodity/wasde/WASDE-Schema.xsd",
        status=404,
        stable=False,
        note="the XML schema the July 2010 XML file names in `xsi:schemaLocation`; "
        "www.usda.gov's page-not-found page, status only",
    ),
)
"""Every page the snapshot records, in the order of ``FETCHED.md``'s rows.

The ESMIS page of the newest release follows the publication page; its URL is read from
the publication page on every run (``latest_release``). A ``UsdaPage`` has one row or two,
as www.usda.gov answers (``capture_usda``).
"""

SPEC_URL: str | None = None
"""The machine-readable API document (OpenAPI, Swagger) the documentation names: none.

The convention of ``/refresh-upstream``: a document named inside a page rather than linked
from it (a Swagger UI's configuration) is recorded here once found, and kept verbatim as
``SPEC_FILE`` after ``PAGES``. ESMIS's OpenAPI document is snapshotted by xippios-usda-esmis,
whose tasks this package uses (ADR-0021).
"""
SPEC_FILE = "openapi/openapi.json"
"""The document's path under ``docs/upstream/``, with the extension it is served with."""

ATTRIBUTION: tuple[str, ...] = ()
"""Every copyright line, licence or terms of use the documentation states, as printed.

Empty: the visible text of the HTML pages states none. ``FETCHED.md`` says so under
Attribution, and every run stops when a page states one that is not here.
"""

EXIT_NOTICE = (
    "Once you access another site through a link that we provide, you are subject to the "
    "copyright and licensing restrictions of the new site."
)
"""A sentence of the notice that the usda.gov pages' settings carry for a link off the site.

``FETCHED.md``'s Attribution describes the notice; a run stops when a WAOB page kept as
Markdown no longer carries this sentence.
"""

CAPTURE = " ".join(
    (
        "The two ESMIS pages, the publication page of the World Agricultural Supply and",
        "Demand Estimates and the page of its newest release, are converted to Markdown, and",
        "so are five pages of the World Agricultural Outlook Board (WAOB): its WASDE page and",
        "the four pages that page's menu links, About WASDE, the FAQ, Historical Changes &",
        "Revisions and the historical data page. The newest release is the first row of the",
        "publication page's release list, read from its View link on every run; the run",
        "stops when that row is not the page's Latest Release. www.usda.gov answers 403",
        "Access Denied at its CDN edge to an automated request for some of WAOB's pages. The",
        "script asks www.usda.gov first: a page it serves is kept from there, and a page it",
        "refuses is recorded by its status at its www.usda.gov URL and kept from",
        f"{ORIGIN}, the CDN origin that www.usda.gov fronts, which serves the same Drupal site",
        "at the same paths; the canonical URL is the www.usda.gov one, and each Markdown file",
        "kept from the CDN origin names both. The 2018 notice of the file names is kept byte",
        "for byte as a PDF; the script does not read its text, so a change to it shows in its",
        "sha256.",
    )
)
"""``FETCHED.md``'s "How this is captured": what is converted, cut or left out, and why."""

CONVERSION = " ".join(
    (
        "The Markdown is `markdownify`'s rendering of the page's `<main>` element, with",
        "headings in ATX style. Breadcrumbs, menus and the other navigation, forms (the",
        "release list's date filter), buttons, images and icons, share links and",
        "screen-reader-only text are dropped; a `<time>` keeps its `datetime` attribute in",
        "parentheses after its text, a link with a `type` attribute (an ESMIS release file's",
        "media type) keeps it in parentheses after the link, two links side by side get a",
        "space between them, a no-break space becomes a space, an emphasis holding only",
        "spaces becomes a space, and a line break that ends a paragraph is dropped; trailing",
        "spaces are removed. Links are kept as the page prints them: a link starting with `/`",
        "is relative to the site the page was served from, which for WAOB's pages is",
        "www.usda.gov as well.",
        "No table on these pages has merged cells or a nested table; the run stops on one, and",
        "on a page whose `<h1>` is not the one the script expects. The ESMIS pages change with",
        "every release.",
    )
)
"""How a page becomes Markdown, for ``FETCHED.md``."""

LEFT_OUT = " ".join(
    (
        "Not snapshotted: ESMIS's release calendar, which xippios-usda-esmis keeps as an",
        "excerpt; the data files the historical data page links (CSV, ZIP); the release",
        "files themselves. No upstream page documents the layout of the XML, XLS or TXT",
        f"files: `{LAYOUT_FILE}` describes them as observed in release files, by hand, and",
        "says what it was written from; its row records no fetch.",
    )
)
"""What the snapshot leaves out, for ``FETCHED.md``."""

_STATEMENT = re.compile(
    r"\N{COPYRIGHT SIGN}|copyright|licen[cs]e|terms of (?:use|service)|public domain",
    re.IGNORECASE,
)
_FETCHED = re.compile(r"\| (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) \|")
_VIEW = re.compile(
    r'<a href="(/publication/world-agricultural-supply-and-demand-estimates/'
    r'(\d{4}-\d{2}-\d{2})(?:-\d+)?)"[^>]*>View</a>'
)
_LATEST_BLOCK = "block-views-blockpublication-releases-latest-release-block"
_DATETIME = re.compile(r'<time datetime="(\d{4}-\d{2}-\d{2})T[^"]*"')
_NO_TEXT = frozenset({"script", "style", "template"})
"""Elements whose content a reader never sees as text."""
_DROP_TAGS = frozenset(
    {"nav", "form", "button", "img", "svg", "iframe", "script", "style", "noscript", "template"}
)
_DROP_CLASSES = frozenset({"usa-sr-only", "visually-hidden", "share"})


@dataclass
class _Tally:
    """HTTP requests sent by this run, redirects and retries included."""

    requests: int = 0


_TALLY = _Tally()


@dataclass(frozen=True)
class Response:
    """One GET as served: status, body and validators, and the redirects on the way."""

    url: str
    status: int
    body: bytes
    etag: str | None
    last_modified: str | None
    redirects: tuple[tuple[int, str], ...]

    @property
    def served_url(self) -> str:
        """The URL the body came from: the last redirect's target, or the URL asked for."""
        return self.redirects[-1][1] if self.redirects else self.url


@dataclass(frozen=True)
class Row:
    """One row of ``FETCHED.md``: the page, its response and its file's content, if any."""

    page: Page
    response: Response
    content: bytes | None


class _RetryableError(Exception):
    """A network error or a 5xx: worth one more attempt."""


class _RecordRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects as urllib does, remembering each status and target."""

    def __init__(self) -> None:
        super().__init__()
        self.hops: list[tuple[int, str]] = []

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Record the hop, then let urllib build the follow-up request."""
        self.hops.append((code, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


def _get(url: str, expect: tuple[int, ...]) -> Response:
    redirects = _RecordRedirects()
    opener = urllib.request.build_opener(redirects)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body: bytes = response.read()
            status: int = response.status
            headers = response.headers
    except urllib.error.HTTPError as error:
        if error.code >= 500:
            raise _RetryableError(f"HTTP {error.code} {error.reason}") from None
        if error.code not in expect:
            raise SystemExit(f"GET {url}: HTTP {error.code} {error.reason}") from None
        body, status, headers = error.read(), error.code, error.headers
    except (http.client.HTTPException, OSError) as error:  # URLError is an OSError
        raise _RetryableError(str(error)) from None
    finally:
        _TALLY.requests += 1 + len(redirects.hops)
    if status not in expect:
        raise SystemExit(f"GET {url}: expected HTTP {' or '.join(map(str, expect))}, got {status}")
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding != "identity":
        raise SystemExit(f"GET {url}: unexpected Content-Encoding {encoding!r}")
    return Response(
        url,
        status,
        body,
        headers.get("ETag"),
        headers.get("Last-Modified"),
        tuple(redirects.hops),
    )


def fetch(url: str, expect: int | tuple[int, ...] = 200) -> Response:
    """GET ``url`` after a polite pause; retry once on a network error or a 5xx.

    ``expect`` is the status, or the statuses, the URL may answer with; another stops the
    run.
    """
    expect = (expect,) if isinstance(expect, int) else expect
    time.sleep(PAUSE)
    try:
        response = _get(url, expect)
    except _RetryableError as error:
        _log(f"  {url}: {error}; retrying once in {RETRY_PAUSE:g} s")
        time.sleep(RETRY_PAUSE)
        try:
            response = _get(url, expect)
        except _RetryableError as error:
            raise SystemExit(f"GET {url}: {error} (after one retry)") from None
    digest = hashlib.sha256(response.body).hexdigest()
    hops = "".join(f", {code} to {target}" for code, target in response.redirects)
    _log(
        f"  {url}: HTTP {response.status}{hops}, {len(response.body)} bytes, sha256 {digest}, "
        f"Last-Modified {response.last_modified or '-'}, ETag {response.etag or '-'}"
    )
    return response


def changed(url: str, what: str) -> SystemExit:
    """The error that stops the run on a page the script does not recognise."""
    return SystemExit(
        f"{url} changed: {what}.\nLook at the page by hand and update "
        "scripts/refresh_upstream.py. Nothing was written."
    )


def decode(response: Response) -> str:
    """The body as UTF-8 text; a body that is not UTF-8 stops the run."""
    try:
        return response.body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise changed(response.url, f"the body is not UTF-8 ({error})") from None


def _is_html(page: Page) -> bool:
    return page.file is None or page.file.endswith(".md")


class _VisibleText(HTMLParser):
    """The text a reader sees: every text node outside scripts, styles and templates."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Enter a script, a style or a template."""
        if tag in _NO_TEXT:
            self._hidden += 1

    def handle_endtag(self, tag: str) -> None:
        """Leave a script, a style or a template."""
        if tag in _NO_TEXT and self._hidden:
            self._hidden -= 1

    def handle_data(self, data: str) -> None:
        """Keep visible text."""
        if not self._hidden:
            self.parts.append(data)


def visible_text(text: str) -> str:
    """The visible text of an HTML document, entities decoded, whitespace collapsed."""
    parser = _VisibleText()
    parser.feed(text)
    parser.close()
    return " ".join("".join(parser.parts).split())


def check_attribution(page: Page, response: Response) -> None:
    """Stop when the page states a copyright, licence or terms that ``ATTRIBUTION`` lacks.

    The check reads the visible text of an HTML page, its header and footer included and
    its scripts left out: a link's URL (``sort=CopyrightDate``) and the usda.gov pages'
    settings, which carry the exit notice ``FETCHED.md`` describes, are not statements of
    the page's own terms. A WAOB page kept as Markdown, from either host, must still
    carry ``EXIT_NOTICE``. The PDF is binary and its text is not read; its sha256 tells a change.
    """
    if not _is_html(page):
        return
    raw = decode(response)
    body = visible_text(raw)
    for statement in ATTRIBUTION:
        body = body.replace(statement, "")
    match = _STATEMENT.search(body)
    if match:
        around = body[max(match.start() - 60, 0) : match.end() + 60]
        raise SystemExit(
            f"GET {page.url}: the page states {match.group(0)!r} ({around!r}), a copyright, "
            "licence or terms of use that ATTRIBUTION does not record.\nRead it by hand, "
            "record it in ATTRIBUTION and update scripts/refresh_upstream.py. Nothing was "
            "written."
        )
    usda = urlsplit(page.url).netloc in {urlsplit(USDA).netloc, urlsplit(ORIGIN).netloc}
    if usda and page.file and EXIT_NOTICE not in raw:
        raise changed(page.url, "the settings no longer carry the exit notice EXIT_NOTICE quotes")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    counts = Counter(key for key, _ in pairs)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate keys {duplicates}")
    return dict(pairs)


def dump_json(value: Any, indent: int = 2) -> bytes:
    """``value`` as JSON in the order it holds, ``ensure_ascii=False``, with a final newline."""
    return (json.dumps(value, indent=indent, ensure_ascii=False) + "\n").encode("utf-8")


def load_json(response: Response, indent: int = 2) -> Any:
    """The JSON document of ``response``, once re-serialising it reproduces the fetched text.

    A source that keeps a JSON document cut to its part writes the part with ``dump_json``;
    this check makes sure that the whole document, written the same way, is the fetched
    text up to line endings, so the part is an excerpt of upstream's text. A duplicate key,
    which ``json.loads`` would drop silently, stops the run too.
    """
    try:
        document = json.loads(response.body, object_pairs_hook=_no_duplicates)
    except ValueError as error:
        raise SystemExit(f"GET {response.url}: not usable JSON ({error})") from None
    fetched = response.body.replace(b"\r\n", b"\n").rstrip(b"\n")
    if dump_json(document, indent).rstrip(b"\n") != fetched:
        raise SystemExit(
            f"GET {response.url}: re-serialised with json.dumps(indent={indent}, "
            "ensure_ascii=False), the document no longer reproduces the fetched text up to "
            "line endings, so a part cut from it would not be an excerpt of upstream's text."
            "\nLook at the document by hand and update scripts/refresh_upstream.py. Nothing "
            "was written."
        )
    return document


def _dropped(tag: Any) -> bool:
    classes = tag.get("class") or []
    return tag.name in _DROP_TAGS or not _DROP_CLASSES.isdisjoint(classes)


class _Markdown(MarkdownConverter):
    """``markdownify``'s converter for one page: its ``<main>``, navigation dropped.

    ``convert_soup`` is ``markdownify``'s hook for a parsed document; this one picks the
    ``<main>`` element, checks it and prepares it as ``CONVERSION`` describes before the
    converter renders it.
    """

    def __init__(self, page: Page) -> None:
        super().__init__(heading_style=ATX, bullets="-", newline_style=BACKSLASH)
        self.page = page

    def convert_soup(self, soup: Any) -> str:
        """Render the page's one ``<main>``, prepared; stop on one the script does not know."""
        url = self.page.url
        mains = soup.find_all("main")
        if len(mains) != 1:
            raise changed(url, f"expected one <main>, found {len(mains)}")
        main = mains[0]
        for element in main.find_all(True):
            if not element.decomposed and _dropped(element):
                element.decompose()
        headings = [" ".join(h1.get_text().split()) for h1 in main.find_all("h1")]
        if headings != [self.page.title]:
            raise changed(url, f"the <h1> is {headings}, not [{self.page.title!r}]")
        for table in main.find_all("table"):
            cells = table.find_all(["td", "th"])
            if table.find_all("table") or any(c.get("rowspan") or c.get("colspan") for c in cells):
                raise changed(
                    url,
                    "a table with merged cells or a nested table, which this script does not "
                    "convert yet; extend it to keep such a table as HTML (conventions §3)",
                )
        for moment in main.find_all("time", datetime=True):
            moment.append(f" (`{moment['datetime']}`)")
        for link in main.find_all("a", type=True):
            link.insert_after(f" (`{link['type']}`)")
        for link in main.find_all("a"):
            if getattr(link.next_sibling, "name", None) == "a":
                link.insert_after(" ")
        for text in main.find_all(string=lambda value: "\N{NO-BREAK SPACE}" in value):
            text.replace_with(text.replace("\N{NO-BREAK SPACE}", " "))
        for emphasis in main.find_all(["strong", "b", "em", "i"]):
            if emphasis.get_text() and not emphasis.get_text().strip():
                emphasis.replace_with(" ")
        for brk in main.find_all("br"):
            if all(isinstance(after, str) and not after.strip() for after in brk.next_siblings):
                brk.decompose()
        return super().convert_soup(main)


def markdown(page: Page, response: Response) -> bytes:
    """The page as Markdown: a line naming where it came from, then its ``<main>``."""
    body = _Markdown(page).convert(decode(response))
    lines = [line.rstrip() for line in body.strip("\n").splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    source = response.served_url
    if page.canonical:
        source += f", which USDA's CDN origin serves for {page.canonical}"
    header = f"Converted by `scripts/refresh_upstream.py` from {source}; see `../FETCHED.md`."
    return f"{header}\n\n{text}\n".encode()


def latest_release(response: Response) -> Page:
    """The ESMIS page of the newest release: the first row of the publication's release list.

    The row's View link gives the URL; the run stops unless its date is the date of the
    page's Latest Release.
    """
    text = decode(response)
    views = _VIEW.findall(text)
    if not views:
        raise changed(response.url, "the release list has no View link")
    path, date = views[0]
    block = text.find(_LATEST_BLOCK)
    latest = _DATETIME.search(text, block) if block >= 0 else None
    if latest is None or latest.group(1) != date:
        found = latest.group(1) if latest else None
        raise changed(
            response.url,
            f"the release list's first row ({date}) is not the Latest Release ({found}), so "
            "the newest release is unclear",
        )
    site = urlsplit(response.served_url)
    return Page(
        f"{site.scheme}://{site.netloc}{path}",
        RELEASE_FILE,
        note=f"{_CONVERTED}; the page of the newest release, the first row of the "
        "publication page's release list, so the URL changes with every release",
        title="World Agricultural Supply and Demand Estimates",
    )


def reduce(page: Page, response: Response) -> bytes:
    """The content ``page``'s file is written with: Markdown for HTML, else the body as fetched.

    ``markdown`` stops the run with ``changed`` on a page it does not recognise, before
    anything is written.
    """
    if page.file and page.file.endswith(".md"):
        return markdown(page, response)
    return response.body


def capture(page: Page) -> Row:
    """Fetch ``page``, check its attribution and make its file's content; write nothing."""
    response = fetch(page.url, page.status)
    check_attribution(page, response)
    return Row(page, response, reduce(page, response) if page.file else None)


def capture_usda(page: UsdaPage) -> list[Row]:
    """Capture a WAOB page from www.usda.gov, or from USDA's CDN origin where it is refused.

    One row where www.usda.gov serves the page; where it answers 403, a row for that answer
    by its status and a row for the same path on the CDN origin, which must answer 200.
    """
    response = fetch(page.url, (200, 403))
    markdown_file = page.file.endswith(".md")
    how = _CONVERTED if markdown_file else "verbatim, byte for byte"
    if response.status == 200:
        served = Page(
            page.url,
            page.file,
            note=f"{how}; {page.what}, served by www.usda.gov itself, so no CDN-origin row"
            f"{page.more}",
            title=page.title,
        )
        check_attribution(served, response)
        return [Row(served, response, reduce(served, response))]
    refused = Page(page.url, status=403, stable=False, note=f"{page.what}; {_DENIED}")
    check_attribution(refused, response)
    copy = "page" if markdown_file else "document"
    kept = Page(
        f"{ORIGIN}{page.path}",
        page.file,
        note=f"{how}; the {copy} above, from USDA's CDN origin{page.more}",
        title=page.title,
        canonical=page.url,
    )
    return [Row(refused, response, None), capture(kept)]


def capture_all(pages: Sequence[Page | UsdaPage]) -> list[Row]:
    """Capture every page in order, the newest release's page after the publication page."""
    rows: list[Row] = []
    for page in pages:
        if isinstance(page, UsdaPage):
            rows += capture_usda(page)
            continue
        rows.append(capture(page))
        if page.url == DOCS_URL:
            rows.append(capture(latest_release(rows[-1].response)))
    return rows


def _iso_http_date(value: str | None) -> str:
    if value is None:
        return "-"
    return parsedate_to_datetime(value).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cell(value: str) -> str:
    return value.replace("|", r"\|")


def _paragraph(*sentences: str) -> list[str]:
    text = " ".join(sentences)
    wrapped = textwrap.fill(text, width=88, break_long_words=False, break_on_hyphens=False)
    return [*wrapped.splitlines(), ""]


def _note(row: Row) -> str:
    parts = [f"redirected ({code}) to {target}" for code, target in row.response.redirects]
    if row.page.excerpt:
        parts.append("excerpt of a shared document; Bytes and sha256 are the whole document's")
    if row.page.note:
        parts.append(row.page.note)
    return "; ".join(parts) or "-"


def _attribution() -> list[str]:
    if ATTRIBUTION:
        stated = "The documentation states " + "; ".join(f"`{s}`" for s in ATTRIBUTION) + "."
    else:
        stated = (
            "The visible text of the HTML pages this script reads, their headers and footers "
            "included, states no copyright line, licence or terms of use; the WASDE FAQ, read "
            "for terms of use and a citation wording, states neither."
        )
    return _paragraph(
        "The documentation and the release files are works of the United States Government",
        "(USDA: the World Agricultural Outlook Board, https://www.usda.gov, and the National",
        "Agricultural Library's ESMIS, https://esmis.nal.usda.gov), in the public domain in",
        "the United States under 17 U.S.C. \N{SECTION SIGN} 105.",
        stated,
        "The script stops when a page it reads starts to state one. The 2018 notice of the",
        "file names, a PDF whose text the script does not read, stated none either when this",
        "snapshot was set up (2026-10-28). The usda.gov pages carry in their settings the",
        "notice a browser shows when a reader follows a link off the site; it says that the",
        "linked site's copyright and licensing restrictions apply there",
        f'("{EXIT_NOTICE}") and states nothing about USDA\'s own pages; the script stops if',
        "it goes. The documentation's text is reproduced here as this package's reference",
        "(ADR-0003); the publisher's objection is met by replacing it with a summary that",
        "keeps the names and semantics the package relies on.",
    )


def _usda_answers(rows: Sequence[Row]) -> str:
    """Which WAOB pages www.usda.gov served in this run, and which it refused."""
    served: list[str] = []
    refused: list[str] = []
    for row, after in zip(rows, [*rows[1:], None], strict=True):
        if not row.page.url.startswith(USDA):
            continue
        if row.response.status == 200 and row.page.file:
            served.append(f"`{row.page.file}`")
        elif row.response.status == 403 and after and after.page.canonical == row.page.url:
            refused.append(f"`{after.page.file}`")
    kept = f"{', '.join(refused)}, which are kept from the CDN origin" if refused else "none"
    return (
        f"In this run www.usda.gov served {', '.join(served) or 'none'} itself and refused {kept}."
    )


def render_fetched(rows: Sequence[Row], fetched: str) -> str:
    """The whole of ``FETCHED.md``, ``fetched`` being the UTC time the run started."""
    lines = [
        f"# Upstream documentation snapshot \N{EM DASH} {SOURCE_NAME}",
        "",
        *_paragraph(
            "Source of truth for every endpoint wrapper and parser (ADR-0003, ADR-0020). The",
            "files in this directory are written by `scripts/refresh_upstream.py`",
            "(`/refresh-upstream`) from the pages in the table below and refreshed",
            "deliberately by PR, so that changes show up as diffs. This file is generated by",
            "the same script; nothing here is edited by hand except",
            f"`{LAYOUT_FILE}`, the file layouts as observed, which its row describes.",
        ),
        "## Attribution",
        "",
        *_attribution(),
        "## How this is captured",
        "",
        *_paragraph(CAPTURE, _usda_answers(rows)),
        *_paragraph(CONVERSION),
        *_paragraph(LEFT_OUT),
        *_paragraph(
            "Fetched is the UTC time the run started, in ISO 8601 with an explicit Z, the",
            "same for every row. Bytes and sha256 are those of the body as fetched: a",
            "converted page's row holds the HTML page's. Last-Modified is the HTTP header in",
            "UTC, ETag as sent; Drupal sets both to the time it last rendered the page, so",
            "they change with a new rendering of the same page. A page recorded without a",
            "file is `(no file)`, and one recorded by its status only, a 403 whose body",
            "carries a per-request reference or a page-not-found page, has no size, sha256",
            f"or validators. Requests go one at a time, {PAUSE:g} s apart, each retried at",
            f"most once, identified as `{USER_AGENT}`; no API key is sent or read.",
        ),
        "## Files and pages",
        "",
        "| File | URL | Fetched | HTTP | Bytes | sha256 | ETag | Last-Modified | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        response, kept = row.response, row.page.stable
        cells = [
            row.page.file or "(no file)",
            response.url,
            fetched,
            str(response.status),
            str(len(response.body)) if kept else "-",
            hashlib.sha256(response.body).hexdigest() if kept else "-",
            (response.etag or "-") if kept else "-",
            _iso_http_date(response.last_modified) if kept else "-",
            _note(row),
        ]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    layout = [
        LAYOUT_FILE,
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "written by hand from release files, not fetched: the file layouts as observed, "
        "not documented (ADR-0020 decision 2); the file says what it was written from",
    ]
    lines.append("| " + " | ".join(layout) + " |")
    lines += ["", f"Regenerate: `{COMMAND}`"]
    return "\n".join(lines) + "\n"


def _files(rows: Sequence[Row]) -> dict[str, bytes]:
    return {row.page.file: row.content for row in rows if row.page.file and row.content is not None}


def _stale(out: Path, files: dict[str, bytes]) -> list[str]:
    """The files under the subdirectories the run writes to that it does not produce."""
    subdirs = sorted({name.split("/", 1)[0] for name in files if "/" in name})
    found = [path for subdir in subdirs for path in sorted((out / subdir).rglob("*"))]
    names = [path.relative_to(out).as_posix() for path in found if path.is_file()]
    return [name for name in names if name not in files]


def write_snapshot(out: Path, rows: Sequence[Row], fetched_md: str) -> None:
    """Write every file as ``reduce`` made it, then ``FETCHED.md``; remove the stale files."""
    if out.exists() and any(out.iterdir()) and not (out / "FETCHED.md").is_file():
        raise SystemExit(f"{out} is neither empty nor a snapshot (no FETCHED.md); not writing")
    files = _files(rows)
    for name in _stale(out, files):
        (out / name).unlink()
        _log(f"  removed {name}: no longer produced")
    for name, content in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(content)
    (out / "FETCHED.md").write_bytes(fetched_md.encode("utf-8"))


def compare(out: Path, rows: Sequence[Row]) -> list[str]:
    """The snapshot's files that differ from this run's, ``FETCHED.md``'s ``Fetched`` aside."""
    files = _files(rows)
    differ = [
        name
        for name, content in files.items()
        if not (out / name).is_file() or (out / name).read_bytes() != content
    ]
    differ += [f"{name} (no longer produced)" for name in _stale(out, files)]
    current = out / "FETCHED.md"
    old = current.read_bytes().decode("utf-8") if current.is_file() else ""
    match = _FETCHED.search(old, max(old.find("| --- |"), 0))
    if not match or render_fetched(rows, match.group(1)) != old:
        differ.append("FETCHED.md")
    return differ


def main(argv: Sequence[str] | None = None) -> int:
    """Fetch every page, then write the snapshot, or with ``--check`` compare it."""
    parser = argparse.ArgumentParser(description="Refresh docs/upstream/ from upstream.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot directory")
    parser.add_argument(
        "--check", action="store_true", help="fetch and compare with the snapshot; write nothing"
    )
    args = parser.parse_args(argv)
    out: Path = args.out
    pages = list(PAGES)
    if SPEC_URL:
        pages.append(Page(SPEC_URL, SPEC_FILE, note="SPEC_URL, verbatim"))
    if not pages:
        raise SystemExit(
            "Nothing to fetch: fill PAGES, and SPEC_URL where the documentation names an "
            "API document, as /refresh-upstream says."
        )
    if not (out / LAYOUT_FILE).is_file():
        raise SystemExit(f"{out / LAYOUT_FILE} is missing; FETCHED.md lists it. Nothing fetched.")
    fetched = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _log("Fetching every page; nothing is written before the last")
    rows = capture_all(pages)
    _log(f"{_TALLY.requests} HTTP requests, redirects and retries included")
    if args.check:
        differ = compare(out, rows)
        for name in differ:
            _log(f"  differs: {name}")
        _log(
            f"{len(differ)} of the snapshot's files differ from upstream; run without --check"
            if differ
            else "The snapshot is current: upstream serves what it records."
        )
        return 1 if differ else 0
    write_snapshot(out, rows, render_fetched(rows, fetched))
    written = sum(1 for row in rows if row.content is not None)
    _log(f"Wrote {written} files and FETCHED.md under {out} (Fetched {fetched})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
