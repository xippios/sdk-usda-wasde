"""Pydantic models mirroring what this package returns, one ``UpstreamModel`` per record.

Conventions §3 and ``/add-endpoint`` give the rules; for a file, fidelity applies to the
file (ADR-0020): field names are the file's attribute names snake_cased with the matrix
index removed, labels, units and footnote markers kept as text as printed, nothing
renamed, converted or joined across files.

``Release`` is ESMIS's release of WASDE, re-shaped from ``xippios-usda-esmis``'s model
(ADR-0021); ``WasdeXmlCell`` is one value of a release's XML file, as
``parse.wasde_xml.parse_wasde_xml`` reads it. No record here carries a documented
personal identifier (ADR-0017).
"""

from decimal import Decimal

from pydantic import AwareDatetime
from xippios.core import UpstreamModel
from xippios.usda.esmis.models import ReleaseFile

__all__ = ["Release", "WasdeXmlCell"]


class Release(UpstreamModel):
    """One WASDE release as ESMIS catalogs it, with its files, revision and month.

    A projection of ``xippios.usda.esmis.models.Release`` built with
    ``UpstreamModel.project`` (conventions §3): ``id`` and ``release_datetime`` are
    copied under ESMIS's names; ``files``, ``revision`` and ``month`` are values parsed
    from ESMIS's own fields (the file URLs, their names, the printed date), the only
    override the projection rule permits. Nothing is converted: the time stays as ESMIS
    prints it.

    Attributes:
        id: ESMIS's release id, a string of digits, e.g. ``"796099"`` (October 2026).
        release_datetime: ``release_datetime`` as ESMIS prints it, an aware ``datetime``
            at ``+00:00``, e.g. ``2026-10-09T12:00:00+00:00``. ESMIS labels every WASDE
            release ``T12:00:00`` with ``+0000`` while WAOB releases at noon Eastern
            (``docs/upstream/layout.md``); the value is upstream's text, never converted.
        files: The release's files in ESMIS's order, each an
            ``xippios.usda.esmis.models.ReleaseFile`` with its ``url``, its ``name`` as the
            URL prints it (``"wasde1026.xml"``) and its ``format``, the extension
            lowercased (``"pdf"``, ``"txt"``, ``"xls"``, ``"xml"``), read from the URL as
            ESMIS's ``list_release_files`` reads it.
        revision: ``"v2"`` where the release's file names carry that suffix
            (``wasde0626v2.xml``: a month WAOB reposted, whose catalog entry lists the
            revised files only), else ``None``; the suffix every file name of the
            release carries, ``None`` when not all carry the same one.
        month: The release month, ``"YYYY-MM"``, from the printed date of
            ``release_datetime``, e.g. ``"2026-10"``: what ``get_release`` takes.
    """

    id: str
    release_datetime: AwareDatetime
    files: list[ReleaseFile]
    revision: str | None
    month: str


class WasdeXmlCell(UpstreamModel):
    r"""One value of a WASDE release's XML file, with the labels its page prints for it.

    Named after the file kind it mirrors (``wasde_xml``, the parser's name) and the
    element that holds most values (``<Cell>``), so the XLS records of a later parser
    can carry their own name. One record per value: a ``cell_value1``,
    ``m1_cell_value1`` or ``wb_value`` attribute of a ``<Cell>`` on pages 8 to 34, or one
    of the seven statistics on a row of the reliability tables of pages 35 to 37.
    Labels are the attributes of the value's ancestors, read from the page down, as
    printed: line breaks (``"Total\r\nSupply"``), double spaces, leading and trailing
    spaces and footnote markers (``"Trade 2/"``) are kept. A field the value's path
    carries no attribute for is ``None``. ``docs/upstream/layout.md`` describes the file.

    Attributes:
        report: The page's ``Name``, e.g. ``"sr12"`` (printed page 12).
        report_month: The page's ``Report_Month`` as printed, e.g. ``"October 2026"``.
        page_title: The page's ``page_title`` as printed, with its leading space, e.g.
            ``" WASDE - 676 - 12"``.
        table: The title of the table the value belongs to, the page's
            ``sub_report_title``, ``sub_report_title2`` or ``sub_report_title3`` as
            printed, e.g. ``"U.S. Feed Grain and Corn Supply and Use  1/"``; on a page
            with several titles the Nth report item takes the Nth (``parse_wasde_xml``).
        sub_report_subtitle: The table's subtitle by the same rule, e.g.
            ``"(Million Metric Tons)"``; ``None`` where the page prints none.
        sub_report_footer: The table's footnotes by the same rule, e.g. ``"1/ Aggregate
            of local marketing years. ..."``; ``None`` where the page prints none.
        matrix: The report item the value sits in, its element name, e.g. ``"matrix1"``;
            ``"table1"`` to ``"table4"`` on the reliability pages.
        commodity_header: ``commodity_headerN`` of the item, e.g. ``"World"``.
        region_header: ``region_headerN`` of the item, e.g. ``"2026/27 Proj."``.
        commodity: ``commodityN``, ``mN_commodityN`` or ``commodity``, e.g.
            ``"Wheat"``, ``"Beef"``, ``"WHEAT"``.
        region: ``regionN`` or ``region``, e.g. ``"World  3/"``, ``"U.S."``.
        market_year: ``market_yearN`` or ``mN_market_yearN``, e.g. ``"2026/27 Proj."``,
            ``"2025/26 (Est.) "``, ``"2026"``.
        forecast_month: ``forecast_monthN``, ``mN_forecast_monthN`` or
            ``wb_forecast_month_desc``, e.g. ``"Oct"``, ``"September"``, ``"IV"``, or
            ``""`` where the page leaves the column's month empty.
        attribute: ``attributeN``, ``mN_attributeN``, ``attr_desc`` or ``attribute``,
            e.g. ``"Ending Stocks"``, ``"Total\r\nSupply"``, ``"Production"``.
        attribute_group: ``attribute_groupN``, the column of page 11's wheat-by-class
            table, e.g. ``"Hard Red\r\nWinter"``, ``"Total"``.
        statistic: On the reliability pages the name of the value's attribute, the
            table index removed by the naming rule (``average1`` is ``"average"``;
            Johannes, 2026-10-28, G5 inside PR 3), e.g. ``"root_mean_square_error"``,
            ``"below_final"``; ``None`` on pages 8 to 34.
        unit: What the file states for the row or the page (Johannes, 2026-10-28, G5
            inside PR 3): on the reliability pages, for ``average``, ``smallest`` and
            ``largest`` only, the nearest ``commodity_label`` of the table at or before
            the value, e.g. ``"Million Bushels"``; on pages 8 to 10 and 18 to 30 the
            table's ``sub_report_subtitle`` as printed, e.g. ``"(Million Metric
            Tons)"``; ``None`` on pages 11 to 17 and 31 to 34, for which the XML carries
            no per-row unit (``parse_wasde_xml``), and on the other statistics.
        cell_value: The value as printed, e.g. ``"2,141"``, ``"-4"``, ``"10.45 *"``,
            ``"3/"``.
        value: ``cell_value`` as a number, its thousands separators removed
            (``Decimal("2141")``); ``None`` where the text is not one, a printed mark
            such as ``"10.45 *"`` or a footnote marker such as ``"3/"``.
    """

    report: str
    report_month: str
    page_title: str
    table: str
    sub_report_subtitle: str | None
    sub_report_footer: str | None
    matrix: str
    commodity_header: str | None
    region_header: str | None
    commodity: str | None
    region: str | None
    market_year: str | None
    forecast_month: str | None
    attribute: str | None
    attribute_group: str | None
    statistic: str | None
    unit: str | None
    cell_value: str
    value: Decimal | None
