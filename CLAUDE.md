# sdk-usda-wasde — instructions for Claude Code

`xippios-usda-wasde` wraps USDA WAOB World Agricultural Supply and Demand Estimates as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds the facts of this package;
the family rules every source shares are in `.claude/family.md`, which the next line imports.

@.claude/family.md

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA WAOB World Agricultural Supply and Demand Estimates, https://www.usda.gov/oce/commodity/wasde |
| API base URL | `https://esmis.nal.usda.gov`, ESMIS, which catalogs WASDE's releases and serves their files; this package reaches it only through `xippios-usda-esmis`'s tasks, and its own client sends nothing in 0.1.0 |
| Documentation | https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates and WAOB's pages under https://www.usda.gov/oce/commodity/wasde, snapshotted in `docs/upstream/` by `scripts/refresh_upstream.py` (`/refresh-upstream`); a page www.usda.gov refuses to automated requests is kept from USDA's CDN origin, usda.azureedge.us; no page names an OpenAPI or Swagger document, so `SPEC_URL` is `None`; the file layouts, as observed, in `docs/upstream/layout.md` |
| Credentials | none; the API is open |
| Rate limit | 30 requests per minute, burst 1, esmis's self-imposed pace (upstream documents no limit; ADR-0010), kept by `xippios-usda-esmis`'s client, through which every request goes; `_client.py` configures the same pace for a client that sends nothing; no hourly or daily quota documented |
| Write tools | no, this package is read-only |
| Files | a release carries XML, XLS, TXT and PDF since 2016-10 (`docs/upstream/layout.md`); parsed in `parse/`, one module per file kind: the XML with the standard library's `xml.etree.ElementTree` (`parse/wasde_xml.py`); the XLS with xlrd, a dependency, of which the refresh script reads the block titles of pages 12 to 15 for now (`_vocabulary.py`), its parser and the PDF's narrative (pypdf) to follow; the parser tests read the samples under `tests/fixtures/files/`, their provenance in its `README.md` (ADR-0020) |
| Depends on | `xippios-usda-esmis~=0.1.0`: the task layer and its models only, never `api/` or `_client`; this package's servers serve its own tasks, and an agent that wants a dependency's tools runs that package's server (ADR-0021); used to list WASDE's releases in ESMIS's catalog and to download their files |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and semantics.

## Layout

```
src/xippios/usda/wasde/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the one configured AsyncClient (base URL, rate limit) and classify,
                   upstream's documented error shapes
  errors.py        the package's own error classes, where conventions §5 calls for one
  models.py        pydantic models (UpstreamModel): Release, esmis's release re-shaped,
                   WasdeXmlCell, one value of a release's XML file, and Table, Commodity,
                   Region and Attribute, the records of the four packaged lists
  api/             empty: the package wraps no endpoint of its own; ESMIS's catalog and the
                   download are xippios-usda-esmis's tasks (ADR-0021)
  parse/           file parsers, one module per file kind: parse_<file_kind>(path) -> list[Model];
                   wasde_xml.py, parse_wasde_xml
  _vocabulary.py   the rules that build the four packaged lists from a release's XML records
                   and its XLS's block titles (xlrd); the refresh script and the live tests
                   call them, no task does
  tasks.py         task functions; __all__ is what the adapters register, but BULK_TASKS,
                   the Python-only ones; MCP_CAPS any per-tool result caps
  mcp.py           xippios-usda-wasde-mcp entry point
  http.py          FastAPI router
  params.py        PACKAGED_LISTS, the four packaged lists' names
  enums.py         empty: no value list is packaged, so no enum is generated
  reference/       table.json, commodity.json, region.json and attribute.json, PackagedList
                   files, plus README with provenance
scripts/
  refresh_reference.py   downloads the latest release's XML and XLS through esmis (five
                         requests), builds the four lists with _vocabulary and writes them
                         with PackagedList.write; --keep and --from rebuild from kept files
  cut_sample.py          downloads one release's XML through esmis once, writes the samples
                         under tests/fixtures/files/wasde_xml/ and the download fixture
  refresh_upstream.py    captures docs/upstream/ and writes FETCHED.md (/refresh-upstream): the
                         ESMIS and WAOB pages, www.usda.gov first, USDA's CDN origin where
                         www.usda.gov refuses
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, never hand-written: esmis's catalog answers under
                   esmis's wrapper names (release_find_by_identifier/, release_find_by_id/),
                   the XML download under the task that sends it (download_release_file/)
  fixtures/files/  a sample of each file kind, <file_kind>/<case>.<ext>; README.md, their provenance
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_parse.py    the parser's tests on the samples
  test_tasks.py    per-task replay tests, every tool through the MCP server, the list tasks
                   on the packaged files
  test_reference.py  the packaged lists against the samples, the list rules and refusals
  test_live.py     @pytest.mark.live smoke tests, one per task, the live parser test on the
                   latest XML, and the packaged lists against the latest XML and XLS, which
                   one session fixture fetches once
docs/upstream/     documentation snapshot and FETCHED.md
.github/workflows/ ci.yml (the required ci check, with the CHANGELOG and fixture-size steps),
                   publish.yml (the release train: tag, build, PyPI), live.yml (nightly live
                   tests), gates.yml (the merge gates as jobs, off until GATES_CALLER is 1)
                   siblings.yml (the sibling proof of ADR-0006: this wheel beside the
                   siblings under xippios.usda and the source packages it depends on (ADR-0021), a visible check the ruleset does not require)
.github/scripts/   check-siblings.sh, which siblings.yml runs; the template's, as is the workflow
.claude/family.md  the family rules, the template's, imported above
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep,
                   adopt-release
```

The import path is `xippios.usda.wasde` (ADR-0006); `src/xippios/` is a namespace
package, and so is `src/xippios/usda/`, the provider level.

## Commands

```bash
uv run pytest -m live --tb=short   # needs XIPPIOS_LIVE_TESTS=1

uv run xippios-usda-wasde-mcp   # stdio; add --http for streamable HTTP
```

`.github/workflows/live.yml` runs the live tests nightly at 02:26 UTC, a time derived from
the slug.
The API needs no key, so the workflow uses no secret.

## USDA WAOB World Agricultural Supply and Demand Estimates specifics

- **Releases.** WASDE is the ESMIS publication `"wasde"`: 703 releases on 2026-10-28, from
  1973-09-17, the newest first, 25 a page. `list_releases` and `get_latest_release`
  re-shape esmis's tasks into `Release` (`UpstreamModel.project`: id and time copied,
  files, revision and month parsed from esmis's fields) and keep esmis's `meta.endpoint`
  (`esmis_api_release_findByIdentifier`), `meta.total` and printed release time
  (`published_at` with `+0000` dropped, `published_at_naive`; ADR-0022). A month is
  `"YYYY-MM"`, the printed date's. Since 2024-12 a reposted month is one release whose
  files carry `v2` (`wasde0626v2.xml`; `Release.revision`) and the original is not
  catalogued, so such a month answers its revision. Release 95621 (2013-08) lists the
  original's XML, `ORIGwasde-08-12-2013.xml`, before the revision's,
  `wasde-08-12-2013.xml`, and esmis's `download_release_file` takes the first file of a
  format, so `get_release("2013-08")` reads the original (esmis row 193 asks for a name
  selector); 2013-07 (95622) lists `R1` and `ORIG` PDF and XLS files beside one XML
  without a prefix. `get_release(month)` takes the month's
  latest release that carries an XML file (Johannes, 2026-10-28, G5 inside PR 3): in
  2010-12 and 2014-01 a later release carries a TXT or an ASC only and the month answers
  the earlier one's XML; a month whose releases carry none (every month before 2010-07)
  is refused, naming their formats and the first release with one (2010-07-09, release
  95659).
- **The XML** (`parse/wasde_xml.py`, its docstring the rules). One generic walker sorts
  every attribute into a dimension, a value, a unit, layout text or a page attribute; any
  other raises `ValidationError` naming the page, element and attribute. A field is the
  attribute's name with the matrix index removed (`m1_commodity1` is `commodity`;
  page 11's class columns `attribute_group2` give `attribute_group`), labels as printed,
  with three exceptions (gap, row 195): the page's and the table's names are kept on the
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
- **Units.** `unit` carries only what the file states for the row or the page (Johannes,
  2026-10-28, G5 inside PR 3). On the reliability pages `average`, `smallest` and
  `largest` take the nearest `commodity_label` of their table at or before them, as the
  page reads; the other four statistics stay `None`. On a page whose XML holds no unit
  attribute (pages 8 to 10, 18 to 30) a table value takes its table's
  `sub_report_subtitle` as printed. On the U.S. pages (11 to 17, 31 to 34) it is `None`:
  the XML carries no per-row unit for them, since it repeats every unit row in every row
  group of a matrix, each with its text, and keeps no trace of which the page prints,
  and a unit on a value's path is its column's share of a unit printed across columns;
  the XLS and the TXT print the unit rows in place.
- **Samples and fixtures.** Six samples under `tests/fixtures/files/wasde_xml/`, each a
  verbatim cut of whole pages of the October 2026 file under 256 KiB, written by
  `scripts/cut_sample.py` from one download, provenance in its `README.md`. The
  download's replay fixture `download_release_file/wasde1026_xml.json` is the recorded
  exchange with the sample `sr08_sr35_sr36.xml` as its body, marked `truncated` with the
  whole file's `original_bytes` and `sha256`, rewritten in the script's own step
  (ADR-0024); detect-secrets reads that sha256 as a secret, and `.secrets.baseline`
  holds it audited, `is_secret: false` (gap, row 124). `.gitattributes` marks
  `tests/fixtures/files/**` `-text`, so no checkout converts the samples' CRLF (gap,
  row 189). The catalog fixtures are esmis's
  answers recorded here through core's recorder with esmis's client (ADR-0021).
- **The packaged lists** (decided by Johannes on 2026-10-28, G5). `reference/table.json`
  (30 pages with their titles, subtitles and footnotes, stated once for the page:
  Johannes, 2026-10-28, G5 inside PR 5), `commodity.json` (43 matrices), `region.json`
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
  list has no task in 0.1.0 and is kept for the tasks that name a table's rows. The
  commodity list holds one record per report item of the supply-and-use pages, 11 to 30,
  32 and 33 (pages 32 and 33 by the session, 2026-10-28, rule 7); the XML names none
  of their commodities as a whole: only page 32's records carry a `commodity`, one per
  row (`Beef`, `Pork`, `Broiler`, `Turkey`, `Red Meat & Poultry`), while the list names
  its matrix `Meats`, so `list_commodities(search="beef")` answers nothing. On pages 12
  to 15 the commodity is the XLS's block title, the
  Nth of sheet `Page N` (column 0 of a header row whose other cells hold market years)
  for the Nth item, and the script refuses to write when a page's counts differ;
  elsewhere it is the title's words between its region and `Supply and Use`; `region`
  is `United States` for a `U.S.` title, `Mexico` and `World` as printed. Region texts
  stay as printed, with indents and footnote markers; a task that slices a table by
  region (to come) matches the text stripped of both (gap row 195). The rules are
  `_vocabulary.py`'s docstring. Nothing is generated into `enums.py` (no value list) and
  `params.PACKAGED_LISTS` names the four files, as the template's
  `/refresh-reference-data` expects; the script replaces the template's `LISTS`,
  `ID_LISTS` and `TABLES` and its `--render-only`, as sdk-usda-esmis's does. The refresh
  budget: five keyless requests (the latest release, then the release and the file for
  the XML and for the XLS), about 3.7 MiB, at esmis's pace. The lists are refreshed
  before each release, in the release train's refresh PR (conventions §12; Workflow
  rules), so each release ships the lists of the latest WASDE, its month
  their vintage (ADR-0022 decision 1). `--keep DIR` keeps the downloaded files with what
  the run learnt of them, `--from DIR` rebuilds from them without a request.
- **Live budget.** The nightly run fetches the latest release only, each file kind once
  (decided by Johannes on 2026-10-28): one session fixture runs `get_release()` and
  keeps the XML for the live parser test, then downloads the release's XLS once for the
  block titles; the live tests of the three list tasks build the lists from those files
  and compare them with the packaged ones, every field but `report_month`, with the
  month word of the reliability titles masked (`Reliability of <Month> Projections`,
  pages 35 to 37: every release names its own month; gap row 195), a difference naming
  the rows. Eight keyless requests, two of them downloads, about 3.7 MiB.
