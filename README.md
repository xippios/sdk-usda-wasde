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

It depends on `xippios-usda-esmis`, installed with it. <!-- what it uses each for, one line (ADR-0021 decision 6) -->

No API key is needed.

## 30-second example

```python
from xippios.usda.wasde import tasks

# result = tasks.<task>(...)
# result.data, result.meta.retrieved_at, result.meta.request
```

Task functions are listed in the status table below as they are added.

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
| (none yet) | | | |

## Upstream terms and attribution

Data comes from USDA WAOB World Agricultural Supply and Demand Estimates (https://www.usda.gov/oce/commodity/wasde), on whatever terms upstream
states for it, if any; this package adds no rights to it. Documentation snapshot and its
attribution: `docs/upstream/FETCHED.md`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
