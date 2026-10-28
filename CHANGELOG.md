# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

## [0.1.0] - 2026-10-28

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for USDA WAOB World Agricultural Supply and Demand Estimates, empty task layer, MCP server and FastAPI router
  wired to it, test harness with core's family check, CI, the nightly live tests and
  the release train, in which a release PR's merge tags and publishes.
- Depends on `xippios-usda-esmis` 0.1.0 (`~=0.1.0`), the package that finds and
  downloads USDA report files on ESMIS.
- Upstream documentation snapshot in `docs/upstream/`, captured by
  `scripts/refresh_upstream.py`: the ESMIS publication page and the page of the newest
  release, WAOB's WASDE page and the four pages its menu links (About WASDE, the FAQ,
  Historical Changes & Revisions, the historical data page), and WAOB's 2018 notice of
  the file names; a page www.usda.gov refuses to automated requests is kept from USDA's
  CDN origin, its www.usda.gov address recorded by status. `layout.md` describes the
  XML, XLS, TXT and PDF files as observed in the October 2026 release and the file kinds
  and names of every release ESMIS lists.
- `list_releases(since, until)` and `get_latest_release()`: WASDE's releases in ESMIS
  through `xippios-usda-esmis`'s tasks, each a `Release` with its id, its release time as
  printed, its files, its month (`"YYYY-MM"`) and its `revision` (`"v2"` for a month
  WAOB reposted); MCP tools `usda_wasde_list_releases` and `usda_wasde_get_latest_release`.
- `get_release(month)`, a bulk task, Python only: the XML of the latest release, or of
  the month's latest release that carries one, downloaded through esmis into a temporary
  directory and parsed into one `WasdeXmlCell` per value, 6543 for October 2026;
  `meta.vintage` is the file's `Report_Month`, `meta.endpoint` the file's name.
- `parse.parse_wasde_xml(path)`: the XML of pages 8 to 37 read with the standard
  library's ElementTree, labels as printed; `unit` is the subtitle of the pages that
  state their unit there and the reliability tables' label for their average, smallest
  and largest, `None` on the U.S. pages, whose unit rows the XML repeats in every row
  group; an attribute the parser does not know raises `ValidationError`.
- Six XML samples cut from the October 2026 file by `scripts/cut_sample.py`, the esmis
  catalog fixtures and the download's replay fixture, its body a sample; the live test
  fetches the latest XML once. `docs/upstream/layout.md` now says that the XML repeats
  each unit row in every row group, which unit a path carries, and which attributes on
  elements are layout text.
- `list_tables(search)`, `list_commodities(search)` and `list_regions(search)`, MCP tools
  `usda_wasde_list_tables`, `usda_wasde_list_commodities` and `usda_wasde_list_regions`:
  answered without a request from four lists packaged under `reference/`, read from the
  October 2026 release (`wasde1026.xml`, `wasde1026.xls`): its 30 table pages with
  their titles, subtitles, footnotes and matrices, the 43 supply-and-use matrices of
  pages 11 to 30, 32 and 33 with their commodity and region, its 70 region texts with
  their pages, and its 451 row labels by matrix (`reference/attribute.json`, for the
  tasks to come, no task yet).
  The XML names the commodity of no matrix as a whole: on pages 12 to 15 it is the XLS's
  block title of the same position, and the refresh refuses to write when a page's
  titles and matrices differ in number; elsewhere the title's words. Only page 32's
  records carry a `commodity`, one per row (e.g. `Beef`, `Pork`, `Broiler`, `Turkey`, `Red
  Meat & Poultry`), while the list names its matrix `Meats`, so
  `list_commodities(search="beef")` answers nothing. `meta.vintage` is the
  release's `Report_Month`. `scripts/refresh_reference.py` downloads the latest XML and
  XLS through esmis (five requests) and writes the lists, refreshed before each release;
  the nightly live test compares them with the latest release, the month word of the
  reliability titles masked and each table footer compared only for whether it is set,
  never its text, which changes every release.
- `xlrd` is a dependency, reading the XLS's block titles and its narrative sheet.
- `get_table(table, month)` and `get_balance_sheet(commodity, region, month)`, MCP tools
  `usda_wasde_get_table` and `usda_wasde_get_balance_sheet`: the values of one page of
  the month's XML, or of one commodity's supply-and-use matrix as the packaged commodity
  list names it, the U.S. or Mexico page for `"United States"` (the default) or
  `"Mexico"` where the commodity has one (page 11's by-class wheat table left to
  `get_table`), else the rows of its world pages whose region, without indent and
  footnote marker, is the one given (`"Argentina"`, `"World"`). Both read the XML as
  `get_release` does, one download per call, nothing kept, with its `meta`; a page,
  commodity or region the packaged lists lack is refused before anything is sent,
  naming the closest. Their records, `WasdeTableValue`, are `WasdeXmlCell` projected
  without the page's labels (page title, subtitle, footnotes, report month), which
  `list_tables` and `meta.vintage` state once. MCP caps of their own, each with a note
  that says how to see the rest: `get_table` 400 rows or 128 KB, `get_balance_sheet`
  300 rows or 128 KB; every page and balance sheet of October 2026 fits.
- `read_report_text(month)`, MCP tool `usda_wasde_read_report_text`: the release's
  narrative as text, from its XLS's sheet `WASDE Text` (25 paragraphs for October 2026,
  `meta.vintage` the month the first table sheet prints), or, for a release without an
  XLS or whose XLS holds no such sheet, from its PDF's narrative pages, up to the page
  headed Interagency Commodity Estimates Committees, `meta.vintage` the ESMIS release id
  (`"95659"`), since a PDF prints a date, not a month label; no figure is read from a
  PDF.
- `parse.parse_wasde_xls(path)` and `parse.parse_wasde_pdf(path)`, the narrative's
  parsers (`WasdeXlsText`, `WasdePdfPage`); `pypdf` is a dependency, `xlwt` a dev
  dependency that writes the XLS sample.
- `scripts/cut_sample.py` cuts XLS samples (sheets copied cell by cell with xlwt) and
  keeps PDF samples whole: an XLS sample of the October 2026 release's sheets `WASDE
  Text` and `Page 8`, the July 2010 PDF (release 95659) and their download fixtures, a
  second XML download fixture whose body is the sample of pages 11 and 24. The live
  tests fetch the latest release's PDF once beside its XML and XLS and run the new tasks
  on those files.
