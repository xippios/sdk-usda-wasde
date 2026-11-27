"""``scripts/probe_releases.py`` offline: its count of requests and its reading of kept files.

The script reads older and revised WASDE files once
(https://github.com/xippios/sdk-usda-wasde/issues/18); these tests send nothing.
"""

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_releases.py"
SAMPLE = ROOT / "tests" / "fixtures" / "files" / "wasde_xml" / "sr14.xml"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("probe_releases", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_releases"] = module
    spec.loader.exec_module(module)
    return module


def test_a_run_sends_sixteen_requests() -> None:
    """Eight files, the release and the file each, the count the maintainer gave."""
    probe = load_script()
    assert len(probe.PROBES) == 8
    assert probe.REQUESTS == 16


def test_kept_files_are_read_again_without_a_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], respx_mock: respx.MockRouter
) -> None:
    """Each kept file, the XML sample under a probe's name or the bytes ``not a workbook``,
    is an input of the test, not an answer from ESMIS.
    """
    probe = load_script()
    for item in probe.PROBES:
        if item.format == "xml":
            shutil.copyfile(SAMPLE, tmp_path / probe._file(item))
        else:
            (tmp_path / probe._file(item)).write_bytes(b"not a workbook")
    assert probe.main(["--from", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 8
    assert lines[0].startswith("2010-07 95659 xml (the first XML): 148 records")
    assert "refused: ValidationError: wasde.xls: not a workbook xlrd reads" in lines[1]
    assert respx_mock.calls.call_count == 0
