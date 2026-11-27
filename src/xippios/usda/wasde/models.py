"""Pydantic models of what this package returns, one ``UpstreamModel`` per record.

Conventions §3 and sdk-core ADR-0060, decision 7, give the rules of the one record this
package shapes itself, ``WasdeRecord``: one value per record; a field under upstream's
name holds upstream's text as printed; a reading of that text stands beside it under a
fixed suffix, ``<stem>_number`` for a number and ``<stem>_label`` for a label; and where
the file names no value that the record needs, as the XML names no commodity on pages 12
to 15, the record reads it from the table's title or from the same release's XLS, and
``commodity_source`` says which (ADR-0060, decision 7; ADR-0020, decision 2, as amended on
2026-11-24). No record names a page or a matrix of the file.

``Release`` is ESMIS's release of WASDE, projected from ``xippios-usda-esmis``'s model
(sdk-core ADR-0021). ``WasdeRecord`` is one value of a release's tables, read from its
XML by ``parse.wasde_xml.parse_wasde_xml``, with its footnotes as ``WasdeFootnote``.
``WasdeTable``, ``WasdeCommodity`` and ``WasdeRegion`` are the rows of the three list
tasks, each the distinct texts of one field of a month's records. ``WasdeXlsText`` is
one paragraph of the narrative in the XLS and ``WasdePdfPage`` one narrative page of the
PDF, text only (sdk-core ADR-0020 decision 4). No record here carries a documented
personal identifier (sdk-core ADR-0017).
"""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime
from xippios.core import UpstreamModel
from xippios.usda.esmis.models import ReleaseFile

__all__ = [
    "CommoditySource",
    "FootnoteOn",
    "Release",
    "WasdeCommodity",
    "WasdeFootnote",
    "WasdePdfPage",
    "WasdeRecord",
    "WasdeRegion",
    "WasdeTable",
    "WasdeXlsText",
]

CommoditySource = Literal["title", "xls", "layout"]
"""Where a record's ``commodity`` was read where its value's path in the XML states none:
the table's title, the block title of the same release's XLS, or the fixed table of the
report's layout (``parse.wasde_xml.LAYOUT``)."""

FootnoteOn = Literal[
    "table",
    "commodity",
    "region",
    "market_year",
    "attribute",
    "attribute_group",
    "unit",
    "value",
]
"""The field of a record whose printed text carries a footnote's mark."""


class Release(UpstreamModel):
    """One WASDE release as ESMIS catalogs it: its id, its release time and its files.

    A projection of ``xippios.usda.esmis.models.Release`` built with
    ``UpstreamModel.project`` (conventions §3): ``id`` and ``release_datetime`` are
    copied under ESMIS's names, and ``files`` is esmis's reading of the release's file
    URLs, ``Release.release_files()``. Nothing is converted: the time stays as ESMIS
    prints it.

    Attributes:
        id: ESMIS's release id, a string of digits, e.g. ``"796099"`` (October 2026).
        release_datetime: ``release_datetime`` as ESMIS prints it, an aware ``datetime``
            at ``+00:00``, e.g. ``2026-10-09T12:00:00+00:00``. ESMIS labels every WASDE
            release ``T12:00:00`` with ``+0000`` while WAOB releases at noon Eastern
            (``docs/upstream/OBSERVED.md``); the value is upstream's text, never converted.
        files: The release's files in ESMIS's order, each an
            ``xippios.usda.esmis.models.ReleaseFile`` with its ``url``, its ``name`` as the
            URL prints it (``"wasde1026.xml"``, ``"wasde0626v2.xml"`` where WAOB reposted
            the month) and its ``format``, the extension lowercased (``"pdf"``, ``"txt"``,
            ``"xls"``, ``"xml"``).
    """

    id: str
    release_datetime: AwareDatetime
    files: list[ReleaseFile]


class WasdeFootnote(UpstreamModel):
    r"""A footnote of a record: the mark a printed text carries and the footnote's text.

    The text is read from the footnotes the record's table prints (the page's
    ``sub_report_footer`` attributes, ``parse_wasde_xml``): the words after the mark up to
    the next mark, as printed but for the spaces around them. A table's note that no mark
    refers to, such as ``"Note: Totals may not add due to rounding."``, stands on each of
    the table's records with ``on`` ``"table"`` and no ``mark``.

    Attributes:
        on: The field whose printed text carries the mark, e.g. ``"table"`` for the title's
            ``1/``, ``"region"`` for ``"World  3/"``, ``"value"`` for ``"10.45 *"``.
        mark: The mark as printed, e.g. ``"1/"``, ``"/2"`` (``"Total /2\r\nDomestic"``),
            ``"*"``, ``"**"``; ``None`` for a table's note without one.
        text: The footnote's text, e.g. ``"Aggregate of local marketing years."``; ``None``
            where the table's footnotes print no such mark.
    """

    on: FootnoteOn
    mark: str | None
    text: str | None


class WasdeRecord(UpstreamModel):
    r"""One value of a WASDE release's tables, complete in itself, read from its XML file.

    One record per value: a ``cell_valueN``, ``mN_cell_valueN`` or ``wb_value`` of pages
    8 to 34, or one of the seven statistics of a row of the reliability tables of pages 35
    to 37 (``parse.wasde_xml``). A field under upstream's name holds the text as printed,
    line breaks (``"Total\r\nSupply"``), runs of spaces, indents and footnote marks
    (``"Trade 2/"``) kept, and its ``_label`` beside it holds the label as read: the line
    breaks and runs of spaces collapsed to one space, the outer spaces and the footnote
    marks (``1/``, ``/2``, ``*``) left out, e.g. ``"Total Supply"``, ``"Trade"``. A label
    ``None`` beside a text ``None``. ``docs/upstream/OBSERVED.md`` describes the file.

    Attributes:
        report_number: The report's number, read from the page's ``page_title``
            (``" WASDE - 676 - 12"`` gives ``676``).
        report_month: The page's ``Report_Month`` as printed, e.g. ``"October 2026"``.
        table: The title of the value's table as printed, e.g. ``"U.S. Feed Grain and
            Corn Supply and Use  1/"``: the page's ``sub_report_title``, or on a page of
            several titles the Nth for its Nth report item (``parse_wasde_xml``).
        table_label: ``table`` as read, e.g. ``"U.S. Feed Grain and Corn Supply and Use"``.
        commodity: The commodity as printed. Where the value's path states it
            (``commodityN``, ``mN_commodityN``: ``"Total Grains 4/"``, ``"Beef"``,
            ``"WHEAT"``) that text; else the title's words, as ``commodity_source`` says;
            ``None`` where neither states one (``"U.S. Dairy Prices"``).
        commodity_label: ``commodity`` as read, e.g. ``"Total Grains"``, ``"CORN"``.
        commodity_source: ``None`` where the value's path states the commodity, or no
            commodity is read; ``"title"`` where the table's title names it (``"Wheat"``
            from ``"U.S. Wheat Supply and Use  1/"``, ``"Cotton"`` from ``"World and U.S.
            Supply and Use for Cotton  1/"``); on pages 12 to 15, whose title names
            several, ``"xls"`` for the block title the same release's XLS prints over
            the table (``"CORN"``) and ``"layout"`` for the fixed table of the report's
            layout where the XLS was not read (``parse.wasde_xml.LAYOUT``).
        region: The region as printed: ``regionN`` or ``region`` of the value's path
            (``"        Argentina"``, ``"World  3/"``), else ``commodity_headerN``, which
            heads the matrix with its region on pages 8 to 10 (``"World"``, ``"United
            States"``, ``"Foreign  3/"``), else the region that starts the table's title
            (``"U.S."``, ``"Mexico"``); ``None`` where none is printed.
        region_label: ``region`` as read, e.g. ``"Argentina"``, ``"World"``.
        market_year: The year as printed: ``market_yearN`` or ``mN_market_yearN``
            (``"2026/27 Proj."``, ``"2025/26 (Est.) "``, ``"2026"``), else
            ``region_headerN``, which heads the matrix with its year on the world pages
            18 to 30 (``"2025/26 Est."``); ``None`` on the reliability pages.
        market_year_label: The year as read, its status left out, e.g. ``"2025/26"``.
        market_year_status: ``"Est."`` or ``"Proj."`` where the year is printed with that
            status, with or without parentheses; ``None`` for a year printed without one.
        forecast_month: ``forecast_monthN``, ``mN_forecast_monthN`` or
            ``wb_forecast_month_desc`` as printed, e.g. ``"Oct"``, ``"September"``,
            ``"IV*"``, ``"Oct Proj."``, or ``""`` where the page leaves the month empty.
        attribute: The row label as printed: ``attributeN``, ``mN_attributeN``,
            ``attr_desc`` or ``attribute``, e.g. ``"Ending Stocks"``, ``"Total /2\r\nDomestic"``.
        attribute_label: ``attribute`` as read, e.g. ``"Total Domestic"``.
        attribute_group: ``attribute_groupN``, the class column of page 11's
            wheat-by-class table, e.g. ``"Hard Red\r\nWinter"``; ``None`` elsewhere.
        attribute_group_label: ``attribute_group`` as read, e.g. ``"Hard Red Winter"``.
        statistic: On the reliability pages the name of the value's attribute, the table
            index removed (``average1`` is ``"average"``), e.g.
            ``"root_mean_square_error"``; ``None`` on pages 8 to 34.
        unit: What the file states for the row or the page: on pages 8 to 10 and 18 to 30
            the table's ``sub_report_subtitle`` as printed (``"(Million Metric Tons)"``);
            on the reliability pages, for ``average``, ``smallest`` and ``largest``, the
            nearest ``commodity_label`` of the table at or before the value (``"Million
            Bushels"``); ``None`` on the U.S. pages, whose XML states no unit per row.
        unit_label: ``unit`` as read, e.g. ``"(Million Metric Tons)"``.
        value: The value as printed, e.g. ``"2,141"``, ``"-4"``, ``"10.45 *"``, ``"3/"``.
        value_number: ``value`` as a number, its thousands separators and its marks left
            out: ``Decimal("2141")``, ``Decimal("10.45")`` for ``"10.45 *"``; ``None``
            where the text holds no number, as ``"3/"``, a footnote's mark printed in
            place of a value (https://github.com/xippios/sdk-usda-wasde/issues/22).
        footnotes: The record's footnotes in the order of its fields: the table's note
            without a mark, then each mark its texts carry, with the footnote's text.
    """

    report_number: int
    report_month: str
    table: str
    table_label: str
    commodity: str | None
    commodity_label: str | None
    commodity_source: CommoditySource | None
    region: str | None
    region_label: str | None
    market_year: str | None
    market_year_label: str | None
    market_year_status: Literal["Est.", "Proj."] | None
    forecast_month: str | None
    attribute: str | None
    attribute_label: str | None
    attribute_group: str | None
    attribute_group_label: str | None
    statistic: str | None
    unit: str | None
    unit_label: str | None
    value: str
    value_number: Decimal | None
    footnotes: list[WasdeFootnote]


class WasdeTable(UpstreamModel):
    """One table of a month's WASDE release, as its records name it: a ``list_tables`` row.

    One row per distinct ``table`` text of the month's records, in the order of the
    file.

    Attributes:
        table: The title as printed, e.g. ``"World Wheat Supply and Use  1/"``.
        table_label: The title as read, e.g. ``"World Wheat Supply and Use"``: what
            ``get_data``'s ``table`` compares.
    """

    table: str
    table_label: str


class WasdeCommodity(UpstreamModel):
    """One commodity of a month's WASDE release, as its records name it: a ``list_commodities`` row.

    One row per distinct ``commodity`` text and source of the month's records, in the
    order of the file; a record without a commodity gives none.

    Attributes:
        commodity: The commodity as printed, e.g. ``"Total Grains 4/"``, ``"CORN"``.
        commodity_label: As read, e.g. ``"Total Grains"``: what ``get_data``'s
            ``commodity`` compares.
        commodity_source: ``WasdeRecord.commodity_source``: ``None`` where the value's
            path states it, else ``"title"``, ``"xls"`` or ``"layout"``.
        tables: The labels of the tables whose records carry it, in the order of the
            file, e.g. ``["U.S. Feed Grain and Corn Supply and Use"]``.
    """

    commodity: str
    commodity_label: str
    commodity_source: CommoditySource | None
    tables: list[str]


class WasdeRegion(UpstreamModel):
    """One region of a month's WASDE release, as its records name it: a ``list_regions`` row.

    One row per distinct ``region`` text of the month's records, in the order of the
    file, so a region printed with several indents or marks has a row for each.

    Attributes:
        region: The region as printed, e.g. ``"        China"``, ``"World  3/"``, ``"U.S."``.
        region_label: As read, e.g. ``"China"``, ``"World"``: what ``get_data``'s
            ``region`` compares.
        tables: The labels of the tables whose records carry it, in the order of the
            file.
    """

    region: str
    region_label: str
    tables: list[str]


class WasdeXlsText(UpstreamModel):
    r"""One paragraph of a WASDE release's narrative: a row of its XLS file's sheet ``WASDE Text``.

    One record per row of the sheet whose cell holds text, in sheet order, as
    ``parse.wasde_xls.parse_wasde_xls`` reads it with xlrd; ``docs/upstream/OBSERVED.md``
    describes the workbook. The text is the narrative the PDF prints on its first pages,
    one paragraph a row, as printed: line breaks, spaces and the carriage return after
    the report's number kept.

    Attributes:
        sheet: The sheet's name as printed, ``"WASDE Text"``.
        row: The row in the sheet, counted from 0 as xlrd and ``OBSERVED.md`` count, e.g.
            ``0`` for ``"WASDE - 676\r"``, ``2`` for the first paragraph.
        text: The cell's text as printed, e.g. ``"WASDE - 676\r"``, ``"WHEAT: The outlook
            for 2026/27 U.S. wheat this month is for higher supplies, ..."``.
        report_month: The report month the workbook's first table sheet prints in its
            first cell (``Page 8``: ``"October 2026"``), as printed, the same on every
            record; ``None`` where that cell holds no ``<Month> <year>`` text.
    """

    sheet: str
    row: int
    text: str
    report_month: str | None


class WasdePdfPage(UpstreamModel):
    r"""One page of a WASDE release's narrative, as the text layer of its PDF file holds it.

    One record per narrative page, from page 1 up to the page headed Interagency
    Commodity Estimates Committees, as ``parse.wasde_pdf.parse_wasde_pdf`` reads it with
    pypdf: text only, never a number read as a figure (sdk-core ADR-0020 decision 4).

    Attributes:
        page: The page's number in the file, counted from 1, e.g. ``1``; the narrative
            pages print the same number in their running header (``WASDE-484-2``).
        text: The page's text as pypdf extracts it, its lines broken where pypdf breaks
            them, e.g. ``"WASDE-484-2 \n \nCOARSE GRAINS:   Projected U.S. feed grain
            supplies ..."``; ``""`` for a page without a text layer.
    """

    page: int
    text: str
