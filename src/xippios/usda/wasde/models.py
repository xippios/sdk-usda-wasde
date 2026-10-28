"""Pydantic models mirroring what this package returns, one ``UpstreamModel`` per record.

Conventions §3 and ``/add-endpoint`` give the rules; for a file, fidelity applies to the
file (ADR-0020): labels, units and footnote markers kept as text as printed, nothing
renamed, converted or joined across files. A ``WasdeXmlCell`` field is named after the
file's attribute, snake_cased with the matrix index removed (``m1_commodity1`` is
``commodity``, ``attribute_group2`` is ``attribute_group``), with three exceptions
(gap, row 195): the page's and the table's names are kept on the record under names of
their own, as conventions §3 keeps sheet and table names (``report`` holds the page's
``Name``, ``table`` its ``sub_report_title``, ``sub_report_title2`` or
``sub_report_title3``, ``matrix`` the report item's element name); a dimension the
pages spell several ways is folded into one field (``attr_desc`` into ``attribute``,
``wb_forecast_month_desc`` into ``forecast_month``); and every value goes into
``cell_value``, ``wb_value`` and the reliability statistics included, the statistic's
name into ``statistic``.

``Release`` is ESMIS's release of WASDE, re-shaped from ``xippios-usda-esmis``'s model
(ADR-0021); ``WasdeXmlCell`` is one value of a release's XML file, as
``parse.wasde_xml.parse_wasde_xml`` reads it. ``Table``, ``Commodity``, ``Region`` and
``Attribute`` are the records of the four packaged lists under ``reference/``, which
``scripts/refresh_reference.py`` writes from the latest release's files (conventions §3,
ADR-0022): labels as the files print them, each record with the ``report_month`` of the
release it was read from. No record here carries a documented personal identifier
(ADR-0017).
"""

from decimal import Decimal

from pydantic import AwareDatetime
from xippios.core import UpstreamModel
from xippios.usda.esmis.models import ReleaseFile

__all__ = ["Attribute", "Commodity", "Region", "Release", "Table", "WasdeXmlCell"]


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
            ``release_datetime``, e.g. ``"2026-10"``: what Python callers pass to
            ``get_release``.
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


class Table(UpstreamModel):
    """One page of a WASDE release's tables, as its XML file heads it: a ``list_tables`` row.

    One record per page element, ``sr08`` to ``sr37``, read from the attributes of the
    page's ``<Report>`` and the names of its report items, as printed
    (``reference/table.json``): its titles, subtitles and footers, stated once here for
    the page.

    Attributes:
        report: The page's ``Name``, e.g. ``"sr12"``: what a ``WasdeXmlCell``'s
            ``report`` holds.
        page: The printed page number, the number that ends ``page_title``
            (``" WASDE - 676 - 12"`` gives ``12``).
        sub_report_title: The page's first title as printed, e.g. ``"U.S. Feed Grain and
            Corn Supply and Use  1/"``.
        sub_report_title2: ``sub_report_title2`` as printed, the second table's title on
            pages 11, 16, 31 and 33 (October 2026), e.g. ``"U.S. Wheat by Class: Supply
            and Use"``; ``None`` where the page has none.
        sub_report_title3: ``sub_report_title3`` as printed, on page 9 (October 2026),
            ``"World and U.S. Supply and Use for Cotton  1/"``; ``None`` elsewhere.
        sub_report_subtitle: ``sub_report_subtitle`` as printed, e.g. ``"(Million
            Metric Tons)"``; ``None`` where the page prints none.
        sub_report_subtitle2: ``sub_report_subtitle2`` as printed; ``None`` on every page
            of October 2026.
        sub_report_subtitle3: ``sub_report_subtitle3`` as printed, on page 9 (October
            2026), ``"Million 480-lb. Bales"``; ``None`` elsewhere.
        sub_report_footer: The page's footnotes as printed, ``sub_report_footer`` of its
            ``<Report>``, e.g. ``"1/ Aggregate of local marketing years. ..."``; on the
            reliability pages 35 to 37, whose ``<Report>`` holds none, the
            ``sub_report_footer`` of the one report item that carries it (``table1``,
            ``table4``); ``None`` where the page has none. Stated once here for the page
            (Johannes, 2026-10-28, G5 inside PR 5).
        sub_report_footer2: ``sub_report_footer2`` as printed, the second table's
            footnotes, e.g. on pages 9, 25, 27, 31 and 32 (October 2026); ``None`` where
            the page has none.
        sub_report_footer3: ``sub_report_footer3`` as printed, e.g. on pages 16, 17, 33
            and 34 (October 2026); ``None`` where the page has none.
        matrices: The page's report items in document order, their element names as
            printed, e.g. ``["matrix1", "matrix2"]``, ``["matrix3", "matrix4"]`` on page
            26, ``["table1", "table2", "table3", "table4"]`` on page 37: the values a
            ``WasdeXmlCell``'s ``matrix`` takes on the page, and their number.
        report_month: The page's ``Report_Month`` as printed, e.g. ``"October 2026"``.
    """

    report: str
    page: int
    sub_report_title: str
    sub_report_title2: str | None
    sub_report_title3: str | None
    sub_report_subtitle: str | None
    sub_report_subtitle2: str | None
    sub_report_subtitle3: str | None
    sub_report_footer: str | None
    sub_report_footer2: str | None
    sub_report_footer3: str | None
    matrices: list[str]
    report_month: str


class Commodity(UpstreamModel):
    """One supply-and-use matrix, with its commodity: a ``list_commodities`` row.

    One record per report item of the supply-and-use pages, the U.S. pages 11 to 17, 32
    and 33 and the world pages 18 to 30 (``reference/commodity.json``). The XML names the
    commodity of none of them as a whole: only page 32's records carry a ``commodity``, one
    per row (e.g. ``Beef``, ``Pork``, ``Broiler``, ``Turkey``, ``Red Meat & Poultry``), and its
    matrix is ``Meats`` here, so a search for a row's commodity finds nothing in this
    list. On pages 12 to 15 the commodity is the XLS's block title, the Nth of
    sheet ``Page N`` for the page's Nth report item (``FEED GRAINS``, ``CORN``); on the
    other pages it is the commodity the item's title names. Pages 8 to 10 (the world and
    U.S. aggregates), 31 (quarterly production and prices), 34 (dairy prices) and 35 to 37
    (reliability) are not in the list.

    Attributes:
        commodity: The commodity as printed: on pages 12 to 15 the XLS block title
            verbatim, e.g. ``"CORN"``, ``"SOYBEAN MEAL"``; on pages 11, 16 to 30, 32 and
            33 the words of the item's title between its region and ``Supply and Use``
            (or ``by Class: Supply and Use``), e.g. ``"Wheat"``, ``"Coarse Grain"``,
            ``"Meats"``, ``"Milk"``.
        region: The region the item's title names: ``"United States"`` for a title that
            starts ``U.S.`` (pages 11 to 17, 32, 33), ``"Mexico"`` for page 16's second item,
            ``"World"`` for the world pages 18 to 30, whose matrices hold the world and
            its regions, as ``list_regions`` prints them.
        report: The page's ``Name``, e.g. ``"sr12"``.
        matrix: The report item, its element name, e.g. ``"matrix2"``: with ``report``,
            the ``WasdeXmlCell`` records of the matrix.
        table: The item's title as ``parse_wasde_xml`` assigns it, e.g. ``"U.S. Feed
            Grain and Corn Supply and Use  1/"``.
        report_month: The page's ``Report_Month`` as printed, e.g. ``"October 2026"``.
    """

    commodity: str
    region: str
    report: str
    matrix: str
    table: str
    report_month: str


class Region(UpstreamModel):
    """One region a WASDE release's XML prints, with the pages it is on: a ``list_regions`` row.

    One record per distinct ``region`` text of the file, in the order of its first
    appearance (``reference/region.json``): the rows of the world pages 18 to 30, page
    9's cotton table and the reliability pages 35 and 36. The U.S. pages print no region
    text.

    Attributes:
        region: The text as printed, with its indent, footnote marker and spaces, e.g.
            ``"World"``, ``"World  3/"``, ``"United States"``, ``"        Burma"``,
            ``"U.S."``: what a ``WasdeXmlCell``'s ``region`` holds.
        reports: The pages that print it, their ``Name`` in file order, e.g.
            ``["sr09", "sr18", "sr35"]``.
        report_month: The release's ``Report_Month`` as printed, e.g. ``"October 2026"``.
    """

    region: str
    reports: list[str]
    report_month: str


class Attribute(UpstreamModel):
    r"""One row label of a WASDE table: an ``attribute`` a matrix of the XML prints.

    One record per distinct ``report``, ``matrix`` and ``attribute`` of the file, in file
    order (``reference/attribute.json``); a value without an ``attribute`` (page 31,
    page 37's tables 2 to 4, which name their rows by commodity) gives none. Packaged for
    the tasks that name a table's rows; no task answers with it in 0.1.0.

    Attributes:
        report: The page's ``Name``, e.g. ``"sr12"``.
        matrix: The report item, e.g. ``"matrix1"``.
        attribute: The row label as printed, e.g. ``"Area Planted"``, ``"    Supply,
            Total"``, ``"Total\r\nSupply"``.
        report_month: The page's ``Report_Month`` as printed, e.g. ``"October 2026"``.
    """

    report: str
    matrix: str
    attribute: str
    report_month: str
