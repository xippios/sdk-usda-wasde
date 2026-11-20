- `docs/upstream/FETCHED.md` lists the pages that the snapshot's pages link and the
  snapshot does not request in a table `Not fetched`, each with its reason, where a
  paragraph named some of them: 147 rows, the folder of ESMIS's release files, the 72 data
  files of the historical data page and the files that Historical Changes & Revisions
  links among them. `scripts/refresh_upstream.py` writes the table from `NOT_FETCHED`, as
  sdk-core's conventions §3 ask, so that the next capture writes it too.
  (https://github.com/xippios/sdk-usda-wasde/issues/47)
