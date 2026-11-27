"""Parse a WASDE release's XML into one record per value, complete in itself (sdk-core ADR-0020).

The file is the tables of printed pages 8 to 37 as an XML export of a reporting tool
(``docs/upstream/OBSERVED.md``): a root ``<Report Name="wasde">`` holds one ``<srNN>`` per
page, each one ``<Report>`` whose attributes are the page's (``Name``, ``Report_Month``,
``page_title``, ``sub_report_title``, ``sub_report_subtitle``, ``sub_report_footer`` and
their numbered twins), whose children are the page's report items (``matrix1`` to
``matrix6``, ``table1`` to ``table4``). Inside an item, group elements carry the labels
of the rows and columns as attributes, and the values sit at the end of each path.

One generic walker reads every page: it never looks at an element's name, only at the
names of its attributes, which it sorts into five kinds. The vocabulary is the one the
October 2026 file uses, its counts in ``OBSERVED.md``:

- **dimensions**, the labels a value carries: ``commodity_headerN``; ``region_headerN``;
  ``commodityN``, ``mN_commodityN``, ``commodity``; ``regionN``, ``region``;
  ``market_yearN``, ``mN_market_yearN``; ``forecast_monthN``, ``mN_forecast_monthN``,
  ``wb_forecast_month_desc``; ``attributeN``, ``mN_attributeN``, ``attr_desc``,
  ``attribute``; ``attribute_groupN`` (the class columns of page 11's wheat-by-class
  table). Each is set by the attribute wherever it sits on the value's path, whatever
  the element is called: page 11's second matrix carries ``attribute2`` on
  ``m2_month_group`` and ``forecast_month2`` on ``m2_attribute_group``;
- **values**: ``cell_valueN``, ``mN_cell_valueN`` and ``wb_value`` on a ``<Cell>``, one
  record each; on the reliability pages 35 to 37 the seven statistics
  ``root_mean_square_error``, ``confidence_interval``, ``average``, ``smallest``,
  ``largest``, ``below_final`` and ``above_final`` (with the table index on page 37),
  one record each, ``statistic`` naming it;
- **units**: ``mN_unit_descrN``, ``mN_unit_descriptionN`` and ``mN_Unit_DescriptionN``,
  and the reliability tables' ``commodity_label``;
- **layout**, attributes that hold no label of a value: ``TextboxN``, ``textboxN``,
  ``FormatFillerN``, ``ReportFillerN``, ``mN_fillerN``, ``mN_formatfillerN``,
  ``commodity_attributeN`` and ``mN_attribute_titleN``;
- **the page's attributes** on the page's ``<Report>``, and ``sub_report_footer`` on a
  reliability table.

Any other attribute of a page's ``<Report>`` or of an element inside it raises
``ValidationError`` naming the page, the element and the attribute, as does a dimension
met twice on one path: a layout change upstream breaks the parser loudly, never
silently (sdk-core ADR-0020, consequences). So does a file that is not well-formed XML, whose
root is not ``<Report Name="wasde">`` with no other attribute, whose ``<srNN>`` does not
hold exactly one ``<Report>``, or whose ``page_title`` names no report and page number.

**The record** (``WasdeRecord``; sdk-core ADR-0060, decision 7). A field holds the text as
printed under upstream's name, a dimension that the pages spell several ways folded into
one field as https://github.com/xippios/sdk-usda-wasde/pull/3 decided (``attr_desc`` into
``attribute``, ``wb_forecast_month_desc`` into ``forecast_month``, every value into
``value``). Where the value's path states no region, ``commodity_headerN``, which heads
the matrices of pages 8 to 10 with their region (``World``, ``United States``), gives it;
where it states no market year, ``region_headerN``, which heads the matrices of the world
pages 18 to 30 with their year (``2025/26 Est.``), gives it. Beside each label stands its
``_label`` (``label``): line breaks and runs of spaces collapsed to one space, outer
spaces dropped, and every mark left out, a mark being a word of ``N/``, ``/N`` or
asterisks, or the asterisks that end a word. ``report_number`` is the report's number in
``page_title`` (``" WASDE - 676 - 12"``).

**Titles, subtitles and footers.** A page's titles are its ``sub_report_title``,
``sub_report_title2`` and ``sub_report_title3``, those present, in that order; its
subtitles likewise; its footers its ``sub_report_footer``, ``sub_report_footer2`` and
``sub_report_footer3``, then the ``sub_report_footer`` of its items, those present.
Each kind is given to the page's report items in document order: one text goes to every
item, N texts to N items one each, none leaves the field ``None``; any other count
raises ``ValidationError``. Pages 9, 11, 16, 31 and 33 of October 2026 have two titles
for two items, and page 37's one footer, on ``table4``, goes to its four tables.

**A commodity or a region that the path does not state** (ADR-0060, decision 7, the one
exception). Where the value's path states no region, the region that starts the table's
title, ``U.S.``, ``Mexico`` or ``World`` (not ``World and U.S.``), is the record's region.
Where it states no commodity:

- on the four pages whose title names several commodities, the keys of ``LAYOUT``
  (pages 12 to 15), the Nth table's commodity is the Nth block title that the same
  release's XLS prints on the page's sheet (``block_titles``, read by
  ``parse.wasde_xls.read_block_titles``), ``commodity_source`` ``"xls"``, where the sheet
  prints as many as the page has tables; else the Nth commodity of the page's title in
  ``LAYOUT``, ``"layout"``, where the page has as many tables as ``LAYOUT`` names; a page
  with another count raises ``ValidationError``;
- elsewhere, the commodity the title names, ``"title"``: the words between its region and
  ``Supply and Use`` (``by Class:`` left out), as in ``"U.S. Wheat Supply and Use  1/"``,
  or after ``World and U.S. Supply and Use for``, as in ``"... for Cotton  1/"``;
- else none, as on page 34, ``"U.S. Dairy Prices"``.

**Units.** ``unit`` carries only what the file states for the row or the page
(https://github.com/xippios/sdk-usda-wasde/pull/3): on the reliability pages ``average``,
``smallest`` and ``largest`` take the nearest ``commodity_label`` of their table at or
before them; on a page whose XML holds no unit attribute a table value takes its table's
``sub_report_subtitle`` as printed (pages 8 to 10 and 18 to 30); a page whose XML holds
unit attributes, the U.S. pages, leaves it ``None``, since the XML repeats every unit row
in every row group of a matrix and keeps no trace of which the page prints before which
rows (``OBSERVED.md``).

**Values.** ``value`` is the attribute's text as printed; ``value_number`` its number
(core's ``parse_decimal``), its thousands separators and its marks left out, ``None``
where the rest holds no finite number. October 2026 prints 6543 values: 6513 numbers,
six with the asterisks page 17 explains (``"10.45 *"``, ``"776 **"``), whose number is
read (https://github.com/xippios/sdk-usda-wasde/issues/22), and 24 footnote marks on
pages 26 and 27 in place of a value (``"3/"``).

**Footnotes.** A table's footer is read into its notes: the text before its first mark,
the table's note (``"Note: Totals may not add due to rounding."``), and for each mark,
``N/`` or asterisks where a word starts, the text up to the next mark. A record carries
the table's note, then a ``WasdeFootnote`` for each mark of its table, commodity, region,
market year, row label, class, unit and value, in that order, with the note of the same
mark, ``N/`` and ``/N`` alike, or ``None`` where the footer has none.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache
from os import PathLike
from pathlib import Path
from typing import NoReturn, get_args

from xippios.core import ValidationError, parse_decimal

from xippios.usda.wasde._client import SOURCE
from xippios.usda.wasde.models import (
    CommoditySource,
    FootnoteOn,
    WasdeFootnote,
    WasdeRecord,
)

__all__ = ["LAYOUT", "label", "marks", "parse_wasde_xml"]

FILE_KIND = "wasde.xml"
"""The file kind, as messages name it."""

LAYOUT: Mapping[str, tuple[str, ...]] = {
    "U.S. Feed Grain and Corn Supply and Use": ("FEED GRAINS", "CORN"),
    "U.S. Sorghum, Barley, and Oats Supply and Use": ("SORGHUM", "BARLEY", "OATS"),
    "U.S. Rice Supply and Use": ("TOTAL RICE", "LONG-GRAIN RICE", "MEDIUM & SHORT-GRAIN RICE"),
    "U.S. Soybeans and Products Supply and Use (Domestic Measure)": (
        "SOYBEANS",
        "SOYBEAN OIL",
        "SOYBEAN MEAL",
    ),
}
"""The fixed table of the report's layout: the commodity of each table of pages 12 to 15.

Keyed by the page's title as read (``label``), each the commodities of the page's tables
in their order, as the XLS's block titles print them; the count of each, two, three,
three and three, is the guard: a page of one of these titles with another count of tables
is refused. The maintainer decided this source on 2026-11-23 and again on 2026-11-27, for
the record where the release's XLS cannot be read; the offline test holds it against the
XLS sample and the live suite against the latest XLS (sdk-core ADR-0061, decision 12)."""

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
_LABELLED_STATISTICS = frozenset({"average", "smallest", "largest"})
"""The statistics in the unit a reliability table's ``commodity_label`` names."""
_LAYOUT = re.compile(
    r"[Tt]extbox\d+|FormatFiller\d+|ReportFiller\d+|m\d+_filler\d+|m\d+_formatfiller\d+"
    r"|commodity_attribute\d+|m\d+_attribute_title\d+"
)
_TITLE = re.compile(r"sub_report_title(\d*)")
_SUBTITLE = re.compile(r"sub_report_subtitle(\d*)")
_FOOTER = re.compile(r"sub_report_footer(\d*)")
_PAGE_FIELDS = ("Name", "Report_Month", "page_title")
_PAGE_TITLE = re.compile(r"WASDE\s*-\s*(\d+)\s*-\s*(\d+)")

_MARK = re.compile(r"\d{1,2}/|/\d{1,2}|\*+")
"""A word that is a footnote's mark: ``1/``, ``/2`` or asterisks."""
_ENDING_STARS = re.compile(r"(?<=[^*])\*+$")
"""The asterisks that end a word, as in ``IV*``: a mark too."""
_FOOTER_MARK = re.compile(r"(?<!\S)(?:(\d{1,2})/|(\*+))")
"""A mark in a footer, where a word starts: ``1/ Aggregate ...``, ``2/Includes``, ``* For``."""
_STATUS = re.compile(r"(?P<year>.*?)\s*\(?(?P<status>Est\.|Proj\.)\)?")
_TITLED = re.compile(
    r"(?P<region>U\.S\.|Mexico|World)\s+(?P<commodity>(?!and\s).+?)(?:\s+by\s+Class:)?"
    r"\s+Supply\s+and\s+Use\b"
)
_FOR = re.compile(
    r"World\s+and\s+U\.S\.\s+Supply\s+and\s+Use\s+for\s+(?P<commodity>[^,]+?)(?:,|\s+\d|\s*$)"
)
_TITLE_REGION = re.compile(r"(U\.S\.|Mexico|World)(?=\s)(?!\s+and\s)")
_ON: tuple[FootnoteOn, ...] = get_args(FootnoteOn)


def _refuse(message: str, raw: object) -> NoReturn:
    """Raise the family's ``ValidationError`` for the file, without a chained cause."""
    raise ValidationError(f"{FILE_KIND}: {message}", raw=raw, source=SOURCE) from None


def _words(text: str) -> list[tuple[str, str]]:
    """Each word of ``text`` as a pair: the word without its marks, and its mark or ``""``."""
    found = []
    for word in text.split():
        if _MARK.fullmatch(word):
            found.append(("", word))
        elif stars := _ENDING_STARS.search(word):
            found.append((word[: stars.start()], stars.group(0)))
        else:
            found.append((word, ""))
    return found


def label(text: str | None) -> str | None:
    r"""A printed text as read: runs of spaces and line breaks collapsed, marks left out.

    ``"Total /2\r\nDomestic"`` gives ``"Total Domestic"``, ``"        Argentina"`` gives
    ``"Argentina"``, ``"World  3/"`` gives ``"World"``; ``None`` gives ``None``.
    """
    if text is None:
        return None
    return " ".join(word for word, _ in _words(text) if word)


def marks(text: str | None) -> list[str]:
    """The footnote marks a printed text carries, in order: ``"Total /2 Use 3/"`` gives two."""
    return [] if text is None else [mark for _, mark in _words(text) if mark]


def _key(mark: str) -> str:
    """A mark's number, or its asterisks: ``"2/"`` and ``"/2"`` both give ``"2"``."""
    return mark.strip("/")


@cache
def _notes(footer: str | None) -> tuple[str | None, Mapping[str, str]]:
    """A footer's note before its first mark, and the text of each mark, by its number."""
    if footer is None:
        return None, {}
    found = list(_FOOTER_MARK.finditer(footer))
    lead = footer[: found[0].start()] if found else footer
    texts: dict[str, str] = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(footer)
        texts.setdefault(match.group(1) or match.group(2), footer[match.end() : end].strip())
    return lead.strip() or None, texts


@dataclass(frozen=True)
class _Item:
    """What every record of one report item shares: its page's labels and its own."""

    report: str
    element: str
    report_number: int
    report_month: str
    table: str
    footer: str | None
    unit: str | None
    region: str | None
    commodity: tuple[str, CommoditySource] | None


@dataclass
class _Walk:
    """The walk of one report item: its records so far and the reliability unit carried."""

    item: _Item
    records: list[WasdeRecord] = field(default_factory=list)
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


def _number(text: str) -> Decimal | None:
    """The printed value as a number, its marks left out; ``None`` where none is printed."""
    number = parse_decimal(text)
    if number is not None:
        return number
    rest = label(text)
    return parse_decimal(rest) if rest else None


def _year(text: str | None) -> tuple[str | None, str | None]:
    """A printed market year as read, and its status: ``"2025/26 (Est.) "`` gives both."""
    read = label(text)
    if read is None:
        return None, None
    status = _STATUS.fullmatch(read)
    if status is None:
        return read, None
    return status.group("year"), status.group("status")


def _footnotes(item: _Item, texts: Mapping[FootnoteOn, str | None]) -> list[WasdeFootnote]:
    """The table's note and a footnote for each mark of the record's texts, field by field."""
    note, notes = _notes(item.footer)
    found = [WasdeFootnote(on="table", mark=None, text=note)] if note else []
    for on in _ON:
        for mark in marks(texts.get(on)):
            found.append(WasdeFootnote(on=on, mark=mark, text=notes.get(_key(mark))))
    return found


def _record(
    item: _Item, labels: Mapping[str, str], statistic: str | None, unit: str | None, value: str
) -> WasdeRecord:
    """One value's record from its item and the labels of its path."""
    region = labels.get("region")
    if region is None:
        region = labels.get("commodity_header", item.region)
    market_year = labels.get("market_year", labels.get("region_header"))
    year, status = _year(market_year)
    commodity = labels.get("commodity")
    source: CommoditySource | None = None
    if commodity is None and item.commodity is not None:
        commodity, source = item.commodity
    texts: dict[FootnoteOn, str | None] = {
        "table": item.table,
        "commodity": commodity if source is None else None,
        "region": region,
        "market_year": market_year,
        "attribute": labels.get("attribute"),
        "attribute_group": labels.get("attribute_group"),
        "unit": unit,
        "value": value,
    }
    return WasdeRecord(
        report_number=item.report_number,
        report_month=item.report_month,
        table=item.table,
        table_label=label(item.table) or "",
        commodity=commodity,
        commodity_label=label(commodity),
        commodity_source=source,
        region=region,
        region_label=label(region),
        market_year=market_year,
        market_year_label=year,
        market_year_status=status,
        forecast_month=labels.get("forecast_month"),
        attribute=labels.get("attribute"),
        attribute_label=label(labels.get("attribute")),
        attribute_group=labels.get("attribute_group"),
        attribute_group_label=label(labels.get("attribute_group")),
        statistic=statistic,
        unit=unit,
        unit_label=label(unit),
        value=value,
        value_number=_number(value),
        footnotes=_footnotes(item, texts),
    )


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
                    f"{walk.item.report} {walk.item.element}: <{element.tag}> sets {dimension} "
                    f"again with the attribute {name!r}; a value has one {dimension}",
                    {"report": walk.item.report, "element": element.tag, "attribute": name},
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
                f"{walk.item.report} {walk.item.element}: unknown attribute {name!r} on "
                f"<{element.tag}>: not a label, a value, a unit or a filler of the layout the "
                "parser knows "
                "(docs/upstream/OBSERVED.md)",
                {"report": walk.item.report, "element": element.tag, "attribute": name},
            )
    for statistic_name, text in values:
        if statistic_name is None:
            unit = walk.item.unit
        else:
            unit = walk.unit if statistic_name in _LABELLED_STATISTICS else None
        walk.records.append(_record(walk.item, labels, statistic_name, unit, text))
    for child in element:
        _walk(child, labels, walk)


def _commodities(
    name: str, page: int, title: str, items: int, block_titles: Mapping[int, Sequence[str]]
) -> list[tuple[str, CommoditySource] | None]:
    """The commodity of each report item that the page's title or layout gives, if any."""
    read = label(title) or ""
    if read in LAYOUT:
        printed = list(block_titles.get(page, ()))
        if len(printed) == items:
            return [(text, "xls") for text in printed]
        layout = LAYOUT[read]
        if len(layout) != items:
            _refuse(
                f"{name}: the page titled {read!r} holds {items} tables, where the report's "
                f"layout has {len(layout)} ({', '.join(layout)}), and the release's XLS gave "
                f"{len(printed)} block titles for it; its commodities cannot be told",
                {"report": name, "tables": items, "layout": list(layout)},
            )
        return [(text, "layout") for text in layout]
    titled = _TITLED.match(title) or _FOR.match(title)
    if titled is None:
        return [None] * items
    return [(titled.group("commodity"), "title")] * items


def _page(holder: ET.Element, block_titles: Mapping[int, Sequence[str]]) -> list[WasdeRecord]:
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
    numbers = _PAGE_TITLE.search(attributes["page_title"])
    if numbers is None:
        _refuse(
            f"{name}: the page_title {attributes['page_title']!r} names no report and page "
            "number, as 'WASDE - 676 - 12' does",
            {"report": name, "page_title": attributes["page_title"]},
        )
    items = list(report)
    titles = _numbered(attributes, _TITLE)
    if not titles:
        _refuse(f"{name}: the page's <Report> has no sub_report_title", {"report": name})
    footers = _numbered(attributes, _FOOTER)
    for child in items:
        footers += _numbered(dict(child.attrib), _FOOTER)
    tables = _by_item(titles, len(items), "title", name)
    subtitles = _by_item(_numbered(attributes, _SUBTITLE), len(items), "subtitle", name)
    footnotes = _by_item(footers, len(items), "footer", name)
    unit_rows = any(_UNIT.fullmatch(key) for node in report.iter() for key in node.attrib)
    page = int(numbers.group(2))
    records: list[WasdeRecord] = []
    for index, child in enumerate(items):
        table = tables[index]
        assert table is not None  # titles is not empty
        same = [position for position, text in enumerate(tables) if text == table]
        commodity = _commodities(name, page, table, len(same), block_titles)[same.index(index)]
        region = _TITLE_REGION.match(table)
        walk = _Walk(
            _Item(
                report=name,
                element=child.tag,
                report_number=int(numbers.group(1)),
                report_month=attributes["Report_Month"],
                table=table,
                footer=footnotes[index],
                unit=None if unit_rows else subtitles[index],
                region=region.group(1) if region else None,
                commodity=commodity,
            )
        )
        _walk(child, {}, walk, item=True)
        records += walk.records
    return records


def parse_wasde_xml(
    path: str | PathLike[str], *, block_titles: Mapping[int, Sequence[str]] | None = None
) -> list[WasdeRecord]:
    """Every value of a WASDE release's XML file, one record each, in the file's order.

    Pages in order, ``sr08`` to ``sr37``, and within a page its report items and their
    values in document order. The rules (the attribute vocabulary, the titles of a page
    with several, the commodity and region a path does not state, the units, the
    footnotes) are this module's docstring.

    Args:
        path: The XML file as ESMIS serves it, e.g. ``"wasde1026.xml"``, UTF-8 with a
            byte order mark.
        block_titles: The block titles the same release's XLS prints on the sheets of
            pages 12 to 15, by printed page number, as
            ``parse.wasde_xls.read_block_titles`` reads them, e.g. ``{12: ["FEED GRAINS",
            "CORN"], ...}``; ``None`` (the default) reads none, and those pages' records
            take their commodity from ``LAYOUT``.

    Raises:
        ValidationError: The file is not well-formed XML, its root is not
            ``<Report Name="wasde">``, or it holds an attribute, a structure or a count
            of titles or tables the parser does not know; the message names the page,
            the element and the attribute.
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
    records: list[WasdeRecord] = []
    for holder in root:
        records += _page(holder, block_titles or {})
    return records
