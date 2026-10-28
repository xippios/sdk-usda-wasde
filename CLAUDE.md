# sdk-usda-wasde — instructions for Claude Code

`xippios-usda-wasde` wraps USDA WAOB World Agricultural Supply and Demand Estimates as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds the facts of this package;
the family rules every source shares are in `.claude/family.md`, which the next line imports.

@.claude/family.md

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA WAOB World Agricultural Supply and Demand Estimates, https://www.usda.gov/oce/commodity/wasde |
| API base URL | `https://esmis.nal.usda.gov` |
| Documentation | https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates and WAOB's pages under https://www.usda.gov/oce/commodity/wasde, snapshotted in `docs/upstream/` by `scripts/refresh_upstream.py` (`/refresh-upstream`); a page www.usda.gov refuses to automated requests is kept from USDA's CDN origin, usda.azureedge.us; no page names an OpenAPI or Swagger document, so `SPEC_URL` is `None`; the file layouts, as observed, in `docs/upstream/layout.md` |
| Credentials | none; the API is open |
| Rate limit | 30 requests per minute, burst 1; a self-imposed pace: upstream documents no per-second or per-minute limit (ADR-0010); enforced client-side in `_client.py` <!-- name here an hourly or daily quota upstream documents, if any, and the QuotaPolicy that keeps it (ADR-0015) --> |
| Write tools | no, this package is read-only |
| Files | parsed in `parse/`, one module per file kind; the parser tests read the samples under `tests/fixtures/files/`, their provenance in its `README.md` (ADR-0020) <!-- each file kind upstream publishes, its format and the library that reads it --> |
| Depends on | `xippios-usda-esmis~=0.1.0`: the task layer and its models only, never `api/` or `_client`; this package's servers serve its own tasks, and an agent that wants a dependency's tools runs that package's server (ADR-0021) <!-- what this package uses each for, one line (ADR-0021 decision 6) --> |

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
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream operation
  parse/           file parsers, one module per file kind: parse_<file_kind>(path) -> list[Model]
  tasks.py         task functions; __all__ is what the adapters register, but BULK_TASKS,
                   the Python-only ones; MCP_CAPS any per-tool result caps
  mcp.py           xippios-usda-wasde-mcp entry point
  http.py          FastAPI router
  params.py        the packaged reference lists, read from reference/
  enums.py         StrEnums (IntEnums for integer ids) generated from the packaged lists;
                   never edited by hand
  reference/       packaged code lists (CSV/JSON) plus README with provenance
scripts/
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  refresh_upstream.py    captures docs/upstream/ and writes FETCHED.md (/refresh-upstream): the
                         ESMIS and WAOB pages, www.usda.gov first, USDA's CDN origin where
                         www.usda.gov refuses
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <endpoint>/<case>.json, never hand-written
  fixtures/files/  a sample of each file kind, <file_kind>/<case>.<ext>; README.md, their provenance
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_api.py      optional: the endpoint wrappers' own tests
  test_tasks.py    per-task replay tests
  test_live.py     @pytest.mark.live smoke tests, one per task
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

<!-- What only this package knows: upstream behaviour established by fixtures, the client's quirks, sections of its own. Fill this section or delete it. -->
