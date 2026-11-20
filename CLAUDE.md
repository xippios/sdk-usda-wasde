# sdk-usda-wasde — instructions for Claude Code

`xippios-usda-wasde` wraps USDA WAOB World Agricultural Supply and Demand Estimates as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and its code rules. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file.

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA WAOB World Agricultural Supply and Demand Estimates, https://www.usda.gov/oce/commodity/wasde |
| API base URL | `https://esmis.nal.usda.gov`, ESMIS, which catalogs WASDE's releases and serves their files; this package reaches it only through `xippios-usda-esmis`'s tasks, and its own client sends nothing in 0.1.1 |
| Documentation | https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates and WAOB's pages under https://www.usda.gov/oce/commodity/wasde, snapshotted in `docs/upstream/` by `scripts/refresh_upstream.py` (`/refresh-upstream`); a page www.usda.gov refuses to automated requests is kept from USDA's CDN origin, usda.azureedge.us; no page names an OpenAPI or Swagger document, so `SPEC_URL` is `None`; the file layouts, as observed, in `docs/upstream/OBSERVED.md`, each note with the release file or sample it was read from |
| Credentials | none; the API is open |
| Rate limit | 30 requests per minute, burst 1, esmis's self-imposed pace (upstream documents no limit; sdk-core ADR-0033), kept by `xippios-usda-esmis`'s client, through which every request goes; `_client.py` configures the same pace for a client that sends nothing; no hourly or daily quota documented |
| Write tools | no, this package is read-only |
| Files | a release carries XML, XLS, TXT and PDF since 2016-10 (`docs/upstream/OBSERVED.md`); parsed in `parse/`, one module per file kind: the XML with the standard library's `xml.etree.ElementTree` (`parse/wasde_xml.py`); the XLS's narrative, sheet `WASDE Text`, with xlrd, a dependency (`parse/wasde_xls.py`), whose block titles of pages 12 to 15 the refresh script reads as well (`_vocabulary.py`); the PDF's narrative pages with pypdf, a dependency, text only (`parse/wasde_pdf.py`; sdk-core ADR-0020 decision 4); the TXT is not read; the parser tests read the samples under `tests/fixtures/files/`, their provenance in its `README.md` (sdk-core ADR-0020) |
| Depends on | `xippios-usda-esmis~=0.3.0`: the task layer and its models only, never `api/` or `_client`; this package's servers serve its own tasks, and an agent that wants a dependency's tools runs that package's server (sdk-core ADR-0021); used to list WASDE's releases in ESMIS's catalog and to download their files |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

## Layout

```
src/xippios/usda/wasde/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the one configured AsyncClient (base URL, rate limit), ENV_VARS and classify,
                   upstream's documented error shapes
  errors.py        the package's own error classes, where conventions §5 calls for one
  models.py        pydantic models mirroring upstream payloads (UpstreamModel); by the
                   family's precedent also an enumeration written by hand, for a value set
                   upstream documents and no packaged list renders. Here: Release, esmis's
                   release re-shaped, WasdeXmlCell, one value of a release's XML file,
                   WasdeTableValue, its projection without the page's labels that the
                   slices answer, WasdeXlsText and WasdePdfPage, a paragraph of its XLS's
                   narrative and a narrative page of its PDF, and Table, Commodity, Region
                   and Attribute, the records of the four packaged lists
  api/             endpoint wrappers, one module per upstream operation (conventions §2);
                   empty here: the package wraps no endpoint of its own; ESMIS's catalog
                   and the download are xippios-usda-esmis's tasks (sdk-core ADR-0021)
  parse/           file parsers, one module per file kind: parse_<file_kind>(path) -> list[Model];
                   wasde_xml.py, parse_wasde_xml; wasde_xls.py, parse_wasde_xls (the
                   narrative sheet); wasde_pdf.py, parse_wasde_pdf (the narrative pages)
  _vocabulary.py   the rules that build the four packaged lists from a release's XML records
                   and its XLS's block titles (xlrd); the refresh script and the live tests
                   call them, no task does
  tasks.py         task functions; __all__ is what the adapters register, but BULK_TASKS,
                   the Python-only ones; MCP_CAPS any per-tool result caps
  mcp.py           xippios-usda-wasde-mcp entry point: build() the tool set, server
  http.py          FastAPI router
  params.py        PACKAGED_LISTS, the four packaged lists' names
  enums.py         empty: no value list is packaged, so no enum is generated
  reference/       table.json, commodity.json, region.json and attribute.json, PackagedList
                   files, plus README with provenance
scripts/
  refresh_reference.py   downloads the latest release's XML and XLS through esmis (five
                         requests), builds the four lists with _vocabulary and writes them
                         with PackagedList.write; --keep and --from rebuild from kept files
  cut_sample.py          downloads one file of one release through esmis once (--format xml,
                         xls or pdf), writes its samples under tests/fixtures/files/wasde_<format>/
                         (XML pages cut verbatim, XLS sheets copied cell by cell with xlwt, a
                         PDF whole) and, if asked, the download fixture
  refresh_upstream.py    captures docs/upstream/ and writes FETCHED.md (/refresh-upstream): the
                         ESMIS and WAOB pages, www.usda.gov first, USDA's CDN origin where
                         www.usda.gov refuses
  adr_index.py           writes docs/adr.md and docs/adr.json from the records in docs/adr/;
                         --check fails while either is stale
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <wrapper>/<case>.json, never hand-written: esmis's
                   catalog answers under esmis's wrapper names (release_find_by_identifier/,
                   release_find_by_id/), the XML, XLS and PDF downloads under the task that
                   sends them (download_release_file/)
  fixtures/files/  a sample of each file kind, <file_kind>/<case>.<ext>; README.md, their provenance
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_parse.py    the XML parser's tests on the samples
  test_parse_xls.py, test_parse_pdf.py  the narrative parsers' tests on the XLS and PDF
                   samples, their refusals on workbooks and PDFs written in the test
  test_tasks.py    per-task replay tests, every tool through the MCP server, the list tasks
                   on the packaged files
  test_reference.py  the packaged lists against the samples, the list rules and refusals
  test_cut_sample.py  cut_sample.py's download fixture, its sample marked, written offline
  test_refresh_upstream.py  FETCHED.md as the capture script renders it, offline, with the
                   row of OBSERVED.md, which a snapshot leaves as written
  test_observed.py docs/upstream/OBSERVED.md as committed: the release files it was
                   written from, each note's date and file, every cited file present
  test_live.py     @pytest.mark.live smoke tests, one per task, the live parser tests on the
                   latest XML, XLS and PDF, and the packaged lists against the latest XML and
                   XLS, which one session fixture fetches once with the PDF
docs/
  upstream/        documentation snapshot, FETCHED.md, and OBSERVED.md, the notes written
                   by hand: the release files' layouts and the catalog as observed
  adr/             this package's design decisions, one NNNN-<slug>.md record each, laid
                   out in its README.md
  adr.md           the index of the decisions, written by scripts/adr_index.py, never by hand
  adr.json         the same index, for machines
  reports/         dated reports, the evidence a decision cites, laid out in its README.md
changelog/         the next release's changelog entries, one fragment per change, laid out
                   in its README.md
CHANGELOG.md       the releases, each section assembled from the fragments
.github/workflows/ ci.yml (the required ci check, with the changelog and fixture-size steps),
                   publish.yml (the release train: tag, build, PyPI), live.yml (nightly live
                   tests), organization.yml (the organization's checks from xippios/.github:
                   conventions, a review of a pull request against the documents the README
                   lists, and adr-index, which runs scripts/adr_index.py --check),
                   siblings.yml (the sibling proof of sdk-core ADR-0006: this wheel beside the
                   siblings under xippios.usda and the source packages it depends on (sdk-core ADR-0021), a visible check the ruleset does not require)
.github/scripts/   check-siblings.sh, which siblings.yml runs; the template's, as is the workflow
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep
```

The import path is `xippios.usda.wasde` (sdk-core ADR-0006); `src/xippios/` is a
namespace package, and so is `src/xippios/usda/`, the provider level.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this Layout says so (conventions §2).

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1

uv run xippios-usda-wasde-mcp   # stdio; add --http for streamable HTTP
```

`uv run pytest` is offline: core's plugin refuses the network and skips the rate limiter's
waits in every test not marked `live` (conventions §10, sdk-core ADR-0035). A test that
asserts a limiter wait or a quota pause is marked `rate_limited`, one that must reach the
network `network`.

`.github/workflows/live.yml` runs the live tests nightly at 02:26 UTC, a time derived from
the slug, and on demand; a pull request never runs them.
Its `uv run pytest -m live --tb=short --assert=plain` step reads no secret: the API needs no
key.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Code rules

- Three layers (sdk-core ADR-0001, conventions §2): endpoint wrappers in `api/`, task
  functions in `tasks.py`, adapters in `mcp.py` and `http.py`. The adapters register
  `tasks.__all__` and call only tasks, the tasks call only wrappers and reference data, and
  a wrapper returns models.
- Upstream's documented error shapes go into `classify` in `_client.py`, once, and an error
  class of the package's own into `errors.py`; a wrapper never inspects a status code
  (conventions §5, §6).
- One limiter paces each host the package sends to (conventions §2, §6). A second base URL
  on the host of the API base URL goes through the one `client` of `_client.py` by its
  absolute URL, and `classify`'s path checks name both bases. An origin or mirror that the
  publisher runs itself, where its canonical host refuses automated requests, takes that
  host's pace through the same client, and `docs/upstream/` names both hosts; a mirror that
  anyone else runs is never sent to. A host that a dependency sends to is reached through
  the dependency's tasks alone. Any other host gets a client of its own in `_client.py`,
  its base URL and its `RateLimit` beside the first's, and a row of its own in the table
  under What this package wraps, with its pace and where the pace comes from.
- A change brings its tests, written before the code, and passes the offline checks above;
  its changelog entry is a fragment under `changelog/`, one file holding its bullet, as
  `changelog/README.md` lays it out (conventions §12). Commit subjects follow Conventional
  Commits (conventions §13): the rule binds a pull request's own commits, not the commit
  that lands the pull request on `main`, whose subject GitHub writes.
- `ruff` leaves `docs/` and `.claude/` alone (`pyproject.toml`), so the upstream snapshot
  keeps its bytes: never reformat it.
- A convention that seems wrong is followed anyway and said in the pull request; changing
  it is a change of sdk-core's `docs/conventions.md` with an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping it for key patterns
  (conventions §10).
- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`, `_TOKEN`
  or `_SECRET`.
- Never write a key, a token or another credential into a file or a commit.
- Never put logic in `mcp.py` or `http.py`, and never add a route or a tool by hand: the
  adapters register `tasks.__all__` (sdk-core ADR-0001).
- Never rename or re-map an upstream concept to another source's (sdk-core ADR-0028).
- Never return a documented personal identifier in a task's projection, echo one in
  `meta.request`, or commit one in a fixture (sdk-core ADR-0017).
- Never edit `docs/upstream/` by hand but `docs/upstream/OBSERVED.md`, the notes on what
  upstream does but never documents, here the file layouts as observed:
  `/refresh-upstream` fetches the rest, and the pull request shows its diff (conventions
  §3).
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and the
  package (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone (conventions §12).

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15): the
update renders the template's files again and never overwrites the files this package
fills, `__init__.py`, `_client.py`, `errors.py`, `models.py`, `api/`, `parse/`, `tasks.py`,
`tasks_write.py`, `params.py`, `enums.py`, `reference/`, `scripts/refresh_reference.py`,
`scripts/refresh_upstream.py`, `tests/test_tasks.py`, `tests/test_live.py`,
`tests/fixtures/`, `docs/upstream/`, `docs/adr.md`, `docs/adr.json`, `README.md`,
`CHANGELOG.md` and `CLAUDE.md`. sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

## When something is unclear

Prefer the smallest change that satisfies the documents the README lists, state the
assumption in the pull request's description, and stop rather than guess at upstream
semantics or the shape of the public API.

## USDA WAOB World Agricultural Supply and Demand Estimates specifics

- **Releases.** WASDE is the ESMIS publication `"wasde"`: 703 releases on 2026-10-28, from
  1973-09-17, the newest first, 25 a page. `list_releases` and `get_latest_release`
  re-shape esmis's tasks into `Release` (`UpstreamModel.project`: id and time copied,
  files, revision and month parsed from esmis's fields) and keep esmis's `meta.endpoint`
  (`esmis_api_release_findByIdentifier`), `meta.total` and printed release time
  (`published_at` with `+0000` dropped, `published_at_naive`; sdk-core ADR-0041). A month
  is `"YYYY-MM"`, the printed date's. Since 2024-12 a reposted month is one release whose
  files carry `v2` (`wasde0626v2.xml`; `Release.revision`) and the original is not
  catalogued, so such a month answers its revision. Release 95621 (2013-08) lists the
  original's XML, `ORIGwasde-08-12-2013.xml`, before the revision's,
  `wasde-08-12-2013.xml`, and esmis's `download_release_file`, given a format alone, takes
  the first file of that format, so `get_release("2013-08")` reads the original
  (https://github.com/xippios/sdk-usda-wasde/issues/20 asks for the revision);
  2013-07 (95622) lists `R1` and `ORIG` PDF and XLS files beside one XML without a
  prefix. `get_release(month)` takes the month's latest release that carries an XML
  file (https://github.com/xippios/sdk-usda-wasde/pull/3): in
  2010-12 and 2014-01 a later release carries a TXT or an ASC only and the month answers
  the earlier one's XML; a month whose releases carry none (every month before 2010-07)
  is refused, naming their formats and the first release with one (2010-07-09, release
  95659).
- **The XML** (`parse/wasde_xml.py`, its docstring the rules). One generic walker sorts
  every attribute into a dimension, a value, a unit, layout text or a page attribute; any
  other raises `ValidationError` naming the page, element and attribute. A field is the
  attribute's name with the matrix index removed (`m1_commodity1` is `commodity`;
  page 11's class columns `attribute_group2` give `attribute_group`), labels as printed,
  with three exceptions (https://github.com/xippios/sdk-usda-wasde/pull/3): the page's and the table's
  names are kept on the
  record under names of their own, as conventions §3 keeps sheet and table names
  (`report` holds `Name`, `table` the `sub_report_title`, `sub_report_title2` or
  `sub_report_title3`, `matrix` the report item's element name); a dimension the pages
  spell several ways is folded into one field (`attr_desc` into `attribute`,
  `wb_forecast_month_desc` into `forecast_month`); and every value goes into
  `cell_value`, `wb_value` and the reliability statistics included, the statistic's name
  into `statistic`. The parser knows the October 2026 layout; the live test checks it
  against the current release nightly, and an older file with an attribute or a
  structure it does not know raises `ValidationError`.
  A page's titles, subtitles and footers go to its report items in document order: one
  to all, N to N (pages 9, 11, 16, 31, 33, 37 checked). October 2026 gives 6543
  records: 5913 table values and 630 reliability statistics (`statistic` names the
  attribute without the table index). The U.S. pages print a commodity heading over each
  matrix that the file does not hold (`FEED GRAINS`, `CORN` on page 12): `matrix` tells
  them apart, and `list_commodities` names them from the XLS.
- **Units.** `unit` carries only what the file states for the row or the page
  (https://github.com/xippios/sdk-usda-wasde/pull/3). On the reliability pages `average`, `smallest` and
  `largest` take the nearest `commodity_label` of their table at or before them, as the
  page reads; the other four statistics stay `None`. On a page whose XML holds no unit
  attribute (pages 8 to 10, 18 to 30) a table value takes its table's
  `sub_report_subtitle` as printed. On the U.S. pages (11 to 17, 31 to 34) it is `None`:
  the XML carries no per-row unit for them, since it repeats every unit row in every row
  group of a matrix, each with its text, and keeps no trace of which the page prints,
  and a unit on a value's path is its column's share of a unit printed across columns;
  the XLS and the TXT print the unit rows in place.
- **The slices** (https://github.com/xippios/sdk-usda-wasde/pull/5). `get_table(table, month)` answers the
  values of one page, `get_balance_sheet(commodity, region, month)` those of one
  commodity's supply-and-use matrix; both read the month's XML through `get_release`'s
  lookup and read (`_releases`, `_read_xml`), one download per call and nothing kept,
  and answer its `meta` with the arguments given. Their records are `WasdeTableValue`,
  `WasdeXmlCell` projected with `UpstreamModel.project` without the page's labels,
  `page_title`, `sub_report_subtitle`, `sub_report_footer` and `report_month`:
  `list_tables` states the page's titles,
  subtitles and footnotes once, to which a marker in a label (`Trade 2/`) refers, and
  the month is `meta.vintage`; `get_release` keeps the full record. The page, the commodity and the
  region are checked against the packaged lists before anything is sent, case kept; a
  near miss raises core's `UnknownCode` naming the closest (core's `closest` on the
  texts, so `"corn"` names `CORN` and `Corn`). A balance sheet is the U.S. or Mexico
  matrix the commodity list names for `"United States"` (the default) or `"Mexico"`,
  told apart from page 11's by-class table by its title (`BY_CLASS`, left to
  `get_table`); else the rows of the commodity's world matrices whose region, stripped of
  indent and footnote marker (`_bare`), is the one given, so `"United States"` answers
  the world table's U.S. rows for Coarse Grain, Corn, Rice, Soybean, Soybean Meal and
  Soybean Oil, which have no U.S. matrix under that name. A record is kept where its
  page, matrix and title are a packaged matrix's: a month's file that holds none raises
  `NotFoundError`. The MCP caps (`MCP_CAPS`; sdk-core ADR-0038; the same pull request):
  `get_table` 400 rows or 128 KB, its note naming `get_balance_sheet` for
  one matrix or region and Python for the whole page; `get_balance_sheet` 300 rows or 128
  KB, its note naming a region on the world pages and Python for the whole matrix;
  every other tool the default, whose note's narrowing only `list_releases` (`since`,
  `until`) can need. A value is about 350 bytes of the tool's JSON, so every answer of
  October 2026 fits whole: the largest page, sr28, 364 values and 129,899 bytes, 1,173
  under the bound; the largest balance sheet, Meats, 280 values and 90,850 bytes; the
  measured sizes are in the comment above `MCP_CAPS`.
- **The narrative** (https://github.com/xippios/sdk-usda-wasde/pull/5). `read_report_text(month)` reads the
  release's XLS, sheet `WASDE Text` (`parse/wasde_xls.py`): one string per row with
  text, verbatim (25 for October 2026, the first `WASDE - 676\r`), `meta.vintage` the
  month cell (0, 0) of the first `Page N` sheet prints (`October 2026`). A release
  without an XLS, or whose XLS has no such sheet or no text in it while it has a PDF,
  is read from the PDF (`parse/wasde_pdf.py`, pypdf): one string per page from page 1
  up to the first page that prints `Interagency Commodity Estimates Committees` on a
  line of its own, after its running header (`WASDE-484-6`, `WASDE-676-6`): pages 1 to
  5 in July 2010 and October 2026; no later page is read, no figure comes from a PDF
  (sdk-core ADR-0020 decision 4), and `meta.vintage` is the ESMIS release id as esmis
  prints it (`"95659"`), since the narrative prints a date, not a month label
  (sdk-core ADR-0020 decision 5). The release is the month's latest that carries an XLS or a
  PDF; a month whose releases carry neither is refused naming their formats. ESMIS
  lists revision workbooks as the XLS of some releases of 2001 to 2008, and which older
  report workbooks hold the sheet is unknown: hence the fallback.
- **Samples and fixtures.** Six samples under `tests/fixtures/files/wasde_xml/`, each a
  verbatim cut of whole pages of the October 2026 file under 256 KiB, one under
  `wasde_xls/`, the October 2026 XLS's sheets `WASDE Text` and `Page 8` copied cell by
  cell with xlwt (a dev dependency), and one under `wasde_pdf/`, the July 2010 PDF
  whole (release 95659), all written by `scripts/cut_sample.py`, one download each,
  provenance in its `README.md`. The download's replay fixtures under
  `download_release_file/` are the recorded exchanges, `wasde1026_xml.json` with the
  sample `sr08_sr35_sr36.xml` as its body, `wasde1026_xml_sr11_sr24.json` with
  `sr11_sr24.xml` and `wasde1026_xls.json` with the XLS sample (base64), each marked
  `sample` with the whole file's `original_bytes` and `sha256`, rewritten in the script's
  own step and written with core's `write_fixture` (sdk-core ADR-0020, amendment
  2026-11-18, point a; sdk-core ADR-0042, decision 4), and `wasde-07-09-2010_pdf.json`
  with the whole PDF (base64); the secret scan skips their `sha256` lines and reads the
  two base64 bodies, the XLS's and the PDF's, as secrets, which `.secrets.baseline`
  holds audited, `is_secret: false`: no line rule tells a base64 body from a token
  (https://github.com/xippios/sdk-usda-wasde/pull/5). Release
  95659 carries an XLS too, so the PDF path replays it with its XLS left out. `.gitattributes` marks
  `tests/fixtures/files/**` `-text`, so no checkout converts the samples' CRLF
  (https://github.com/xippios/sdk-usda-wasde/pull/3). The catalog fixtures are esmis's
  answers recorded here through core's recorder with esmis's client (sdk-core ADR-0021).
- **The packaged lists** (https://github.com/xippios/sdk-usda-wasde/pull/4). `reference/table.json`
  (30 pages with their titles, subtitles and footnotes, stated once for the page),
  `commodity.json` (43 matrices), `region.json`
  (70 texts) and
  `attribute.json` (451 row labels) are `PackagedList` files, written by
  `scripts/refresh_reference.py` from the latest release's XML and XLS with
  `PackagedList.write`, never by hand; each is named after its `param` (`table`,
  `commodity`, `region`, `attribute`; conventions §3), `endpoint` the XML's name as
  ESMIS catalogs it (`wasde1026.xml`), `fetched` the UTC time the XML was complete,
  `note` the provenance (the release, its `Report_Month`, for the commodity list the
  XLS and the positional rule), and every record carries `report_month`, which the list
  tasks give as `meta.vintage`. `list_tables`, `list_commodities` and `list_regions`
  answer from them without a request, `meta` from `PackagedList.meta`, `search` through
  core's `matches`, the default MCP cap (the largest answer 29,639 bytes); the attribute
  list has no task in 0.1.1 and is kept for the tasks that name a table's rows. The
  commodity list holds one record per report item of the supply-and-use pages, 11 to 30,
  32 and 33; the XML names none
  of their commodities as a whole: only page 32's records carry a `commodity`, one per
  row (e.g. `Beef`, `Pork`, `Broiler`, `Turkey`, `Red Meat & Poultry`), while the list names
  its matrix `Meats`, so `list_commodities(search="beef")` answers nothing. On pages 12
  to 15 the commodity is the XLS's block title, the
  Nth of sheet `Page N` (column 0 of a header row whose other cells hold market years)
  for the Nth item, and the script refuses to write when a page's counts differ;
  elsewhere it is the title's words between its region and `Supply and Use`; `region`
  is `United States` for a `U.S.` title, `Mexico` and `World` as printed. Region texts
  stay as printed, with indents and footnote markers; `get_balance_sheet` matches a
  region against the text stripped of both. The rules are
  `_vocabulary.py`'s docstring. Nothing is generated into `enums.py` (no value list) and
  `params.PACKAGED_LISTS` names the four files, as the template's
  `/refresh-reference-data` expects; the script replaces the template's `LISTS`,
  `ID_LISTS` and `TABLES` and its `--render-only`, as sdk-usda-esmis's does. The refresh
  budget: five keyless requests (the latest release, then the release and the file for
  the XML and for the XLS), about 3.7 MiB, at esmis's pace. The lists are refreshed
  before each release, in the release train's refresh PR (conventions §12), so each
  release ships the lists of the latest WASDE, its month
  their vintage (sdk-core ADR-0041 decision 1); a refresh that reproduces them record for
  record needs no PR: 0.1.1 ships those of ESMIS release 796099 (October 2026), which the
  refresh of 2026-10-28 reproduced. `--keep DIR` keeps the downloaded files with what
  the run learnt of them, `--from DIR` rebuilds from them without a request.
- **Live budget.** The nightly run fetches the latest release only, each file kind once
  (https://github.com/xippios/sdk-usda-wasde/pull/3 and https://github.com/xippios/sdk-usda-wasde/pull/5): one session
  fixture runs `get_release()` and
  keeps the XML for the live parser test, then downloads the release's XLS and PDF once
  each, for the block titles and the narrative parsers' live tests; the live tests of
  the three list tasks build the lists from those files and compare them with the
  packaged ones, every field but `report_month`, with the month word of the reliability
  titles masked (`Reliability of <Month> Projections`, pages 35 to 37: every release
  names its own month; https://github.com/xippios/sdk-usda-wasde/pull/4) and each table footer,
  `sub_report_footer` to
  `sub_report_footer3`, compared only for whether it is set on both sides, never its
  text, which changes every release (the same pull request), a
  difference naming the rows. `get_table`,
  `get_balance_sheet` and `read_report_text` run live through the fixture `served`,
  their lookups live, core's `AsyncClient.download` copying the session's file. Sixteen
  keyless requests, three of them downloads, about 4.7 MB.
