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
    get_balance_sheet,
    get_latest_release,
    get_release,
    list_commodities,
    list_releases,
    read_report_text,
)

latest = get_latest_release()  # the newest WASDE release in ESMIS
latest.data.id, latest.data.month  # "796099", "2026-10"
latest.meta.published_at  # 2026-10-09 12:00:00: ESMIS's printed time, no zone (ADR-0022)

releases = list_releases(since=date(2026, 1, 1))  # bound it: without since, 29 requests
[release.month for release in releases.data if release.revision]  # ["2026-06", "2026-05"]

page_12 = list_commodities(search="sr12")  # packaged with the package: no request
[row.commodity for row in page_12.data]  # ["FEED GRAINS", "CORN"]: matrix1 and matrix2

corn = get_balance_sheet("CORN")  # page 12's U.S. corn matrix, read from the latest XML
corn.meta.endpoint, corn.meta.vintage, len(corn.data)  # "wasde1026.xml", "October 2026", 60
corn.data[0].attribute, corn.data[0].cell_value  # "Area Planted", "90.9" (2024/25)

october = get_release("2026-10")  # Python only: every value, 6543 records, one download
narrative = read_report_text("2026-10")  # the XLS's sheet WASDE Text, one string a paragraph
narrative.data[1][:6]  # "WHEAT:"
```

Each record of `get_release` is one value of the release's tables with the labels its
page prints, as printed (`WasdeXmlCell`): 6543 for October 2026, pages 8 to 37. `unit`
is what the file states: the subtitle of the world and summary pages (8 to 10, 18 to 30),
the label of a reliability table for its average, smallest and largest; on the U.S.
pages it is `None`, since the XML does not say which of its repeated unit rows the page
shows (the XLS and the TXT print them in place). `list_tables`, `list_commodities` and
`list_regions` answer from lists packaged with the package, read from the October 2026
release's files by `scripts/refresh_reference.py` (`reference/README.md`) and refreshed
before each release: its 30 table pages with their titles, subtitles and footnotes, the
43 supply-and-use matrices of pages 11 to 30, 32 and 33 with their commodities, and its
70 region texts, as printed. The XML names none of these matrices' commodities as a
whole: on pages 12 to 15 they are the XLS's block titles; only page 32's records carry a
`commodity`, one per row (e.g. `Beef`, `Pork`, `Broiler`, `Turkey`, `Red Meat & Poultry`),
while the list names its matrix `Meats`, so `list_commodities(search="beef")` answers
nothing.

`get_table` and `get_balance_sheet` answer a slice of `get_release`'s records, a page or
one commodity's matrix, the world pages' rows of one region, named as the packaged lists
name them (`"CORN"` is page 12's U.S. corn, `"Corn"` the world corn pages; `"Argentina"`
matches `"        Argentina"`); each call downloads the month's XML and keeps nothing,
so a Python caller wanting several slices of one month calls `get_release` once.
`read_report_text` answers the narrative as text, from the XLS's sheet `WASDE Text`, or
from the PDF's narrative pages for a release without one; no figure is ever read from a
PDF. Task functions are listed in the status table below.

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
exactly tasks.__all__. -->

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| ESMIS `esmis_api_release_findByIdentifier` for `wasde`, through xippios-usda-esmis's `list_releases`, pages walked newest first | `list_releases(since=None, until=None)` | `usda_wasde_list_releases` | alpha |
| ESMIS `esmis_api_release_findByIdentifier` for `wasde`, page 0, through xippios-usda-esmis's `get_latest_release` | `get_latest_release()` | `usda_wasde_get_latest_release` | alpha |
| the release's XML file, downloaded through xippios-usda-esmis's `download_release_file`, parsed by `parse_wasde_xml` | `get_release(month=None)`, a bulk task | none, Python only | alpha |
| the XML's pages, their titles, subtitles, footnotes and matrices, packaged from the latest release (`reference/table.json`), no request | `list_tables(search=None)` | `usda_wasde_list_tables` | alpha |
| the XML's supply-and-use matrices of pages 11 to 30, 32 and 33 with their commodities, on pages 12 to 15 the XLS's block titles, packaged (`reference/commodity.json`), no request | `list_commodities(search=None)` | `usda_wasde_list_commodities` | alpha |
| the XML's region texts with their pages, packaged (`reference/region.json`), no request | `list_regions(search=None)` | `usda_wasde_list_regions` | alpha |
| one page of the release's XML, as `get_release` reads it, one download per call | `get_table(table, month=None)` | `usda_wasde_get_table` | alpha |
| one commodity's supply-and-use matrix of the release's XML, a U.S. or Mexico page or the world pages' rows of one region, matrices from `reference/commodity.json`, one download per call | `get_balance_sheet(commodity, region="United States", month=None)` | `usda_wasde_get_balance_sheet` | alpha |
| the release's narrative: its XLS's sheet `WASDE Text` read with xlrd, else its PDF's narrative pages read with pypdf, text only | `read_report_text(month=None)` | `usda_wasde_read_report_text` | alpha |

## Upstream terms and attribution

Data comes from USDA WAOB World Agricultural Supply and Demand Estimates (https://www.usda.gov/oce/commodity/wasde), on whatever terms upstream
states for it, if any; this package adds no rights to it. Documentation snapshot and its
attribution: `docs/upstream/FETCHED.md`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
