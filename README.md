# xippios-usda-wasde

Typed Python client, MCP server and FastAPI routes for
[USDA WAOB World Agricultural Supply and Demand Estimates](https://www.usda.gov/oce/commodity/wasde), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-usda-wasde            # client only
uv add "xippios-usda-wasde[mcp]"     # + MCP server
uv add "xippios-usda-wasde[http]"    # + FastAPI router
```

It depends on `xippios-usda-esmis`, installed with it, to list WASDE's releases in ESMIS's
catalog and to download their files; this package's server serves its own tools only.

No API key is needed.

## 30-second example

```python
from datetime import date

from xippios.usda.wasde import (
    get_data,
    get_report_text,
    list_commodities,
    list_releases,
)

releases = list_releases(since=date(2026, 1, 1))  # bound it: without since, 29 requests
releases.data[0].id, releases.data[0].release_datetime  # "796142", 2026-11-10 12:00:00+00:00

corn = get_data(2026, 10, commodity="CORN")  # page 12's U.S. corn, from the XML and the XLS
corn.meta.endpoint, corn.meta.vintage  # "wasde1026.xml", "796099": the ESMIS release id
row = corn.data[0]
row.table_label, row.commodity_source  # "U.S. Feed Grain and Corn Supply and Use", "xls"
row.attribute_label, row.market_year_label, row.value  # "Area Planted", "2024/25", "90.9"
[note.text for note in row.footnotes]  # the table's note and its 1/, as printed

list_commodities(2026, 10, search="rice")  # the month's own commodities: "TOTAL RICE", "Rice"
narrative = get_report_text(2026, 10)  # the XLS's sheet WASDE Text, one string a paragraph
narrative.data[1][:6]  # "WHEAT:"
```

`get_data` answers one record per value of a month's tables, pages 8 to 37 of the
release's XML, complete in itself (`WasdeRecord`; sdk-core ADR-0060, decision 7): the
report's number and month, the table's title, the commodity, the region, the market year
with its status, the forecast month, the row label with its class and statistic, the
unit, `value` as printed (`"10.45 *"`) with `value_number` beside it (`10.45`), and the
footnotes with their texts. Each label stands as printed and beside it its `_label`, the
text with its line breaks, runs of spaces and footnote marks left out, which the
filters `commodity`, `region` and `table` compare. Where the XML names the commodity or
the region only in the table's title, the record reads it there; on pages 12 to 15, whose
XML names no table's commodity, it reads the block title of the same release's XLS, or
where the XLS cannot be read a fixed table of the report's layout, and
`commodity_source` says which: `title`, `xls` or `layout`. `unit` is what the file
states: the subtitle of the world and summary pages (8 to 10, 18 to 30), the label of a
reliability table for its average, smallest and largest; on the U.S. pages it is `None`,
since the XML does not say which of its repeated unit rows the page shows.

`list_tables`, `list_commodities` and `list_regions` answer the distinct labels of the
month's own records, read from its file, so every label and footnote is the month's.
`get_data` and the three lists refuse a month before July 2010, the first whose WASDE has
an XML file, before anything is sent: the TXT tables before it are
https://github.com/xippios/sdk-usda-wasde/issues/31. Of the later XML files, those of
2020-10, 2024-12 and 2025-05 read whole, as the October 2026 samples do, while July 2010's
raises `ValidationError` at its root and those of 2011-07, 2013-08 and 2014-10 at pages 35
to 37, each after its download (`docs/upstream/OBSERVED.md`, "Older and revised files";
https://github.com/xippios/sdk-usda-wasde/issues/19). With xippios-usda-esmis 0.3.0, whose
walk of ESMIS's list of releases ends early (`docs/upstream/OBSERVED.md`, "The order of the
pages"), a month from 1995-02 to 2018-11 raises `NotFoundError` as one without a release,
the same for `get_report_text`, until the package takes xippios-usda-esmis 0.4.0, which
mends the walk (https://github.com/xippios/sdk-usda-esmis/pull/71). Each call downloads the
month's file and keeps nothing. `get_report_text` answers the narrative as text, from the XLS's
sheet `WASDE Text`, or from the PDF's narrative pages for a release without an XLS or
whose XLS has no such sheet; no figure is ever read from a PDF. `meta.vintage` of every
task that reads a file is the ESMIS release id. Task functions are listed in the status
table below.

## MCP

```json
{
  "mcpServers": {
    "usda-wasde": {
      "command": "uvx",
      "args": ["--from", "xippios-usda-wasde[mcp]", "xippios-usda-wasde-mcp"]
    }
  }
}
```

Tools are read-only and named `usda_wasde_<verb>_<noun>`. Results are capped, at
200 rows or 64 KB unless a tool has a cap of its own, with a note on how to see the rest.
`--http` serves streamable HTTP instead of stdio.

## Status

<!-- Core's family check (tests/test_family.py) reads this table: keep the "## Status"
heading and the "Task function" column. Each row's Task function cell starts with the
task's name in backticks, alone or as its call (`get_data(code, year)`); several tasks in
one row are backticked names separated by commas; prose may follow. The tables list
exactly tasks.__all__, and tasks_write.__all__ where the package has write tasks. -->

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| ESMIS `esmis_api_release_findByIdentifier` for `wasde`, through xippios-usda-esmis's `list_releases`, pages walked newest first | `list_releases(*, since=None, until=None)` | `usda_wasde_list_releases` | alpha |
| the month's XML, downloaded through xippios-usda-esmis's `download_release_file`, parsed by `parse_wasde_xml`, and for pages 12 to 15 the block titles of its XLS | `get_data(year, month, *, commodity=None, region=None, table=None)` | `usda_wasde_get_data` | alpha |
| the month's XML, its tables' titles | `list_tables(year, month, *, search=None)` | `usda_wasde_list_tables` | alpha |
| the month's XML and XLS, its records' commodities | `list_commodities(year, month, *, search=None)` | `usda_wasde_list_commodities` | alpha |
| the month's XML, its records' regions | `list_regions(year, month, *, search=None)` | `usda_wasde_list_regions` | alpha |
| the month's narrative: its XLS's sheet `WASDE Text` read with xlrd, else its PDF's narrative pages read with pypdf, text only | `get_report_text(year, month)` | `usda_wasde_get_report_text` | alpha |

## Upstream terms and attribution

Data comes from USDA WAOB World Agricultural Supply and Demand Estimates (https://www.usda.gov/oce/commodity/wasde), on whatever terms upstream
states for it, if any; this package adds no rights to it. Documentation snapshot and its
attribution: `docs/upstream/FETCHED.md`.

## Documents

- sdk-core: [docs/conventions.md](https://github.com/xippios/sdk-core/blob/main/docs/conventions.md) — the conventions every xippios source package follows: its layout, names, results, tests and releases.
- sdk-core: [docs/adr.md](https://github.com/xippios/sdk-core/blob/main/docs/adr.md) — the index of the family's architecture decisions, which the conventions cite.
- sdk-core: [docs/definition-of-done.md](https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md) — what a change satisfies before its pull request is opened.
- sdk-core: [docs/review-checklist.md](https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md) — what the review of a pull request checks, in order.
- sdk-usda-wasde: [docs/adr.md](https://github.com/xippios/sdk-usda-wasde/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.
- sdk-usda-wasde: [docs/upstream/FETCHED.md](https://github.com/xippios/sdk-usda-wasde/blob/main/docs/upstream/FETCHED.md) — the snapshot of the upstream documentation, the reference for names, parameters and semantics.
- sdk-usda-wasde: [docs/upstream/OBSERVED.md](https://github.com/xippios/sdk-usda-wasde/blob/main/docs/upstream/OBSERVED.md) — what no upstream page documents: the layouts of a release's XML, XLS, TXT and PDF and ESMIS's list of releases, as observed, each note with the file it was read from.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/sdk-usda-wasde/blob/main/LICENSE).
