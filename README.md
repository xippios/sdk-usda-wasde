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

from xippios.usda.wasde import get_latest_release, get_release, list_releases

latest = get_latest_release()  # the newest WASDE release in ESMIS
latest.data.id, latest.data.month  # "796099", "2026-10"
latest.meta.published_at  # 2026-10-09 12:00:00: ESMIS's printed time, no zone (ADR-0022)

releases = list_releases(since=date(2026, 1, 1))  # bound it: without since, 29 requests
[release.month for release in releases.data if release.revision]  # ["2026-06", "2026-05"]

october = get_release("2026-10")  # Python only: downloads the XML, parses it, removes it
october.meta.endpoint, october.meta.vintage  # "wasde1026.xml", "October 2026"
corn = [cell for cell in october.data if cell.report == "sr12" and cell.matrix == "matrix2"]
corn[0].attribute, corn[0].market_year, corn[0].cell_value  # "Area Planted", "2024/25", "90.9"
```

Each record of `get_release` is one value of the release's tables with the labels its
page prints, as printed (`WasdeXmlCell`): 6543 for October 2026, pages 8 to 37. On pages
8 to 34 `unit` is `None`, since the file does not say which unit row the page shows;
the world pages state theirs in `sub_report_subtitle`. Task functions are listed in the
status table below.

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

## Upstream terms and attribution

Data comes from USDA WAOB World Agricultural Supply and Demand Estimates (https://www.usda.gov/oce/commodity/wasde), on whatever terms upstream
states for it, if any; this package adds no rights to it. Documentation snapshot and its
attribution: `docs/upstream/FETCHED.md`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
