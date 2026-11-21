# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [0.2.0] - 2026-11-21

### Added

- `xippios.usda.wasde.mcp.build()` returns the read-only tool set that
  `xippios-usda-wasde-mcp` serves, core's `ToolSet` with the caps of `tasks.MCP_CAPS`, so a
  host serves the eight WASDE tools beside other sources' in one server. `ENV_VARS`, beside
  `SOURCE`, names the variables the package reads: none, as the API is keyless.
  (https://github.com/xippios/sdk-core/issues/245,
  https://github.com/xippios/sdk-template/issues/81)

### Changed

- `docs/upstream/FETCHED.md` lists the pages that the snapshot's pages link and the
  snapshot does not request in a table `Not fetched`, each with its reason, where a
  paragraph named some of them: 147 rows, the folder of ESMIS's release files, the 72 data
  files of the historical data page and the files that Historical Changes & Revisions
  links among them. `scripts/refresh_upstream.py` writes the table from `NOT_FETCHED`, as
  sdk-core's conventions §3 ask, so that the next capture writes it too.
  (https://github.com/xippios/sdk-usda-wasde/issues/47)
- The packaged lists are the November 2026 release's (ESMIS release 796142), where they
  were October 2026's: `list_tables`, `list_commodities` and `list_regions` answer
  `meta.vintage` `November 2026`, `meta.endpoint` `wasde1126.xml` and `meta.retrieved_at`
  2026-11-20T18:03:38Z, every record's `report_month` is `November 2026`, and the
  descriptions of the tools `usda_wasde_list_tables`, `usda_wasde_list_commodities`,
  `usda_wasde_list_regions` and `usda_wasde_get_balance_sheet` name the November 2026
  release. Eight of the 30 tables state new footnotes, page 12's without its note on
  July's corn area and yield, page 35's on the November projection, and the titles of
  pages 35 to 37 read `Reliability of November Projections`. The 43 matrices, the 70
  regions and the 451 row labels keep their records but the month, and no record was
  added or removed. (https://github.com/xippios/sdk-usda-wasde/issues/43)
- The parsers' refusal of an XML attribute or an XLS cell that the known layout lacks names
  `docs/upstream/OBSERVED.md`, where it named `docs/upstream/layout.md`: the notes on what
  no upstream page documents, the layouts of a release's four files and ESMIS's list of
  WASDE releases, move there, each ending with the date and the release file or sample it
  was read from. The descriptions of the tools `usda_wasde_get_table`,
  `usda_wasde_get_balance_sheet` and `usda_wasde_read_report_text` no longer cite a
  decision by a name and a date. (https://github.com/xippios/sdk-usda-wasde/issues/13,
  https://github.com/xippios/sdk-usda-wasde/issues/12)
- `xippios-usda-wasde-mcp` names itself in its usage line and its errors, an unknown option
  ending `xippios-usda-wasde-mcp: error: unrecognized arguments: --bogus`, where they named
  the server, `xippios-usda-wasde`. Its help says that `--allow-remote` changes nothing on
  this read server, which is not held to loopback, where it spoke of a write server.
  (https://github.com/xippios/sdk-core/issues/167)
- A tool's error answer sets `isError` on its result beside the text
  `error: <ErrorClass>: <message>`, so a client tells `usda_wasde_get_balance_sheet`'s
  refusal of `"corn"` from data without reading the text.
  (https://github.com/xippios/sdk-core/issues/168)
- A refusal that names another task names its MCP tool too: `get_table`'s refusal of a page
  the packaged list lacks points to `list_tables` (over MCP, the tool
  `usda_wasde_list_tables`), `get_balance_sheet`'s of a commodity or a region to
  `list_commodities` or `list_regions` (`usda_wasde_list_commodities`,
  `usda_wasde_list_regions`), and its refusal of a month whose file lacks the matrices to
  `get_table` (`usda_wasde_get_table`). (https://github.com/xippios/sdk-core/issues/111)
- A route answers an argument that its schema refuses, a `get_table` without `table` or a
  `list_releases` whose `since` is no date, as problem details before the task runs: HTTP
  422, the title `InvalidRequestError` and the detail `<argument>: <message>`, such as
  `table: Field required`, where FastAPI's own 422 listed its error details with the
  input. (https://github.com/xippios/sdk-core/issues/66)
- The refusal of a page, a commodity or a region that the packaged lists lack ends with
  `If upstream added it since, the packaged list is out of date.`, where it named the
  maintainers' `/refresh-reference-data`, which an agent cannot run: `get_table("sr7")`
  names `sr37`, `sr27` and `sr17` and ends so. (https://github.com/xippios/sdk-core/issues/111)
- Adopts sdk-template v0.3.4, from v0.3.1, with conventions 1.27 and no new core minor: the
  floor stays `xippios-core~=0.3.0`, and no module or test changes. The README lists the
  documents a change follows under `## Documents`, and `CLAUDE.md` takes the place of
  `.claude/family.md`, which the update deletes, and cites sdk-core's records as
  `sdk-core ADR-NNNN`. (https://github.com/xippios/sdk-template/releases/tag/v0.3.4,
  https://github.com/xippios/sdk-usda-wasde/issues/10)
- Adopted sdk-template v0.3.1 (conventions §15), with no new core minor: the floor stays
  `xippios-core~=0.3.0`. `.github/CODEOWNERS` is rendered from the template's answers and
  names the code owner of the paths whose changes need one; `.gitignore` leaves copier's
  `*.rej` and `*.orig` out; `.claude/family.md`, `/adopt-release`, `/release-prep` and
  the PR template no longer describe how a pull request is merged.

### Breaking

- A tool refuses an argument that it does not declare before it runs, whatever its value,
  and names the ones it takes, where the argument was dropped and the tool ran without it:
  `usda_wasde_get_table` called with `year` answers
  `error: InvalidRequestError: year: Not an argument of this tool` with `table` and
  `month`, the arguments it takes, and downloads nothing, where it read the latest
  release's page. (https://github.com/xippios/sdk-core/issues/84)
- Adopts sdk-template v0.4.0, from v0.3.4, with `core_version=0.4.0`,
  `source_dependencies=[{name: usda-esmis, minor: "0.3", key_env: ""}]`: xippios-core 0.4.0
  and its conventions 1.28, and xippios-usda-esmis 0.3.0.
  (https://github.com/xippios/sdk-template/releases/tag/v0.4.0,
  https://github.com/xippios/sdk-usda-wasde/issues/39)
- Requires `xippios-core~=0.4.0`, from `~=0.3.0`, with its conventions 1.28, and
  `xippios-usda-esmis~=0.3.0`, from `~=0.1.0`. This package's tasks send the same requests
  and answer the same records through esmis 0.3. A caller that also calls esmis's own
  tasks takes esmis's changes since 0.1, among them `download_release_file` refusing a
  `dest` left out with `InvalidRequestError`.
  (https://github.com/xippios/sdk-core/releases/tag/v0.4.0,
  https://github.com/xippios/sdk-usda-esmis/releases/tag/v0.3.0)

## [0.1.1] - 2026-10-29

The first version on PyPI. 0.1.0 was tagged on 2026-10-28, on its release PR's merge,
but never published: the pending trusted publisher on PyPI named another project, and
a publish run whose tag exists cannot be re-run from the start, so the release is
re-done as a patch, as `publish.yml` prescribes. 0.1.1 ships 0.1.0 unchanged; what it
contains is listed under 0.1.0 in `CHANGELOG.md`.

## [0.1.0] - 2026-10-28

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for USDA WAOB World Agricultural Supply and Demand Estimates, MCP server and
  FastAPI router wired to the task layer, test harness with core's family check, CI,
  the nightly live tests and the release train, in which a release PR's merge tags and
  publishes.
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
