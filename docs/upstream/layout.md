# WASDE file layouts, as observed

**Observed, not documented.** No upstream page documents the layout of the files a WASDE
release carries (`FETCHED.md`, "Not snapshotted"). This file describes them as they were
observed on 2026-10-28 in the four files of one release and in ESMIS's list of every
WASDE release, as ADR-0020 decision 2 asks for file-format notes. It is written by hand
from those files, not fetched: `scripts/refresh_upstream.py` neither writes nor checks
it, and `FETCHED.md` lists it in a row of its own. What it states holds for the files
below; a parser that relies on it is checked against the current release by its live
test (ADR-0020 decision 6).

## What it was written from

The October 2026 release, ESMIS release 796099, released 2026-10-09, downloaded on
2026-10-28 through xippios-usda-esmis's `download_release_file`:

| File | URL | Bytes | sha256 |
| --- | --- | --- | --- |
| wasde1026.xml | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 |
| wasde1026.xls | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xls | 354304 | 5beb5732b587807d10a12fddf58c1c1120a08891bef4f361a346ab68a7906025 |
| wasde1026.txt | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.txt | 122378 | a60aa93db2328a5ccc0e7a96c8f9f0093d6b168f44b31969635c5a34e54786f6 |
| wasde1026.pdf | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.pdf | 939374 | 6cc97c08be7e683b6114ae8e16d49fce2f21dce3ed3f9933b0acbd2d37e6840b |

The sizes agree with those ESMIS's page of the release printed on 2026-10-28 (917.36 KB,
119.51 KB, 346 KB and 3.4 MB, in units of 1024). The release history below is read from
the 703 WASDE releases that xippios-usda-esmis's `list_releases("wasde")` returned on
2026-10-28, every page of the list. No other release file was read for this file.

## The four files

| Kind | Format | Holds |
| --- | --- | --- |
| XML | UTF-8 with a byte order mark, CRLF line ends, indented by two spaces | the tables of pages 8 to 37, one element per page, values as printed text |
| XLS | Excel 97-2003 workbook (BIFF8, OLE2 signature `D0 CF 11 E0 A1 B1 1A E1`) | the narrative in sheet `WASDE Text`, the tables of pages 8 to 37 in sheets `Page 8` to `Page 37`, values as numbers |
| TXT | ASCII, CRLF line ends, at most 80 characters a line | the tables of pages 8 to 37 as printed, fixed width |
| PDF | PDF 1.6, 40 pages | the whole report: narrative, tables, back matter |

The numbers a task returns come from the XML, the XLS or the TXT, never from the PDF
(ADR-0020 decision 4).

## XML

### Envelope

The file starts with a byte order mark and `<?xml version="1.0" encoding="utf-8"?>`. The
root is `<Report Name="wasde">`; its 30 children are `<sr08>` to `<sr37>`, one per
printed page 8 to 37, in page order, and each holds exactly one `<Report>` element whose
attributes describe the page:

| Attribute | On | Example |
| --- | --- | --- |
| `Name` | every page | `sr08` |
| `Report_Month` | every page | `October 2026` |
| `page_title` | every page | ` WASDE - 676 - 8`, with the leading space |
| `sub_report_title` | every page | `World and U.S. Supply and Use for Grains  1/` |
| `sub_report_subtitle` | sr08, sr09, sr10, sr14, sr18 to sr30 | `Million Metric Tons`, `(Million Metric Tons)` |
| `sub_report_footer` | sr08 to sr16, sr18 to sr24, sr26, sr28 to sr31 | the page's footnotes, `1/ Aggregate of local marketing years. …` |
| `sub_report_title2` | sr11, sr16, sr31, sr33 | the second table's title, `U.S. Wheat by Class: Supply and Use` |
| `sub_report_title3` | sr09 | `World and U.S. Supply and Use for Cotton  1/` |
| `sub_report_subtitle3` | sr09 | `Million 480-lb. Bales` |
| `sub_report_footer2` | sr09, sr25, sr27, sr31, sr32 | footnotes |
| `sub_report_footer3` | sr16, sr17, sr33, sr34 | footnotes |

On the reliability pages 35 to 37 the footnotes are the `sub_report_footer` of a table
element instead (`table1` on pages 35 and 36, `table4` on page 37). The page elements
range from 7239 bytes (`sr36`) to 238679 bytes (`sr33`) as they stand in the file.

### Structure

The element names (`matrixN`, `TextboxN`, a `<group>_Collection` around the instances of
each group) are those of an XML export of SQL Server Reporting Services; the file does not
name its producer, so this is an inference. A page's `<Report>` holds its report items:
`matrix1` to `matrix6`, crosstabs, on pages 8 to 34, and `table1` to `table4` on the
reliability pages 35 to 37. Inside a matrix, every group is an element
`<prefix>_<name>_Collection` holding one element per instance, and the instance carries
its label as an attribute: `<m1_commodity_group commodity1="Total Grains 4/">`,
`<m1_year_group market_year1="2024/25">`, `<m1_month_group forecast_month1="Sep">`. The
value is an attribute of an empty `<Cell>` element at the end of the path:

```xml
<m1_attribute_group>
  <s3 attribute1="Total&#xD;&#xA;Supply">
    <s4>
      <Cell cell_value1="3653.72" />
```

A value's labels are therefore the attributes of its ancestors, read from the matrix
down. The names are numbered per matrix (`market_year1` in `matrix1`, `market_year4` in
the first matrix of page 14) and not consistently: the second matrix of page 11 carries
its attribute label on `m2_month_group` and its forecast month on `m2_attribute_group`,
and page 29's third matrix nests `forecast_month2` inside `region6`. The table at the end
of this section gives each matrix's chain.

### Cells

| `Cell` attribute | Where | Count | What it holds |
| --- | --- | --- | --- |
| `cell_value1` to `cell_value6` | pages 8 to 30, 33, 34 | 5414 | a value as printed |
| `m1_cell_value1`, `m2_cell_value1` | pages 31, 32 | 475 | a value as printed |
| `wb_value` | page 16, the Mexico sugar table | 24 | a value as printed |
| `m1_unit_descr1` to `m1_unit_descr5`, `m2_unit_descr1` | pages 11, 12, 14 to 17, 33, 34 | 1422 | a unit as printed, on a row of its own (`Million Acres` before `Area Planted`), empty in the columns where the page prints none; the file repeats each unit row in every row group of its matrix, with its text (page 12's `Million Acres`, `Metric Tons` and `Million Metric Tons` in all 13 groups of its first matrix), and does not say which of them the page shows |
| `TextboxN`, `FormatFillerN`, `ReportFillerN`, `m1_filler2`, `m1_filler4`, `m2_filler2`, `m2_filler4`, `m3_filler2`, `m3_filler4`, `m1_formatfiller10` | most pages | 3126 | `filler` or `Filler` (36 `m1_filler2` cells on page 15 hold `1` to `4`): layout, no value of the table |
| none | most pages | 1090 | an empty `<Cell />` |

Of the 5913 value cells, 5883 hold a number as printed: digits with a decimal point
where the page prints one (`2858.26`, `824.20`), a comma as thousands separator (589
cells, `2,141`), a minus sign (33 cells). The rest are printed marks: on page 17 six
values carry the asterisks the page explains in its footnotes (`10.45 *`, `776 **`), and
on pages 26 and 27, 24 cells hold a footnote marker instead of a value (`3/`). A unit can
be split over several unit cells where the page prints it on two lines
(`Million 480 ` and ` Pound Bales`).

Units also stand on elements: `m1_unit_description1` and `m2_unit_description1` (pages
31, 32), `m2_unit_descr1` (page 11) and `m2_Unit_Description1` (page 16) are attributes
of the elements in a value's path. Each holds the text of its own column's cell, so a unit
printed across columns is split over them (`Million` over Broiler and ` Pounds` over
Turkey on page 31, `Million` and `Bushels` over two of page 11's six classes), and the
other columns hold an empty one. The XML thus carries no per-row unit for these pages;
the XLS and the TXT print the unit rows in place (below).

Other attributes on elements are layout text, not labels of a value: `m1_filler1` and its
like (`Filler`), page 13's `Textbox2` in a value's path (`Million Bushels` in 42 of 168),
page 31's `Textbox17` and `m2_formatfiller7` (`Annual`, over rows without values), page
34's `m1_attribute_title1` (`Milk Prices 2/` once, empty six times), and page 35's
`commodity_attribute2` (`Percent`, as `Textbox41` and `textbox4` on pages 36 and 37). The
U.S. pages print a commodity heading over each matrix (`FEED GRAINS` and `CORN` on page
12, `SORGHUM`, `BARLEY` and `OATS` on page 13) that no attribute of the file holds: there
the matrix tells the commodities apart.

### Labels as printed

Labels keep the page's text: a line break inside a label is a CR LF
(`Total&#xD;&#xA;Supply`; 4444 such breaks in the labels of the file, none in the page
attributes), footnote markers stay (`Trade 2/`, `Total&#xD;&#xA;Use 3/`, `World  3/`), and
the leading spaces that indent a row stay (`  Supply, Total 3/`), as do the two trailing
ones (`Area Harvested `). The year and month labels the October 2026 file uses:

| Label | Values | Pages |
| --- | --- | --- |
| `market_yearN` | `2024/25`, `2025/26 Est.`, `2026/27 Proj.` | 11 to 17 |
| `market_yearN` | `2024/25`, `2025/26 (Est.) `, `2026/27 (Proj.) `, with the trailing space | 8 to 11 |
| `market_yearN` | `2024`, `2025`, `2026 Proj.`, `2027 Proj.` | 33, 34 |
| `region_headerN` | `2024/25`, `2025/26 Est.`, `2026/27 Proj.`: the year heads the matrix | 18 to 30 |
| `m1_market_year1`, `m2_market_year1` | `2025`, `2026`, `2027`, `2026 Proj.`, `2027 Proj.` | 31, 32 |
| `forecast_monthN` | `Sep`, `Oct`, or empty for a year that is not projected | 8 to 17, 19, 21, 23, 25, 27 to 30, 33, 34 |
| `forecast_monthN` | `September`, `October` as well | 12 to 15 |
| `wb_forecast_month_desc` | `Sep`, `Oct` | 16 |
| `m1_forecast_month1`, `m2_forecast_month1` | quarters `I` to `IV`, with `*` when projected, `Annual`, `Sep Proj.`, `Oct Proj.` | 31 |
| `m1_forecast_month1` | `Sep`, `Oct`, or empty | 32 |

### Reliability pages 35 to 37

These pages have tables, not matrices, and no `Cell` elements: each row is one element
whose attributes are its labels and its values. On pages 35 and 36 a `region_group`
carries `region` and the seven values `root_mean_square_error`, `confidence_interval`,
`average`, `smallest`, `largest`, `below_final` and `above_final`, inside an
`attribute_group` (`attribute`: `Production`) inside a `commodity_group` (`commodity`:
`WHEAT`). The `commodity_group` carries `Percent` in `commodity_attribute2` (page 35),
`Textbox41` (page 36) or `textbox4` (page 37), and on pages 36 and 37 a `commodity_label`
with the commodity's unit (`Million Metric Tons`, `Million Bushels`); page 35's footnote
explains the measures. On page 37 the commodity label is `commodity1` on the
`commodity_group` of table 1 and `commodity2` to `commodity4` on `commodity_group2` to
`commodity_group4` in tables 2 to 4; the values sit on `attribute_group` (suffix `1`:
`root_mean_square_error1`, …) and on `commodity_group2` to `commodity_group4` (suffixes
`2` to `4`). Page 36's footnote says that no WASDE was published in October 2013 or
October 2025.

### Pages, titles and the path to each value

| Page | Titles | Item: labels from the outside in → value (cells) | Values |
| --- | --- | --- | --- |
| `sr08`, 8 | World and U.S. Supply and Use for Grains  1/ | matrix1: `commodity_header1` › `commodity1` › `market_year1` › `forecast_month1` › `attribute1` → `cell_value1` (80)<br>matrix2: `commodity_header2` › `commodity2` › `market_year2` › `forecast_month2` › `attribute2` → `cell_value2` (80) | 160 |
| `sr09`, 9 | World and U.S. Supply and Use for Grains, Continued  1/<br>World and U.S. Supply and Use for Cotton  1/ | matrix1: `commodity_header1` › `commodity1` › `market_year1` › `forecast_month1` › `attribute1` → `cell_value1` (80)<br>matrix2: `region2` › `market_year2` › `forecast_month2` › `attribute2` → `cell_value2` (60) | 140 |
| `sr10`, 10 | World and U.S. Supply and Use for Oilseeds  1/ | matrix1: `commodity_header1` › `commodity1` › `market_year1` › `forecast_month1` › `attribute1` → `cell_value1` (60)<br>matrix2: `commodity_header2` › `commodity2` › `market_year2` › `forecast_month2` › `attribute2` → `cell_value2` (60)<br>matrix3: `commodity_header3` › `commodity3` › `market_year3` › `forecast_month3` › `attribute3` → `cell_value3` (60) | 180 |
| `sr11`, 11 | U.S. Wheat Supply and Use  1/<br>U.S. Wheat by Class: Supply and Use | matrix1: `attribute1` › `market_year1` › `forecast_month1` → `cell_value1` (60)<br>matrix2: `market_year2` › `attribute2` › `forecast_month2` › `attribute_group2` › `m2_unit_descr1` → `cell_value2` (138) | 198 |
| `sr12`, 12 | U.S. Feed Grain and Corn Supply and Use  1/ | matrix1: `attribute1` › `market_year1` › `forecast_month1` → `cell_value1` (52)<br>matrix2: `attribute2` › `market_year2` › `forecast_month2` → `cell_value2` (60) | 112 |
| `sr13`, 13 | U.S. Sorghum, Barley, and Oats Supply and Use  1/ | matrix1: `attribute1` › `market_year1` › `forecast_month1` › `Textbox2` → `cell_value1` (56)<br>matrix2: `attribute2` › `market_year2` › `forecast_month2` → `cell_value2` (56)<br>matrix3: `attribute3` › `market_year3` › `forecast_month3` → `cell_value3` (56) | 168 |
| `sr14`, 14 | U.S. Rice Supply and Use  1/ | matrix1: `attribute4` › `market_year4` › `forecast_month4` → `cell_value4` (60)<br>matrix2: `attribute5` › `market_year5` › `forecast_month5` → `cell_value5` (40)<br>matrix3: `attribute6` › `market_year6` › `forecast_month6` → `cell_value6` (48) | 148 |
| `sr15`, 15 | U.S. Soybeans and Products Supply and Use (Domestic Measure)  1/ | matrix1: `attribute4` › `market_year4` › `forecast_month4` → `cell_value4` (56)<br>matrix2: `attribute5` › `market_year5` › `forecast_month5` → `cell_value5` (44)<br>matrix3: `attribute6` › `market_year6` › `forecast_month6` → `cell_value6` (36) | 136 |
| `sr16`, 16 | U.S. Sugar Supply and Use  1/<br>Mexico Sugar Supply and Use and High Fructose Corn Syrup Consumption 1/ | matrix1: `attribute4` › `market_year4` › `forecast_month4` → `cell_value4` (88)<br>matrix2: `market_year2` › `wb_forecast_month_desc` › `attr_desc` › `m2_Unit_Description1` → `wb_value` (24) | 112 |
| `sr17`, 17 | U.S. Cotton Supply and Use  1/ | matrix1: `attribute4` › `market_year4` › `forecast_month4` → `cell_value4` (52) | 52 |
| `sr18`, 18 | World Wheat Supply and Use  1/ | matrix1: `region_header1` › `region1` › `attribute1` → `cell_value1` (161)<br>matrix2: `region_header2` › `region2` › `attribute2` → `cell_value2` (161) | 322 |
| `sr19`, 19 | World Wheat Supply and Use  1/  (Cont'd.) | matrix1: `region_header1` › `region1` › `forecast_month1` › `attribute1` → `cell_value1` (322) | 322 |
| `sr20`, 20 | World Coarse Grain Supply and Use  1/ | matrix1: `region_header1` › `region1` › `attribute1` → `cell_value1` (140)<br>matrix2: `region_header2` › `region2` › `attribute2` → `cell_value2` (140) | 280 |
| `sr21`, 21 | World Coarse Grain Supply and Use  1/  (Cont'd.) | matrix1: `region_header1` › `region1` › `forecast_month1` › `attribute1` → `cell_value1` (280) | 280 |
| `sr22`, 22 | World Corn Supply and Use  1/ | matrix1: `region_header1` › `region1` › `attribute1` → `cell_value1` (133)<br>matrix2: `region_header2` › `region2` › `attribute2` → `cell_value2` (133) | 266 |
| `sr23`, 23 | World Corn Supply and Use  1/  (Cont'd.) | matrix1: `region_header1` › `region1` › `forecast_month1` › `attribute1` → `cell_value1` (266) | 266 |
| `sr24`, 24 | World Rice Supply and Use  (Milled Basis)  1/ | matrix1: `region_header1` › `region1` › `attribute1` → `cell_value1` (138)<br>matrix2: `region_header2` › `region2` › `attribute2` → `cell_value2` (138) | 276 |
| `sr25`, 25 | World Rice Supply and Use  (Milled Basis)  1/  (Cont'd.) | matrix1: `region_header1` › `region1` › `forecast_month1` › `attribute1` → `cell_value1` (276) | 276 |
| `sr26`, 26 | World Cotton Supply and Use  1/ | matrix3: `region_header3` › `region3` › `attribute3` → `cell_value3` (147)<br>matrix4: `region_header4` › `region4` › `attribute4` → `cell_value4` (147) | 294 |
| `sr27`, 27 | World Cotton Supply and Use  1/ | matrix2: `region_header2` › `region2` › `forecast_month2` › `attribute2` → `cell_value2` (294) | 294 |
| `sr28`, 28 | World Soybean Supply and Use  1/ | matrix4: `region_header4` › `region4` › `attribute4` → `cell_value4` (91)<br>matrix5: `region_header5` › `region5` › `attribute5` → `cell_value5` (91)<br>matrix3: `region_header2` › `region2` › `forecast_month2` › `attribute2` → `cell_value2` (182) | 364 |
| `sr29`, 29 | World Soybean Meal Supply and Use  1/ | matrix4: `region_header4` › `region4` › `attribute4` → `cell_value4` (78)<br>matrix5: `region_header5` › `region5` › `attribute5` → `cell_value5` (78)<br>matrix6: `region_header6` › `region6` › `forecast_month2` › `attribute6` → `cell_value6` (156) | 312 |
| `sr30`, 30 | World Soybean Oil Supply and Use  1/ | matrix4: `region_header4` › `region4` › `attribute4` → `cell_value4` (72)<br>matrix5: `region_header5` › `region5` › `attribute5` → `cell_value5` (72)<br>matrix6: `region_header6` › `region6` › `forecast_month2` › `attribute6` → `cell_value6` (144) | 288 |
| `sr31`, 31 | U.S. Quarterly Animal Product Production  1/<br>U.S. Quarterly Prices for Animal Products | matrix1: `m1_market_year1` › `m1_forecast_month1` › `m1_commodity1` › `m1_unit_description1` → `m1_cell_value1` (117)<br>matrix2: `m2_market_year1` › `m2_forecast_month1` › `m2_commodity1` › `m2_unit_description1` → `m2_cell_value1` (78) | 195 |
| `sr32`, 32 | U.S. Meats Supply and Use | matrix1: `m1_commodity1` › `m1_market_year1` › `m1_forecast_month1` › `m1_attribute1` › `m1_unit_description1` → `m1_cell_value1` (280) | 280 |
| `sr33`, 33 | U.S. Egg Supply and Use<br>U.S. Milk Supply and Use | matrix1: `attribute4` › `market_year4` › `forecast_month4` → `cell_value4` (54)<br>matrix2: `attribute5` › `market_year5` › `forecast_month5` → `cell_value5` (96) | 150 |
| `sr34`, 34 | U.S. Dairy Prices | matrix1: `attribute5` › `market_year5` › `forecast_month5` → `cell_value5` (42) | 42 |
| `sr35`, 35 | Reliability of October Projections 1/ | table1: rows `region_group`, 7 values each (36 rows) | 36 rows |
| `sr36`, 36 | Reliability of October Projections  (Continued) 1/ | table1: rows `region_group`, 7 values each (24 rows) | 24 rows |
| `sr37`, 37 | Reliability of United States October Projections  1/ | table1: rows `attribute_group` (24); table2: `commodity_group2` (4); table3: `commodity_group3` (1); table4: `commodity_group4` (1); 7 values each | 30 rows |

The world pages run in pairs, the historical and estimated years on the first page and
the projected year, by forecast month, on the second (`(Cont'd.)` in the title on pages
19, 21, 23 and 25; page 27 repeats page 26's title); soybeans, soybean meal and soybean
oil hold all three years on one page each (28 to 30).

## XLS

The workbook has 31 sheets: `WASDE Text`, then `Page 8` to `Page 37`, one per printed
table page, named after it. Strings are stored as UTF-16 (codepage 1200 in the file).

`WASDE Text` is one column of 26 rows: row 0 is `WASDE - 676` followed by a carriage
return, row 1 is empty, and rows 2 to 25 are the report's narrative, one paragraph a
row, as the PDF prints it on pages 1 to 5 (`WHEAT: The outlook for 2026/27 U.S. wheat …`
to the cotton paragraphs).

A page sheet starts with the report month (`October 2026`), the page title
(` WASDE - 676 - 11`) and the table title (`U.S. Wheat Supply and Use  1/`), one row each
with an empty row between them: rows 0, 2 and 4, except on `Page 9`, where they are rows
1, 3 and 5. A subtitle row follows where the page prints one. Then each table is laid
out as the page prints it, which differs from sheet to sheet:

- row labels (commodity, region, attribute, market year, forecast month) in the first
  columns, column labels (attributes, market years, forecast months, classes) in header
  rows; a line break inside a label is a line feed here (`Total\nSupply`), where the XML
  has CR LF;
- values as numbers (floating point: `855.0`, `2858.26`), except the printed marks, which
  are text as in the XML (`10.45 *`, `3/`);
- a unit as text on a row of its own, in a value column, before the rows it governs
  (`Million Acres` in column 9 of row 10 on `Page 11`);
- `filler` as text where the XML has a filler cell (a blank line between groups on
  `Page 8`);
- the footnotes in the last row, in column 0.

Value columns are not contiguous on some sheets: `Page 11` has 13 columns, its first
table's values in columns 4, 6, 9 and 11. Rows × columns and the columns that hold
numbers (counted from 0):

| Sheet | Rows × columns | Columns with numbers |
| --- | --- | --- |
| Page 8 | 63 × 8 | 3, 4, 5, 6, 7 |
| Page 9 | 64 × 8 | 3, 4, 5, 6, 7 |
| Page 10 | 70 × 8 | 3, 4, 5, 6, 7 |
| Page 11 | 58 × 13 | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| Page 12 | 51 × 5 | 1, 2, 3, 4 |
| Page 13 | 66 × 5 | 1, 2, 3, 4 |
| Page 14 | 65 × 5 | 1, 2, 3, 4 |
| Page 15 | 60 × 5 | 1, 2, 3, 4 |
| Page 16 | 50 × 12 | 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| Page 17 | 29 × 5 | 1, 2, 3, 4 |
| Page 18 | 61 × 8 | 1, 2, 3, 4, 5, 6, 7 |
| Page 19 | 58 × 9 | 2, 3, 4, 5, 6, 7, 8 |
| Page 20 | 57 × 8 | 1, 2, 3, 4, 5, 6, 7 |
| Page 21 | 52 × 9 | 2, 3, 4, 5, 6, 7, 8 |
| Page 22 | 57 × 8 | 1, 2, 3, 4, 5, 6, 7 |
| Page 23 | 51 × 9 | 2, 3, 4, 5, 6, 7, 8 |
| Page 24 | 63 × 7 | 1, 2, 3, 4, 5, 6 |
| Page 25 | 59 × 8 | 2, 3, 4, 5, 6, 7 |
| Page 26 | 57 × 8 | 1, 2, 3, 4, 5, 6, 7 |
| Page 27 | 56 × 9 | 2, 3, 4, 5, 6, 7, 8 |
| Page 28 | 70 × 9 | 2, 3, 4, 5, 6, 7, 8 |
| Page 29 | 70 × 8 | 2, 3, 4, 5, 6, 7 |
| Page 30 | 64 × 8 | 2, 3, 4, 5, 6, 7 |
| Page 31 | 55 × 16 | 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 |
| Page 32 | 53 × 11 | 1, 3, 4, 5, 6, 7, 8, 9, 10 |
| Page 33 | 48 × 7 | 1, 2, 3, 4, 5, 6 |
| Page 34 | 22 × 7 | 1, 2, 3, 4, 5, 6 |
| Page 35 | 62 × 8 | 1, 2, 3, 4, 5, 6, 7 |
| Page 36 | 44 × 8 | 1, 2, 3, 4, 5, 6, 7 |
| Page 37 | 50 × 8 | 1, 2, 3, 4, 5, 6, 7 |

## TXT

1824 lines, CRLF, ASCII only, no form feeds, no line longer than 80 characters; six tab
characters stand in the column headings of the reliability pages. It holds
the table pages 8 to 37 in order and no narrative. Each page starts with a header line,
the page title centred and the report month at the right
(`                                WASDE - 676 - 8                     October 2026`),
then the table title and subtitle centred, the column headings between two rules of 80
`=`, and the rows: labels at the left, values right-aligned in fixed columns as printed
(`824.20`); a market year or commodity that heads several rows stands on a line of its
own (`    2026/27 (Proj.)`, then `Sep` and `Oct` rows).

## PDF

40 pages, made with Acrobat PDFMaker 26 for Word (`Creator`), produced by Adobe PDF
Library 26.2.171. Page 1 carries the ISSN 1554-9089 and the narrative runs to page 5;
page 6 lists the Interagency Commodity Estimates Committees, page 7 is the table of
contents, pages 8 to 37 are the tables the XML, XLS and TXT carry (35 to 37 the
reliability tables), page 38 lists related USDA reports, page 39 has no text a text
extractor reads, and page 40 is the back cover with links. Every page but 39 has a text
layer.

## The releases ESMIS lists

703 releases, the first on 1973-09-17 and the last on 2026-10-09. Every
`release_datetime` reads `T12:00:00Z`, while WAOB states the release time as noon
Eastern (on 2026-10-28, `pages/wasde-faqs.md`: "released at 12:00 noon Eastern time";
`pages/wasde-report.md`: "12:00pm ET"). Releases per year, and the releases that carry at
least one file of each kind:

| Year | Releases | PDF | TXT | XLS | XLSX | XML | ZIP | DOC | ASC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1973 | 6 | 6 |  |  |  |  |  |  |  |
| 1974 | 16 | 16 |  |  |  |  |  |  |  |
| 1975 | 13 | 13 |  |  |  |  |  |  |  |
| 1976 | 14 | 14 |  |  |  |  |  |  |  |
| 1977 | 16 | 16 |  |  |  |  |  |  |  |
| 1978 | 14 | 14 |  |  |  |  |  |  |  |
| 1979 | 15 | 15 |  |  |  |  |  |  |  |
| 1980 | 16 | 16 |  |  |  |  |  |  |  |
| 1981 | 16 | 16 |  |  |  |  |  |  |  |
| 1982 | 16 | 16 |  |  |  |  |  |  |  |
| 1983 | 17 | 17 |  |  |  |  |  |  |  |
| 1984 | 17 | 17 |  |  |  |  |  |  |  |
| 1985 | 12 | 12 |  |  |  |  |  |  |  |
| 1986 | 12 | 12 |  |  |  |  |  |  |  |
| 1987 | 13 | 13 |  |  |  |  |  |  |  |
| 1988 | 12 | 12 |  |  |  |  |  |  |  |
| 1989 | 12 | 12 |  |  |  |  |  |  |  |
| 1990 | 12 | 12 |  |  |  |  |  |  |  |
| 1991 | 12 | 12 |  |  |  |  |  |  |  |
| 1992 | 12 | 12 |  |  |  |  |  |  |  |
| 1993 | 12 | 12 |  |  |  |  |  |  |  |
| 1994 | 12 | 12 |  |  |  |  |  |  |  |
| 1995 | 23 |  | 23 |  |  |  | 1 |  |  |
| 1996 | 15 |  | 15 |  |  |  |  |  |  |
| 1997 | 12 |  | 12 |  |  |  |  |  |  |
| 1998 | 12 | 11 | 12 |  |  |  |  |  |  |
| 1999 | 12 | 12 | 12 |  |  |  |  |  |  |
| 2000 | 12 | 12 | 12 |  |  |  |  |  |  |
| 2001 | 14 | 13 | 13 | 2 |  |  |  |  |  |
| 2002 | 12 | 12 | 12 | 2 |  |  |  |  |  |
| 2003 | 12 | 12 | 12 | 1 |  |  |  |  |  |
| 2004 | 12 | 12 | 12 | 1 |  |  |  |  |  |
| 2005 | 12 | 12 | 12 |  |  |  |  |  |  |
| 2006 | 12 | 12 | 12 |  |  |  |  | 2 |  |
| 2007 | 12 | 12 | 12 |  |  |  |  |  |  |
| 2008 | 17 | 15 | 15 | 1 |  |  |  | 1 |  |
| 2009 | 13 | 12 | 13 |  |  |  |  |  |  |
| 2010 | 13 | 12 | 10 | 6 | 1 | 6 |  |  |  |
| 2011 | 12 | 12 |  | 12 |  | 12 |  |  |  |
| 2012 | 12 | 12 |  | 12 |  | 12 |  |  |  |
| 2013 | 11 | 11 |  | 11 |  | 11 |  |  |  |
| 2014 | 13 | 12 |  | 12 |  | 12 |  |  | 1 |
| 2015 | 12 | 12 |  | 12 |  | 12 |  |  |  |
| 2016 | 12 | 12 | 3 | 12 |  | 12 |  |  |  |
| 2017 | 12 | 12 | 12 | 12 |  | 12 |  |  |  |
| 2018 | 13 | 13 | 13 | 13 |  | 13 |  |  |  |
| 2019 | 13 | 13 | 13 | 13 |  | 13 |  |  |  |
| 2020 | 12 | 12 | 12 | 12 |  | 12 |  |  |  |
| 2021 | 12 | 12 | 12 | 12 |  | 12 |  |  |  |
| 2022 | 12 | 12 | 12 | 12 |  | 12 |  |  |  |
| 2023 | 12 | 12 | 12 | 12 |  | 12 |  |  |  |
| 2024 | 12 | 12 | 12 | 12 |  | 12 |  |  |  |
| 2025 | 11 | 11 | 11 | 11 |  | 11 |  |  |  |
| 2026 | 10 | 10 | 10 | 10 |  | 10 |  |  |  |

The first XML is that of 2010-07-09, and every release since 2011 carries an XML and an
XLS but one, 2014-01-23, which carries an ASC file only. The XLS files of 2001 to 2008
are revision files (below), not the report's tables. TXT is missing from 2011 to 2015
and from the first nine releases of 2016 (it is back from 2016-10-12). The one XLSX is
that of 2010-08-12, the one ZIP (`95501.zip`, with a `readme.txt`) that of 1995-01-31,
the three DOC files belong to 2006-05-12 and 2006-07-12 (revision notes) and
2008-07-02, and the one ASC is `wasde-01-23-2014.asc`.

Counting every calendar month from the first release (September 1973) to the last
(October 2026), eight months have no release in the catalog: 1974-02, 1975-02, 1975-05,
1976-02, 1977-02, 2013-10, 2019-01 and 2025-10. Page 36's footnote names two of them,
October 2013 and October 2025, as months without a WASDE, due to a partial government
shutdown.

### File names

| Form | Releases |
| --- | --- |
| `wasde-<mm>-<dd>-<yyyy>.<ext>` | 1973-09-17 to 2018-09-12 |
| `WASDE-582-October-11-2018.<ext>` | 2018-10-11 |
| `latest.<ext>` | 2018-11-08 to 2021-07-12 except 2019-05-10, and the PDF and TXT of 2024-11-08 |
| `wasde<mm><yy>.<ext>` | 2019-05-10, then 2021-08-12 to 2026-10-09 except the revised months below; on 2024-11-08 the XML and the XLS only |
| `wasde<mm><yy>v2.<ext>` | the revised months 2024-12-10, 2025-04-10, 2025-05-12, 2026-05-12, 2026-06-11 |

WAOB's notice of 2018 (`New_WASDE_Filename_Format.pdf`) announces the `WASDEmmyy` names
on its own website from the August 10, 2018 report on, beside the `latest.*` names,
which were to continue through the April 2019 release only. ESMIS's catalog uses the
`wasde<mm><yy>` names once, on 2019-05-10, and from 2021-08-12 on, and the `latest.*`
names until 2021-07-12, and once more for the PDF and the TXT of 2024-11-08. Other names
occur once or a few times: revision files of 2001 to 2008
(`wasde-05-10-2001_wheat-revision.pdf`, `wasde-05-10-2002_EUgrains_revision.xls`,
`wasde-05-09-2008_Historical_Dairy_revisions.xls`, …), announcements and special reports
of 2001 and 2008, cotton TXT files of January to April 1996
(`wasde-01-16-1996_cotton.txt`), the original and the revision of July 2013
(`ORIGwasde-07-11-2013.pdf`, `R1wasde-07-11-2013.pdf`) and the original of August 2013
(`ORIGwasde-08-12-2013.xml`), and `Pages_from_wasde-06-22-1984-2.pdf`.

### Revisions and several releases in a month

A revised month is one release whose files carry the `v2` suffix only: release 795937
(2026-06-11) lists `wasde0626v2.pdf`, `wasde0626v2.txt`, `wasde0626v2.xls` and
`wasde0626v2.xml`, and the catalog lists no file of the original. Most months have one
release; months with more are frequent until 1996, and later 2001-05, 2001-09, 2008-05,
2008-07, 2008-10, 2008-12, 2009-09, 2010-12, 2014-01, 2018-12 (2018-12-11 and
2018-12-14) and 2019-11 (three releases on 2019-11-08, each with `latest.*` files).
