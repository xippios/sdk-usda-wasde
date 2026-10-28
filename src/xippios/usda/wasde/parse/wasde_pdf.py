"""Parse the narrative pages of a WASDE release's PDF file, text only (ADR-0020 decision 4).

The PDF is the whole report (``docs/upstream/layout.md``): the narrative on its first
pages, then a page that lists the Interagency Commodity Estimates Committees, the
contents, the tables of pages 8 to 37 and the back matter. This parser reads the
narrative only, with pypdf, and never a number as a figure: a figure a task returns comes
from the release's XML, XLS or TXT, or is not returned.

- **The narrative's end.** The narrative is the pages from page 1 up to, and not
  including, the first page that prints the committees' heading, ``Interagency Commodity
  Estimates Committees``, on a line of its own, its case and the spaces around it
  ignored. The page opens with its running header, ``WASDE-484-6`` in July 2010, the
  heading on the line after it (``INTERAGENCY COMMODITY ESTIMATES COMMITTEES``), so the
  rule looks for the line, not for the page's first words. July 2010 (release 95659, 40
  pages) gives pages 1 to 5; the live test checks the rule on the current release.
  Pages are read in order and none after the heading's page.
- **The pages.** One ``WasdePdfPage`` per narrative page, its number counted from 1 and
  its text as pypdf's ``extract_text()`` gives it, lines broken where pypdf breaks them;
  page 1 opens with the masthead (``ISSN: 1554-9089``, the agencies, the date). A page
  without a text layer gives ``""``.

A file pypdf cannot read raises ``ValidationError``, as does a file with no page that
prints the heading (a scan without a text layer, a layout the parser does not know) and
one that prints it on page 1, which leaves no narrative: where the narrative ends cannot
be told, and nothing is returned.
"""

from os import PathLike
from pathlib import Path
from typing import NoReturn

from pypdf import PdfReader
from xippios.core import ValidationError, XippiosError

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import WasdePdfPage

__all__ = ["HEADING", "parse_wasde_pdf"]

FILE_KIND = "wasde.pdf"
"""The file kind, as messages name it."""
HEADING = "Interagency Commodity Estimates Committees"
"""The heading of the page after the narrative, as the reports print it."""


def _refuse(message: str, raw: object) -> NoReturn:
    """Raise the family's ``ValidationError`` for the file, without a chained cause."""
    raise ValidationError(f"{FILE_KIND}: {message}", raw=raw, source=SOURCE) from None


def _headed(text: str) -> bool:
    """Whether ``text`` holds the committees' heading on a line of its own."""
    heading = HEADING.casefold()
    return any(line.strip().casefold() == heading for line in text.splitlines())


def _narrative(path: Path) -> list[WasdePdfPage]:
    """The narrative pages of the PDF at ``path``; ``parse_wasde_pdf`` is its door."""
    reader = PdfReader(path)
    pages: list[WasdePdfPage] = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if _headed(text):
            if not pages:
                _refuse(f"page 1 prints the heading {HEADING!r}: no narrative", str(path))
            return pages
        pages.append(WasdePdfPage(page=number, text=text))
    _refuse(
        f"none of its {len(pages)} pages prints the heading {HEADING!r} on a line of its own, "
        "so where the narrative ends cannot be told",
        str(path),
    )


def parse_wasde_pdf(path: str | PathLike[str]) -> list[WasdePdfPage]:
    """The narrative pages of a WASDE release's PDF file, one record per page, in order.

    The pages before the one headed Interagency Commodity Estimates Committees, their
    text as pypdf extracts it; the rules are this module's docstring.

    Args:
        path: The PDF file as ESMIS serves it, e.g. ``"wasde-07-09-2010.pdf"``.

    Raises:
        ValidationError: pypdf cannot read the file (any error it raises on it, its class
            and text named), no page prints the heading, or page 1 does. An ``OSError``,
            a file that cannot be opened, passes as raised.
    """
    try:
        return _narrative(Path(path))
    except (XippiosError, OSError):
        raise
    except Exception as error:  # pypdf raises more than its own errors on a corrupt file
        _refuse(f"not a PDF pypdf reads: {type(error).__name__}: {error}", str(path))
