"""Parse a WASDE release's XML file into one record per value (ADR-0020).

The file is the tables of printed pages 8 to 37 as an XML export of a reporting tool
(``docs/upstream/layout.md``): a root ``<Report Name="wasde">`` holds one ``<srNN>`` per
page, each one ``<Report>`` whose attributes are the page's (``Name``, ``Report_Month``,
``page_title``, ``sub_report_title``, ``sub_report_subtitle``, ``sub_report_footer`` and
their numbered twins), whose children are the page's report items (``matrix1`` to
``matrix6``, ``table1`` to ``table4``). Inside an item, group elements carry the labels
of the rows and columns as attributes, and the values sit at the end of each path.

One generic walker reads every page: it never looks at an element's name, only at the
names of its attributes, which it sorts into five kinds. The vocabulary is the one the
October 2026 file uses, its counts in ``layout.md``:

- **dimensions**, the labels a value carries into its record, field by field:
  ``commodity_headerN``; ``region_headerN``; ``commodityN``, ``mN_commodityN``,
  ``commodity``; ``regionN``, ``region``; ``market_yearN``, ``mN_market_yearN``;
  ``forecast_monthN``, ``mN_forecast_monthN``, ``wb_forecast_month_desc``;
  ``attributeN``, ``mN_attributeN``, ``attr_desc``, ``attribute``; ``attribute_groupN``
  (the class columns of page 11's wheat-by-class table). A field is named after the
  attribute with the matrix index removed and is set by the attribute wherever it sits,
  whatever the element is called: page 11's second matrix carries ``attribute2`` on
  ``m2_month_group`` and ``forecast_month2`` on ``m2_attribute_group``;
- **values**: ``cell_valueN``, ``mN_cell_valueN`` and ``wb_value`` on a ``<Cell>``, one
  record each; on the reliability pages 35 to 37 the seven statistics
  ``root_mean_square_error``, ``confidence_interval``, ``average``, ``smallest``,
  ``largest``, ``below_final`` and ``above_final`` (with the table index on page 37),
  one record each, ``statistic`` naming it;
- **units**: ``mN_unit_descrN`` (on a ``<Cell>`` of a unit row, or on page 11's second
  matrix on an element of the value's path), ``mN_unit_descriptionN`` and
  ``mN_Unit_DescriptionN`` (on an element of the value's path), and the reliability
  tables' ``commodity_label``;
- **layout**, attributes that hold no label of a value: ``TextboxN``, ``textboxN``,
  ``FormatFillerN``, ``ReportFillerN``, ``mN_fillerN``, ``mN_formatfillerN``,
  ``commodity_attributeN`` (``"Percent"``, the heading page 35 prints over its first two
  columns, which pages 36 and 37 hold in ``Textbox41`` and ``textbox4``) and
  ``mN_attribute_titleN`` (``"Milk Prices 2/"``, a heading row of page 34 without
  values). Their texts are ``filler``, ``Filler``, empty, or headings and units the
  page prints in a text box (``"Million Bushels"`` on page 13, ``"Annual"`` on page 31);
- **the page's attributes** on the page's ``<Report>``, and ``sub_report_footer`` on a
  reliability table.

Any other attribute raises ``ValidationError`` naming the page, the element and the
attribute, as does a dimension met twice on one path: a layout change upstream breaks
the parser loudly, never silently (ADR-0020, consequences). So does a file that is not
well-formed XML, or whose root is not ``<Report Name="wasde">``.

**Titles, subtitles and footers.** A page's titles are its ``sub_report_title``,
``sub_report_title2`` and ``sub_report_title3``, those present, in that order; its
subtitles likewise; its footers its ``sub_report_footer``, ``sub_report_footer2`` and
``sub_report_footer3``, then the ``sub_report_footer`` of its items, those present.
Each kind is given to the page's report items in document order: one text goes to every
item, N texts to N items one each, none leaves the field ``None``; any other count
raises ``ValidationError``. In October 2026 every page has one title, but pages 9
(title and title3, subtitle and subtitle3, footer and footer2), 11 (title and title2,
one footer), 16 (title and title2, footer and footer3), 31 (title and title2, footer and
footer2) and 33 (title and title2, one footer3), each with two items, whose second
item's labels and footnotes are those of the second title's table; page 37's one
footer, on ``table4``, goes to its four tables.

**Units.** On the reliability pages the unit is carried, the way a reader reads the
page: each value takes the nearest ``commodity_label`` of its table at or before it
(``"Million Bushels"`` on CORN carries to SORGHUM, BARLEY and OATS on page 37); a table
without one leaves it ``None``. On pages 8 to 34 the file does not say which unit a
value has, so ``unit`` is ``None`` there: where a page prints unit rows (pages 11, 12,
14 to 17, 33, 34), the file repeats every one of them in every row group of the matrix
with its text (page 12's ``Million Acres``, ``Metric Tons`` and ``Million Metric Tons``
in each of its 13 groups) and keeps no trace of which the page shows before which rows;
a unit on a value's path is the text of its column's cell, one part of a unit printed
across several columns (``"Million"`` over Broiler and ``" Pounds"`` over Turkey on page
31). The units of the world pages stand in ``sub_report_subtitle``
(``"(Million Metric Tons)"``).

**Values.** ``cell_value`` is the attribute's text as printed; ``value`` its number, the
thousands separators removed (core's ``parse_decimal``), ``None`` where the text is no
finite number. October 2026 prints 6543 values: 6513 numbers (601 with a thousands
separator, 33 negative), six with the asterisks page 17 explains (``"10.45 *"``,
``"776 **"``) and 24 footnote markers on pages 26 and 27 (``"3/"``).
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal
from os import PathLike
from pathlib import Path
from typing import NoReturn

from xippios.core import ValidationError, parse_decimal

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import WasdeXmlCell

__all__ = ["parse_wasde_xml"]

FILE_KIND = "wasde.xml"
"""The file kind, as messages name it."""

_DIMENSIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("commodity_header", re.compile(r"commodity_header\d+")),
    ("region_header", re.compile(r"region_header\d+")),
    ("commodity", re.compile(r"(?:m\d+_)?commodity\d*")),
    ("region", re.compile(r"region\d*")),
    ("market_year", re.compile(r"(?:m\d+_)?market_year\d+")),
    ("forecast_month", re.compile(r"(?:m\d+_)?forecast_month\d+|wb_forecast_month_desc")),
    ("attribute", re.compile(r"(?:m\d+_)?attribute\d*|attr_desc")),
    ("attribute_group", re.compile(r"attribute_group\d+")),
)
_CELL_VALUE = re.compile(r"(?:m\d+_)?cell_value\d+|wb_value")
_STATISTIC = re.compile(
    r"(root_mean_square_error|confidence_interval|average|smallest|largest|below_final"
    r"|above_final)\d*"
)
_UNIT = re.compile(r"m\d+_(?:unit_descr|unit_description|Unit_Description)\d+")
_COMMODITY_LABEL = "commodity_label"
_LAYOUT = re.compile(
    r"[Tt]extbox\d+|FormatFiller\d+|ReportFiller\d+|m\d+_filler\d+|m\d+_formatfiller\d+"
    r"|commodity_attribute\d+|m\d+_attribute_title\d+"
)
_TITLE = re.compile(r"sub_report_title(\d*)")
_SUBTITLE = re.compile(r"sub_report_subtitle(\d*)")
_FOOTER = re.compile(r"sub_report_footer(\d*)")
_PAGE_FIELDS = ("Name", "Report_Month", "page_title")


def _refuse(message: str, raw: object) -> NoReturn:
    """Raise the family's ``ValidationError`` for the file, without a chained cause."""
    raise ValidationError(f"{FILE_KIND}: {message}", raw=raw, source=SOURCE) from None


@dataclass(frozen=True)
class _Page:
    """What every record of one report item shares: the page's labels and the item's."""

    report: str
    report_month: str
    page_title: str
    table: str
    sub_report_subtitle: str | None
    sub_report_footer: str | None
    matrix: str


@dataclass
class _Walk:
    """The walk of one report item: its records so far and the unit carried in it."""

    page: _Page
    records: list[WasdeXmlCell] = field(default_factory=list)
    unit: str | None = None


def _numbered(attributes: dict[str, str], pattern: re.Pattern[str]) -> list[str]:
    """The texts of ``name``, ``name2``, ``name3``... in ``attributes``, in that order."""
    found = [
        (int(m.group(1) or 1), text)
        for k, text in attributes.items()
        if (m := pattern.fullmatch(k))
    ]
    return [text for _, text in sorted(found)]


def _by_item(texts: list[str], items: int, kind: str, report: str) -> list[str | None]:
    """``texts`` given to ``items`` report items: one to all, N to N, none to none."""
    given: list[str | None] = list(texts)
    if not given:
        return [None] * items
    if len(given) == 1:
        return given * items
    if len(given) == items:
        return given
    _refuse(
        f"{report} has {len(texts)} {kind}s for {items} report items; a page gives one to "
        "every item or one to each",
        {"report": report, kind: texts},
    )


def _value(text: str) -> Decimal | None:
    """The printed text as a number, ``None`` where it is no finite number."""
    number = parse_decimal(text)
    return number if number is not None and number.is_finite() else None


def _walk(element: ET.Element, labels: dict[str, str], walk: _Walk, *, item: bool = False) -> None:
    """Read ``element`` and its descendants: their labels, their values, the unit carried.

    ``item`` marks the report item itself, whose ``sub_report_footer`` the page has read.
    """
    labels = dict(labels)
    values: list[tuple[str | None, str]] = []
    for name, text in element.attrib.items():
        if item and _FOOTER.fullmatch(name):
            continue
        dimension = next((key for key, pattern in _DIMENSIONS if pattern.fullmatch(name)), None)
        if dimension is not None:
            if dimension in labels:
                _refuse(
                    f"{walk.page.report} {walk.page.matrix}: <{element.tag}> sets {dimension} "
                    f"again with the attribute {name!r}; a value has one {dimension}",
                    {"report": walk.page.report, "element": element.tag, "attribute": name},
                )
            labels[dimension] = text
        elif _CELL_VALUE.fullmatch(name):
            values.append((None, text))
        elif statistic := _STATISTIC.fullmatch(name):
            values.append((statistic.group(1), text))
        elif name == _COMMODITY_LABEL:
            if text:
                walk.unit = text
        elif not (_UNIT.fullmatch(name) or _LAYOUT.fullmatch(name)):
            _refuse(
                f"{walk.page.report} {walk.page.matrix}: unknown attribute {name!r} on "
                f"<{element.tag}>: not a label, a value, a unit or a filler of the layout "
                "the parser knows (docs/upstream/layout.md)",
                {"report": walk.page.report, "element": element.tag, "attribute": name},
            )
    page = walk.page
    for statistic_name, text in values:
        walk.records.append(
            WasdeXmlCell(
                report=page.report,
                report_month=page.report_month,
                page_title=page.page_title,
                table=page.table,
                sub_report_subtitle=page.sub_report_subtitle,
                sub_report_footer=page.sub_report_footer,
                matrix=page.matrix,
                commodity_header=labels.get("commodity_header"),
                region_header=labels.get("region_header"),
                commodity=labels.get("commodity"),
                region=labels.get("region"),
                market_year=labels.get("market_year"),
                forecast_month=labels.get("forecast_month"),
                attribute=labels.get("attribute"),
                attribute_group=labels.get("attribute_group"),
                statistic=statistic_name,
                unit=walk.unit if statistic_name is not None else None,
                cell_value=text,
                value=_value(text),
            )
        )
    for child in element:
        _walk(child, labels, walk)


def _page(holder: ET.Element) -> list[WasdeXmlCell]:
    """The records of one page, ``<srNN>``, which holds the page's one ``<Report>``."""
    reports = list(holder)
    if len(reports) != 1 or reports[0].tag != "Report":
        _refuse(
            f"<{holder.tag}> holds {[child.tag for child in reports]}, not one <Report>",
            {"element": holder.tag},
        )
    report = reports[0]
    attributes = dict(report.attrib)
    missing = [name for name in _PAGE_FIELDS if name not in attributes]
    if missing:
        _refuse(f"<{holder.tag}>'s <Report> lacks {missing}", {"element": holder.tag})
    name = attributes["Name"]
    for key in attributes:
        if key not in _PAGE_FIELDS and not any(
            pattern.fullmatch(key) for pattern in (_TITLE, _SUBTITLE, _FOOTER)
        ):
            _refuse(
                f"{name}: unknown attribute {key!r} on the page's <Report>",
                {"report": name, "element": "Report", "attribute": key},
            )
    items = list(report)
    titles = _numbered(attributes, _TITLE)
    if not titles:
        _refuse(f"{name}: the page's <Report> has no sub_report_title", {"report": name})
    footers = _numbered(attributes, _FOOTER)
    for item in items:
        footers += _numbered(dict(item.attrib), _FOOTER)
    tables = _by_item(titles, len(items), "title", name)
    subtitles = _by_item(_numbered(attributes, _SUBTITLE), len(items), "subtitle", name)
    footnotes = _by_item(footers, len(items), "footer", name)
    records: list[WasdeXmlCell] = []
    for index, item in enumerate(items):
        table = tables[index]
        assert table is not None  # titles is not empty
        walk = _Walk(
            _Page(
                report=name,
                report_month=attributes["Report_Month"],
                page_title=attributes["page_title"],
                table=table,
                sub_report_subtitle=subtitles[index],
                sub_report_footer=footnotes[index],
                matrix=item.tag,
            )
        )
        _walk(item, {}, walk, item=True)
        records += walk.records
    return records


def parse_wasde_xml(path: str | PathLike[str]) -> list[WasdeXmlCell]:
    """Every value of a WASDE release's XML file, one record each, in the file's order.

    Pages in order, ``sr08`` to ``sr37``, and within a page its report items and their
    values in document order. The rules (the attribute vocabulary, the titles of a page
    with several, the units) are this module's docstring.

    Args:
        path: The XML file as ESMIS serves it, e.g. ``"wasde1026.xml"``, UTF-8 with a
            byte order mark.

    Raises:
        ValidationError: The file is not well-formed XML, its root is not
            ``<Report Name="wasde">``, or it holds an attribute, a structure or a count
            of titles the parser does not know; the message names the page, the element
            and the attribute.
    """
    try:
        root = ET.parse(Path(path)).getroot()
    except ET.ParseError as error:
        _refuse(f"not well-formed XML: {error}", str(path))
    if root.tag != "Report" or root.attrib != {"Name": "wasde"}:
        _refuse(
            f'the root is <{root.tag}> with {sorted(root.attrib)}, not <Report Name="wasde">',
            {"element": root.tag},
        )
    records: list[WasdeXmlCell] = []
    for holder in root:
        records += _page(holder)
    return records
