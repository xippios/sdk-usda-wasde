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
