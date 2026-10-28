# Sample files

A sample of each file kind the parsers read, `<file_kind>/<case>.<ext>`: a small real
file, or the first rows of one as conventions §10 allows, never typed in by hand
(ADR-0020). A binary file carries no comment, so each sample's provenance is one row
here: the release id, the URL, the bytes and sha256 of the full file as upstream serves
it, and the UTC time it was fetched, with `Z`.

Every sample is written by `scripts/cut_sample.py` from one download of the file through
xippios-usda-esmis, which prints its row below; Kept says what of the file it holds.

- `wasde_xml/` holds verbatim cuts of the October 2026 release's XML: the file's leading
  bytes up to and including the root's opening tag, the pages kept (`<srNN>` to
  `</srNN>`, each with the line break and indent before it), the root's closing tag, all
  as the file has them; a sample is named after the pages it keeps. Each parses to the
  same records as those pages of the whole file.
- `wasde_xls/` holds the October 2026 release's XLS cut to two sheets, `WASDE Text` (the
  narrative) and `Page 8` (whose first cell prints the report month): a binary workbook
  cannot be cut by bytes, so the script copies every cell that holds a value, at its row
  and column, with its type and value as xlrd reads them, into a workbook written with
  xlwt, and reads the copy back to compare it with the original, cell for cell. No
  formatting is kept, and a text cell holding no character is left empty, as xlwt writes
  it.
- `wasde_pdf/` holds the July 2010 release's PDF whole (release 95659, the first with an
  XML file), the PDF sample under 256 KiB whose download fixture stays under the cap as
  well (base64 adds a third).

The download's replay fixtures under `../download_release_file/` are the recorded GET
exchanges of the files: `wasde1026_xml.json` carries `wasde_xml/sr08_sr35_sr36.xml` as its
body, `wasde1026_xml_sr11_sr24.json` `wasde_xml/sr11_sr24.xml` and `wasde1026_xls.json`
`wasde_xls/wasde_text_page_8.xls` (base64), each marked `truncated` with the whole file's
bytes and sha256; `wasde-07-09-2010_pdf.json` carries the whole PDF (base64), unmarked.

| File | Release | URL | Bytes | sha256 | Kept | Fetched |
| --- | --- | --- | --- | --- | --- | --- |
| `wasde_xml/sr08_sr35_sr36.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr08, sr35, sr36 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr09_sr16.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr09, sr16 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr11_sr24.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr11, sr24 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr12_sr37.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr12, sr37 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr13_sr34.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr13, sr34 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr31_sr32.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr31, sr32 | 2026-10-28T15:06:18Z |
| `wasde_xls/wasde_text_page_8.xls` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xls | 354304 | 5beb5732b587807d10a12fddf58c1c1120a08891bef4f361a346ab68a7906025 | sheets WASDE Text, Page 8, copied cell by cell (values and types, no formatting) into a workbook written with xlwt | 2026-10-28T19:30:54Z |
| `wasde_pdf/wasde-07-09-2010.pdf` | 95659 | https://esmis.nal.usda.gov/sites/default/release-files/3t945q76s/3n203z415/8c97kq758/wasde-07-09-2010.pdf | 152211 | 8a4f13b3cd90e2ba92ddf368d6966691f9bcde94ae6705282f2cdac6161ce18e | the whole file | 2026-10-28T19:29:27Z |
