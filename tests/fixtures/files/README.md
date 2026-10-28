# Sample files

A sample of each file kind the parsers read, `<file_kind>/<case>.<ext>`: a small real
file, or the first rows of one as conventions §10 allows, never typed in by hand
(ADR-0020). A binary file carries no comment, so each sample's provenance is one row
here: the release id, the URL, the bytes and sha256 of the full file as upstream serves
it, and the UTC time it was fetched, with `Z`.

`wasde_xml/` holds verbatim cuts of the October 2026 release's XML, written by
`scripts/cut_sample.py` from one download: the file's leading bytes up to and including
the root's opening tag, the pages kept (`<srNN>` to `</srNN>`, each with the line break
and indent before it), the root's closing tag, all as the file has them; a sample is
named after the pages it keeps. Each parses to the same records as those pages of the
whole file. The download's replay fixture,
`../download_release_file/wasde1026_xml.json`, carries `wasde_xml/sr08_sr35_sr36.xml`
as its body, marked `truncated` with the whole file's bytes and sha256.

| File | Release | URL | Bytes | sha256 | Pages kept | Fetched |
| --- | --- | --- | --- | --- | --- | --- |
| `wasde_xml/sr08_sr35_sr36.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr08, sr35, sr36 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr09_sr16.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr09, sr16 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr11_sr24.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr11, sr24 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr12_sr37.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr12, sr37 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr13_sr34.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr13, sr34 | 2026-10-28T15:06:18Z |
| `wasde_xml/sr31_sr32.xml` | 796099 | https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml | 3569419 | 85e67ec8e8ec8eb98462596a4e784c170534630108cd51f4f42037756a9e50b9 | sr31, sr32 | 2026-10-28T15:06:18Z |
