# Reference data for USDA WAOB World Agricultural Supply and Demand Estimates

Four lists ship here as packaged lists, versioned with the package, each read from the
latest WASDE release's files by `scripts/refresh_reference.py` (`/refresh-reference-data`)
and written with core's `PackagedList.write`, never by hand, in the file shape of
`PackagedList` (`param`, `endpoint`, `fetched`, `note`, `records`; conventions §3,
ADR-0022; decided by Johannes on 2026-10-28, G5). Each file is named after its `param`,
the parameter the list serves:

- `table.json`: one record per page of the XML, `sr08` to `sr37` (`models.Table`): its
  `Name`, the printed page number, its titles, subtitles and footers as printed, stated
  once for the page (`sub_report_footer` to `sub_report_footer3` of its `<Report>`, on
  pages 35 to 37 the one report item's `sub_report_footer`; Johannes, 2026-10-28, G5
  inside PR 5), its report items; `list_tables` answers from it.
- `commodity.json`: one record per supply-and-use matrix of the U.S. pages 11 to 17, 32
  and 33 and the world pages 18 to 30 (`models.Commodity`): the commodity, the region the
  title names, the page, the matrix and its title; `list_commodities` answers from it.
- `region.json`: every distinct `region` text of the XML as printed, indents and
  footnote markers kept, with the pages that print it (`models.Region`); `list_regions`
  answers from it.
- `attribute.json`: every distinct `attribute` text of the XML by page and matrix
  (`models.Attribute`), for the tasks that name a table's rows; no task answers with it
  in 0.1.0.

**The commodity on pages 12 to 15 is matched by position.** The XML names the commodity
of no matrix on the U.S. pages; pages 11, 16, 17, 32 and 33 name it in their titles
(`U.S. Wheat Supply and Use  1/`, `U.S. Milk Supply and Use`), but the titles of pages 12
to 15 name several
(`U.S. Feed Grain and Corn Supply and Use  1/`). There the XLS's sheet `Page N` prints a
block title in column 0 of each block's header row, the row whose other cells hold the
market years (`FEED GRAINS`, `CORN` on `Page 12`), in the order of the XML's report items
of the page: the Nth title is the commodity of the Nth item, taken verbatim. The script
refuses to write unless every one of the four pages has as many titles as report items,
and the nightly live test checks the match on the current release. Elsewhere the
commodity is the title's words between its region and `Supply and Use`, as printed
(`Wheat`, `Coarse Grain`, `Meats`); the region is `United States` for a title that starts
`U.S.`, `Mexico` and `World` as printed. Each file's `note` states its rule.

**When they are refreshed.** Before each release, in the release train's refresh PR of
its own (D15, conventions §12): a release ships the lists of the latest WASDE, whose
`Report_Month` is their vintage (ADR-0022 decision 1). Between releases the nightly live
tests compare the packaged tables, commodities and regions with the latest release's,
every field but `report_month`, with the month word of the reliability titles masked
(`Reliability of <Month> Projections`, pages 35 to 37), since every release names its
own month there; any other difference fails, naming the rows.

`endpoint` is the XML's name as ESMIS catalogs it (`wasde1026.xml`), the file every
record's page, matrix and labels come from; the commodity file's `note` names the XLS as
well. `fetched` is the UTC time the XML was complete. Every record carries the release's
`report_month` (`October 2026`), which the list tasks give as `meta.vintage`.

They load through `xippios.core.PackagedList`, which also builds the answer's `meta`:

```python
from xippios.core import PackagedList

from xippios.usda.wasde.models import Commodity

commodities = PackagedList.load("xippios.usda.wasde", "commodity")
rows = commodities.parse(Commodity, source="usda-wasde")
```

No enum is generated from them (`enums.py` holds none): they are tables of several
fields, no value list. One row per file, which the script rewrites: Origin is the files it
was read from, Fetched the file's `fetched`, the UTC time the XML was complete.

| File | Origin | Fetched |
| --- | --- | --- |
| `table.json` | `wasde1026.xml`, ESMIS release 796099 of 2026-10-09, its pages' `<Report>` attributes and the reliability items' footers (30 records) | 2026-10-28T16:26:51Z |
| `commodity.json` | `wasde1026.xml` and `wasde1026.xls`, ESMIS release 796099 of 2026-10-09, the XML's report items of pages 11 to 30, 32 and 33 and the XLS's block titles of pages 12 to 15 (43 records) | 2026-10-28T16:26:51Z |
| `region.json` | `wasde1026.xml`, ESMIS release 796099 of 2026-10-09, its `region` texts (70 records) | 2026-10-28T16:26:51Z |
| `attribute.json` | `wasde1026.xml`, ESMIS release 796099 of 2026-10-09, its `attribute` texts by page and item (451 records) | 2026-10-28T16:26:51Z |
