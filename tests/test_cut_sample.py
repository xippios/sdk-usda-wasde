"""``scripts/cut_sample.py``'s download fixture, written offline.

Nothing here sends a request: the script's fixture step takes the response a run
downloaded, here one made in the test, and writes under ``tmp_path``, never under
``tests/fixtures/``. A sample that is not the whole file becomes the body, marked
``sample`` with the whole file's size and sha256, and core's ``write_fixture`` writes it
(sdk-core ADR-0020, amendment 2026-11-18, point a; sdk-core ADR-0042, decision 4).
"""

import base64
import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from xippios.core.testing import fixture_text, load_fixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cut_sample.py"
URL = "https://esmis.nal.usda.gov/sites/default/release-files/796099/wasde1026.xml"
HEAD = b'<?xml version="1.0"?>\n<Report Name="wasde">\n'
WHOLE = HEAD + b"  <sr08></sr08>\n  <sr09></sr09>\n</Report>\n"
CUT = HEAD + b"  <sr08></sr08>\n</Report>\n"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cut_sample", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def downloaded(content: bytes, url: str = URL) -> httpx.Response:
    """The response of a download, as the script's one GET receives it."""
    return httpx.Response(
        200,
        content=content,
        headers={"content-type": "application/xml"},
        request=httpx.Request("GET", url),
    )


def test_a_sample_body_is_marked_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "FIXTURES", tmp_path)
    path = script.write_download_fixture(downloaded(WHOLE), CUT, "wasde1026_xml", binary=False)
    assert path == tmp_path / "download_release_file" / "wasde1026_xml.json"
    fixture = load_fixture(path)
    response = fixture.response
    assert (response.sample, response.truncated) == (True, False)
    assert response.content == CUT
    assert response.original_bytes == len(WHOLE)
    assert response.sha256 == hashlib.sha256(WHOLE).hexdigest()
    assert fixture.request.url == URL
    assert path.read_text(encoding="utf-8") == fixture_text(fixture), "written as core writes"


def test_a_binary_sample_is_stored_base64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "FIXTURES", tmp_path)
    whole, cut = b"\xd0\xcf\x11\xe0 whole workbook", b"\xd0\xcf\x11\xe0 copy"
    path = script.write_download_fixture(downloaded(whole), cut, "wasde1026_xls", binary=True)
    response = load_fixture(path).response
    assert (response.sample, response.body_base64) == (True, True)
    assert response.body == base64.b64encode(cut).decode("ascii")
    assert (response.original_bytes, response.sha256) == (
        len(whole),
        hashlib.sha256(whole).hexdigest(),
    )


def test_the_whole_file_is_the_exchange_as_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "FIXTURES", tmp_path)
    path = script.write_download_fixture(downloaded(WHOLE), WHOLE, "whole", binary=False)
    response = load_fixture(path).response
    assert (response.sample, response.truncated) == (False, False)
    assert (response.original_bytes, response.sha256) == (None, None)
    assert response.content == WHOLE


def test_a_fixture_over_the_cap_is_refused_and_nothing_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "FIXTURES", tmp_path)
    monkeypatch.setattr(script, "CAP", 512)
    with pytest.raises(SystemExit, match="over 256 KiB"):
        script.write_download_fixture(downloaded(WHOLE * 20), WHOLE * 10, "big", binary=False)
    assert list(tmp_path.iterdir()) == []
