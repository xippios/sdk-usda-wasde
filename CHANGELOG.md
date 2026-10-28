# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

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
- `get_release(month)`, a bulk task, Python only: the latest release's, or the month's,
  XML downloaded through esmis into a temporary directory and parsed into one
  `WasdeXmlCell` per value, 6543 for October 2026; `meta.vintage` is the file's
  `Report_Month`, `meta.endpoint` the file's name.
- `parse.parse_wasde_xml(path)`: the XML of pages 8 to 37 read with the standard
  library's ElementTree, labels as printed, the reliability statistics with their
  carried unit; an attribute the parser does not know raises `ValidationError`.
- Six XML samples cut from the October 2026 file by `scripts/cut_sample.py`, the esmis
  catalog fixtures and the download's replay fixture, its body a sample; the live test
  fetches the latest XML once. `docs/upstream/layout.md` now says that the XML repeats
  each unit row in every row group, which unit a path carries, and which attributes on
  elements are layout text.
