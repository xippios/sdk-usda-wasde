"""Parser tests on the PDF sample of ``tests/fixtures/files/wasde_pdf/`` (ADR-0020).

The sample is the July 2010 release's PDF, whole (release 95659,
``tests/fixtures/files/README.md``). The tests assert the narrative rule's shape, never a
size and never a number: the pages from page 1 up to the one headed Interagency Commodity
Estimates Committees, their text as pypdf extracts it, and that no page after the
heading's is read. The refusals are tested on PDFs written in the test with pypdf, or on
the sample with pypdf's text extraction replaced, never on a fixture file.
"""

from pathlib import Path

import pytest
from pypdf import PageObject, PdfReader, PdfWriter
from xippios.core import ValidationError

from xippios.usda.wasde.models import WasdePdfPage
from xippios.usda.wasde.parse import parse_wasde_pdf
from xippios.usda.wasde.parse.wasde_pdf import HEADING

SAMPLE = Path(__file__).parent / "fixtures" / "files" / "wasde_pdf" / "wasde-07-09-2010.pdf"


def lines(text: str) -> list[str]:
    """A page's lines, stripped and case-folded, for the heading check."""
    return [line.strip().casefold() for line in text.splitlines()]


def test_the_narrative_runs_from_page_1_to_the_page_before_the_heading() -> None:
    pages = parse_wasde_pdf(SAMPLE)
    reader = PdfReader(SAMPLE)
    after = len(pages) + 1
    assert [page.page for page in pages] == list(range(1, after)), "consecutive from page 1"
    assert HEADING.casefold() in lines(reader.pages[after - 1].extract_text())
    for page in pages:
        assert page.text == reader.pages[page.page - 1].extract_text(), "as pypdf extracts it"
        assert HEADING.casefold() not in lines(page.text)
    assert list(WasdePdfPage.model_fields) == list(pages[0].model_dump())


def test_july_2010_prints_its_narrative_on_pages_1_to_5() -> None:
    """The heading follows the page's running header, on the line after it."""
    pages = parse_wasde_pdf(SAMPLE)
    assert [page.page for page in pages] == [1, 2, 3, 4, 5]
    assert "ISSN: 1554-9089" in pages[0].text
    assert "WHEAT:" in pages[0].text
    assert [page.text.split("\n", 1)[0].strip() for page in pages[1:]] == [
        f"WASDE-484-{number}" for number in range(2, 6)
    ]
    heading = PdfReader(SAMPLE).pages[5].extract_text().split("\n")
    assert [line.strip() for line in heading[:3]] == [
        "WASDE-484-6",
        "",
        "INTERAGENCY COMMODITY ESTIMATES COMMITTEES",
    ]


def test_no_page_after_the_headings_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tables of pages 8 to 37 are never extracted (ADR-0020 decision 4)."""
    read: list[int] = []
    extract = PageObject.extract_text

    def counted(self: PageObject, *args: object, **kwargs: object) -> str:
        read.append(1)
        return extract(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(PageObject, "extract_text", counted)
    pages = parse_wasde_pdf(SAMPLE)
    assert len(read) == len(pages) + 1, "the narrative's pages and the heading's"


def blank(tmp_path: Path, count: int) -> Path:
    """A PDF of ``count`` blank pages, without text, written with pypdf."""
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=612, height=792)
    path = tmp_path / "wasde.pdf"
    with path.open("wb") as file:
        writer.write(file)
    return path


def test_a_pdf_without_the_heading_is_refused(tmp_path: Path) -> None:
    """A scan without a text layer, or a layout the parser does not know."""
    with pytest.raises(ValidationError) as caught:
        parse_wasde_pdf(blank(tmp_path, 3))
    assert str(caught.value) == (
        "wasde.pdf: none of its 3 pages prints the heading 'Interagency Commodity Estimates "
        "Committees' on a line of its own, so where the narrative ends cannot be told"
    )


def test_the_heading_on_page_1_leaves_no_narrative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def headed(self: PageObject, *args: object, **kwargs: object) -> str:
        return "WASDE-1-1 \n \n  Interagency Commodity Estimates Committees \n"

    monkeypatch.setattr(PageObject, "extract_text", headed)
    with pytest.raises(ValidationError, match="page 1 prints the heading"):
        parse_wasde_pdf(blank(tmp_path, 2))


@pytest.mark.parametrize("content", [b"", b"not a pdf", b"%PDF-1.5\n"])
def test_a_file_that_is_no_pdf_is_refused(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "wasde.pdf"
    path.write_bytes(content)
    with pytest.raises(ValidationError, match=r"^wasde\.pdf: not a PDF pypdf reads"):
        parse_wasde_pdf(path)
