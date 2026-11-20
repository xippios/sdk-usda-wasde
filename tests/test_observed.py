"""``docs/upstream/OBSERVED.md`` as committed: what WASDE's files hold that no page documents.

sdk-core's conventions §3 keep these notes in one file written by hand, which
``FETCHED.md`` lists in a row of its own, and give each its evidence: a file layout names
the release files it was written from, with their URLs, bytes and sha256, and each note
the date and the file or sample it was observed in. A note here is a ``###`` section,
and its last paragraph, ``Observed:``, names them: a file of the release by its name, as
the table ``What it was written from`` lists it, a sample or a recording by its path
under ``tests/fixtures/``, a file of the snapshot by its path under ``docs/upstream/``.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "docs" / "upstream"
OBSERVED = UPSTREAM / "OBSERVED.md"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
CITED = re.compile(r"`([\w./-]+(?:\.(?:json|md|pdf|xls|xml|txt)|/))`")
SOURCE = re.compile(
    r"^\| (?P<name>\S+) \| (?P<url>https://esmis\.nal\.usda\.gov/\S+/(?P=name)) "
    r"\| (?P<bytes>\d+) \| (?P<sha256>[0-9a-f]{64}) \|$",
    re.MULTILINE,
)


def text() -> str:
    return OBSERVED.read_text(encoding="utf-8")


def sections() -> list[tuple[str, str, str]]:
    """Each ``##`` and ``###`` section: its level, its heading and its text."""
    parts = re.split(r"^(##|###) (.+)$", text(), flags=re.MULTILINE)
    return list(zip(parts[1::3], parts[2::3], parts[3::3], strict=True))


def notes() -> dict[str, list[str]]:
    """Each note's heading and its paragraphs, each paragraph's lines joined by a space.

    A ``##`` heading groups notes and is none itself.
    """
    return {
        heading: [" ".join(block.split()) for block in body.split("\n\n") if block.strip()]
        for level, heading, body in sections()
        if level == "###"
    }


def written_from() -> dict[str, str]:
    """The release files of the table ``What it was written from``, each name its URL."""
    (body,) = [body for _, heading, body in sections() if heading == "What it was written from"]
    return {match["name"]: match["url"] for match in SOURCE.finditer(body)}


def test_the_notes_are_observed_md_and_no_layout_md_remains() -> None:
    assert OBSERVED.is_file()
    assert not (UPSTREAM / "layout.md").exists()


def test_fetched_md_lists_observed_md_in_a_row_of_its_own() -> None:
    rows = (UPSTREAM / "FETCHED.md").read_text(encoding="utf-8").splitlines()
    assert f"| OBSERVED.md | - | - | - | - | - | - | - | {HAND} |" in rows


def test_the_layouts_name_the_release_files_they_were_written_from() -> None:
    """The four files of release 796099, each with its URL, bytes and sha256."""
    files = written_from()
    assert sorted(files) == [f"wasde1026.{kind}" for kind in ("pdf", "txt", "xls", "xml")]
    assert all("/release-files/796099/" in url for url in files.values())


def test_every_note_ends_with_what_it_was_observed_in_and_its_date() -> None:
    found = notes()
    assert found
    for heading, paragraphs in found.items():
        observed = paragraphs[-1]
        assert observed.startswith("Observed: "), heading
        assert DATE.search(observed), heading
        assert CITED.search(observed), heading


def test_every_file_a_note_was_observed_in_exists() -> None:
    """A release file is a row of the table above; a sample, recording or page is here."""
    release = written_from()
    missing = []
    for heading, paragraphs in notes().items():
        for cited in CITED.findall(paragraphs[-1]):
            if cited in release:
                continue
            path = ROOT / cited if cited.startswith("tests/") else UPSTREAM / cited
            if not path.exists():
                missing.append(f"{heading}: {cited}")
    assert missing == []
