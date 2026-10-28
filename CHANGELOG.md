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
  release, WAOB's WASDE page, historical data page and FAQ (kept from USDA's CDN
  origin, their www.usda.gov addresses, which refuse automated requests, recorded by
  status), and WAOB's 2018 notice of the file names; `layout.md` describes the XML, XLS,
  TXT and PDF files as observed in the October 2026 release and the file kinds and
  names of every release ESMIS lists.
