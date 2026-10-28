"""Build the four packaged lists from one WASDE release's files (conventions §3, ADR-0022).

``scripts/refresh_reference.py`` calls these on the latest release's XML and XLS and
writes what they return to ``reference/`` with ``PackagedList.write``; the live tests
call them on the current release and compare it with the packaged lists. No task calls
them: the list tasks answer from the packaged files, and the package reads no XLS at
call time.

- ``tables``: one ``Table`` per page element of the XML, ``sr08`` to ``sr37``, from the
  attributes of the page's ``<Report>`` (``Name``, ``Report_Month``, the number that ends
  ``page_title``, ``sub_report_title`` to ``sub_report_title3``, ``sub_report_subtitle``
  to ``sub_report_subtitle3``) and the element names of its report items, as printed.
- ``commodities``: one ``Commodity`` per report item of pages 11 to 30, the U.S. and the
  world supply-and-use pages, in file order. Its ``table`` is the title
  ``parse_wasde_xml`` gives the item; its ``region`` the region that title starts with,
  ``U.S.`` read as ``"United States"`` (as the world pages' rows print it), ``Mexico``
  and ``World`` as printed (Johannes, 2026-10-28, G5). Its ``commodity``, which the XML
  holds for none of these items, is on pages 12 to 15 the XLS's block title by position
  (``block_titles``): sheet ``Page N`` prints one in column 0 of each block's header row,
  in the order of the page's report items, and the Nth title goes to the Nth item. On
  the other pages it is the title's words between its region and ``Supply and Use`` (a
  ``by Class:`` before it left out), as printed: ``"Wheat"`` from ``"U.S. Wheat by Class:
  Supply and Use"``, ``"Coarse Grain"`` from ``"World Coarse Grain Supply and Use  1/"``.
- ``regions``: one ``Region`` per distinct ``region`` text of the records, in the order
  of its first appearance, with the pages that print it.
- ``attributes``: one ``Attribute`` per distinct ``report``, ``matrix`` and
  ``attribute`` of the records, in file order; a value without an ``attribute`` gives
  none.

A file these rules do not fit raises ``ValidationError`` naming the page, and the
refresh script writes nothing: a page of 11 to 30 without values, a title that does not
start with ``U.S.``, ``Mexico`` or ``World`` and name a commodity before ``Supply and
Use``, a page of 12 to 15 whose XLS block titles are not as many as its report items, a
sheet the XLS lacks, more than one ``Report_Month``, a page without a printed number.
"""

import io
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import NoReturn

import xlrd
from xippios.core import ValidationError

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import Attribute, Commodity, Region, Table, WasdeXmlCell

__all__ = [
    "BLOCK_PAGES",
    "COMMODITY_PAGES",
    "attributes",
    "block_titles",
    "commodities",
    "regions",
    "report_name",
    "tables",
]

COMMODITY_PAGES = range(11, 31)
"""The printed pages whose report items are the commodity list's: the U.S. supply-and-use
pages 11 to 17 and the world pages 18 to 30."""
BLOCK_PAGES = (12, 13, 14, 15)
"""The printed pages whose commodities are the XLS's block titles: the XML names the
commodity of none of their report items, and their titles name several
(``"U.S. Feed Grain and Corn Supply and Use  1/"``)."""
REGIONS = {"U.S.": "United States", "Mexico": "Mexico", "World": "World"}
"""A title's leading region to the ``region`` of its commodities (Johannes, 2026-10-28, G5):
``U.S.`` as the world pages' rows print the country, the others as printed."""

_TITLE = re.compile(
    r"(?P<region>U\.S\.|Mexico|World) (?P<commodity>.+?)(?: by Class:)? Supply and Use"
)
_MARKET_YEAR = re.compile(r"\d{4}/\d{2}")
_PAGE_NUMBER = re.compile(r"(\d+)\s*$")
_HEADINGS = re.compile(r"(sub_report_title|sub_report_subtitle)(\d*)")
_HEADING_NUMBERS = ("", "2", "3")


def _refuse(message: str, raw: object) -> NoReturn:
    """Raise the family's ``ValidationError`` for the release's files."""
    raise ValidationError(f"reference lists: {message}", raw=raw, source=SOURCE) from None


def report_name(page: int) -> str:
    """The XML's ``Name`` of a printed page, ``12`` giving ``"sr12"``."""
    return f"sr{page:02d}"


def _month(records: Sequence[WasdeXmlCell]) -> str:
    """The one ``Report_Month`` the records carry; none or several are refused."""
    months = list(dict.fromkeys(record.report_month for record in records))
    if len(months) != 1:
        _refuse(f"the records carry {len(months)} Report_Month values, not one", months)
    return months[0]


def tables(path: str | PathLike[str]) -> list[Table]:
    """One ``Table`` per page of the release's XML file, in page order.

    Args:
        path: The XML file as ESMIS serves it, e.g. ``"wasde1026.xml"``, one that
            ``parse_wasde_xml`` reads.

    Raises:
        ValidationError: A page lacks its ``<Report>``, its ``Name``, ``Report_Month``,
            ``page_title`` or ``sub_report_title``, a number at the end of
            ``page_title``, or carries a title or subtitle numbered beyond 3.
    """
    root = ET.parse(Path(path)).getroot()
    found: list[Table] = []
    for holder in root:
        report = holder.find("Report")
        if report is None:
            _refuse(f"<{holder.tag}> holds no <Report>", {"element": holder.tag})
        attributes = dict(report.attrib)
        missing = [
            name
            for name in ("Name", "Report_Month", "page_title", "sub_report_title")
            if name not in attributes
        ]
        if missing:
            _refuse(f"<{holder.tag}>'s <Report> lacks {missing}", {"element": holder.tag})
        name = attributes["Name"]
        beyond = [
            key
            for key in attributes
            if (match := _HEADINGS.fullmatch(key)) and match.group(2) not in _HEADING_NUMBERS
        ]
        if beyond:
            _refuse(f"{name} carries {beyond}; a table names titles and subtitles 1 to 3", beyond)
        page = _PAGE_NUMBER.search(attributes["page_title"])
        if page is None:
            _refuse(f"{name}: page_title ends in no page number", {"report": name})
        found.append(
            Table(
                report=name,
                page=int(page.group(1)),
                sub_report_title=attributes["sub_report_title"],
                sub_report_title2=attributes.get("sub_report_title2"),
                sub_report_title3=attributes.get("sub_report_title3"),
                sub_report_subtitle=attributes.get("sub_report_subtitle"),
                sub_report_subtitle2=attributes.get("sub_report_subtitle2"),
                sub_report_subtitle3=attributes.get("sub_report_subtitle3"),
                matrices=[item.tag for item in report],
                report_month=attributes["Report_Month"],
            )
        )
    return found


def block_titles(path: str | PathLike[str]) -> dict[str, list[str]]:
    """The XLS's block titles of pages 12 to 15, by the page's ``Name``, in sheet order.

    Sheet ``Page N`` of the release's XLS prints a title in column 0 of each block's
    header row, the row whose other cells hold the market years (``"2024/25"``,
    ``"2025/26 Est."``): ``FEED GRAINS`` and ``CORN`` on ``Page 12``. A title is that
    cell's text verbatim, read with xlrd.

    Args:
        path: The XLS file as ESMIS serves it, e.g. ``"wasde1026.xls"``.

    Raises:
        ValidationError: The workbook lacks a sheet ``Page 12`` to ``Page 15``.
    """
    with xlrd.open_workbook(str(Path(path)), logfile=io.StringIO(), on_demand=True) as book:
        sheets = book.sheet_names()
        found: dict[str, list[str]] = {}
        for page in BLOCK_PAGES:
            name = f"Page {page}"
            if name not in sheets:
                _refuse(f"the XLS has no sheet {name!r}", sheets)
            sheet = book.sheet_by_name(name)
            titles: list[str] = []
            for row in range(sheet.nrows):
                cells = sheet.row(row)
                if not cells or cells[0].ctype != xlrd.XL_CELL_TEXT:
                    continue
                label = str(cells[0].value)
                if label.strip() and any(
                    cell.ctype == xlrd.XL_CELL_TEXT and _MARKET_YEAR.search(str(cell.value))
                    for cell in cells[1:]
                ):
                    titles.append(label)
            found[report_name(page)] = titles
    return found


def commodities(
    records: Sequence[WasdeXmlCell], titles: Mapping[str, Sequence[str]]
) -> list[Commodity]:
    """One ``Commodity`` per report item of pages 11 to 30, in file order.

    Args:
        records: Every record of the release's XML, as ``parse_wasde_xml`` reads it.
        titles: The XLS's block titles by page, as ``block_titles`` reads them, e.g.
            ``{"sr12": ["FEED GRAINS", "CORN"], ...}``.

    Raises:
        ValidationError: A page of 11 to 30 has no values; an item's title does not
            start with ``U.S.``, ``Mexico`` or ``World`` and name a commodity before
            ``Supply and Use``; a page of 12 to 15 has no block titles, or not as many as
            report items. The message names the page.
    """
    items: dict[str, dict[str, str]] = {}
    for record in records:
        items.setdefault(record.report, {}).setdefault(record.matrix, record.table)
    month = _month(records)
    found: list[Commodity] = []
    for page in COMMODITY_PAGES:
        report = report_name(page)
        on_page = items.get(report)
        if not on_page:
            _refuse(f"{report} has no values; the commodity list reads pages 11 to 30", report)
        blocks: Sequence[str] = ()
        if page in BLOCK_PAGES:
            blocks = titles.get(report, ())
            if len(blocks) != len(on_page):
                _refuse(
                    f"{report}: the XLS sheet 'Page {page}' prints {len(blocks)} block titles "
                    f"for the XML's {len(on_page)} report items {list(on_page)}; the "
                    "commodity of the Nth item is the Nth title, so the counts must match",
                    {"report": report, "titles": list(blocks), "matrices": list(on_page)},
                )
        for index, (matrix, table) in enumerate(on_page.items()):
            match = _TITLE.match(table)
            if match is None:
                _refuse(
                    f"{report} {matrix}: the title {table!r} does not start with U.S., Mexico "
                    "or World and name a commodity before 'Supply and Use'",
                    {"report": report, "matrix": matrix, "table": table},
                )
            found.append(
                Commodity(
                    commodity=blocks[index] if blocks else match.group("commodity"),
                    region=REGIONS[match.group("region")],
                    report=report,
                    matrix=matrix,
                    table=table,
                    report_month=month,
                )
            )
    return found


def regions(records: Sequence[WasdeXmlCell]) -> list[Region]:
    """One ``Region`` per distinct ``region`` text, in the order of its first appearance.

    Args:
        records: Every record of the release's XML, as ``parse_wasde_xml`` reads it.
    """
    month = _month(records)
    pages: dict[str, list[str]] = {}
    for record in records:
        if record.region is not None:
            reports = pages.setdefault(record.region, [])
            if record.report not in reports:
                reports.append(record.report)
    return [
        Region(region=region, reports=reports, report_month=month)
        for region, reports in pages.items()
    ]


def attributes(records: Sequence[WasdeXmlCell]) -> list[Attribute]:
    """One ``Attribute`` per distinct ``report``, ``matrix`` and ``attribute``, in file order.

    Args:
        records: Every record of the release's XML, as ``parse_wasde_xml`` reads it.
    """
    month = _month(records)
    rows = dict.fromkeys(
        (record.report, record.matrix, record.attribute)
        for record in records
        if record.attribute is not None
    )
    return [
        Attribute(report=report, matrix=matrix, attribute=attribute, report_month=month)
        for report, matrix, attribute in rows
    ]
