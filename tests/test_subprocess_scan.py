"""Tests for Phase 5 subprocess scanning: lcp.scanjson + lcp.subprocess_scan.

The scan child speaks the public LCP document format on stdout; errors are a
single JSON object on stderr plus a distinguishing exit code (0 ok /
3 import failure / 4 scan failure).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent


def _last_stderr_json(stderr: str) -> dict:
    """Parse the contract's JSON object from stderr (skipping any noise)."""
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON object on stderr: {stderr!r}")


class TestScanJsonEntryPoint:
    """python -m lcp.scanjson — the machine-mode scan contract."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        # cwd=tests/ puts the fixtures on the child's sys.path (sys.path[0]).
        return subprocess.run(
            [sys.executable, "-m", "lcp.scanjson", *args],
            capture_output=True,
            text=True,
            cwd=TESTS_DIR,
            timeout=120,
        )

    def test_happy_path_writes_lcp_document_to_stdout(self):
        proc = self._run("sample_package")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert doc["manifest"]["library"]["name"] == "sample_package"
        assert doc["symbols"]

    def test_import_failure_exits_3_with_stderr_json(self):
        proc = self._run("definitely_not_installed_xyz")
        assert proc.returncode == 3
        err = _last_stderr_json(proc.stderr)
        assert err["type"] == "import_failure"
        assert "definitely_not_installed_xyz" in err["message"]
        assert proc.stdout == ""

    def test_systemexit_during_import_exits_4(self):
        proc = self._run("crashing_module")
        assert proc.returncode == 4
        err = _last_stderr_json(proc.stderr)
        assert err["type"] == "scan_failure"
        assert "SystemExit" in err["message"]
        assert proc.stdout == ""

    def test_import_time_stdout_noise_does_not_corrupt_protocol(self):
        proc = self._run("printing_module")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)  # fails if noise leaked onto stdout
        assert "printing_module:documented" in doc["symbols"]
        assert "import-time noise" in proc.stderr


import time
import venv

import pytest

from lcp.subprocess_scan import (
    DEFAULT_SCAN_TIMEOUT,
    ScanFailedError,
    ScanImportError,
    ScanInterpreterNotFoundError,
    ScanSpawnError,
    ScanTimeoutError,
    scan_package_subprocess,
)


class TestScanPackageSubprocess:
    """Server-side runner: spawn, parse, classify failures."""

    def test_happy_path_returns_document(self):
        doc = scan_package_subprocess(
            "sample_package", extra_paths=[str(TESTS_DIR)]
        )
        assert doc.manifest.library.name == "sample_package"
        assert len(doc.symbols) > 0

    def test_import_failure_raises_scan_import_error(self):
        with pytest.raises(ScanImportError, match="definitely_not_installed_xyz"):
            scan_package_subprocess("definitely_not_installed_xyz")

    def test_crashing_package_raises_scan_failed_error(self):
        with pytest.raises(ScanFailedError, match="SystemExit"):
            scan_package_subprocess(
                "crashing_module", extra_paths=[str(TESTS_DIR)]
            )

    def test_timeout_kills_the_scan(self, monkeypatch):
        monkeypatch.setenv("LCP_TEST_IMPORT_SLEEP", "30")
        start = time.monotonic()
        with pytest.raises(ScanTimeoutError, match="timed out"):
            scan_package_subprocess(
                "slow_import_module",
                extra_paths=[str(TESTS_DIR)],
                timeout=1.0,
            )
        assert time.monotonic() - start < 10  # killed, not waited out

    def test_interpreter_not_found(self):
        with pytest.raises(
            ScanInterpreterNotFoundError, match="/nonexistent/python"
        ):
            scan_package_subprocess("json", python="/nonexistent/python")

    def test_spawn_oserror_raises_scan_spawn_error(self, monkeypatch):
        def blocked(*args, **kwargs):
            raise PermissionError("spawn blocked")

        monkeypatch.setattr("lcp.subprocess_scan.subprocess.run", blocked)
        with pytest.raises(ScanSpawnError, match="spawn blocked"):
            scan_package_subprocess("json")

    def test_default_timeout_is_60s(self):
        assert DEFAULT_SCAN_TIMEOUT == 60.0


@pytest.fixture(scope="module")
def second_venv(tmp_path_factory) -> Path:
    """A pip-less venv whose site-packages holds a package this process cannot see."""
    root = tmp_path_factory.mktemp("second-venv")
    venv.create(root, with_pip=False)
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    vpy = root / bin_dir / ("python.exe" if sys.platform == "win32" else "python")
    purelib = subprocess.run(
        [str(vpy), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (Path(purelib) / "secondvenv_only_pkg.py").write_text(
        '"""A package that exists only in the second venv."""\n'
        "\n"
        "def greet(name: str) -> str:\n"
        '    """Return a greeting for name."""\n'
        '    return f"hello {name}"\n',
        encoding="utf-8",
    )
    return vpy


class TestCrossEnvironmentScan:
    """Exit criterion: a package installed only in a second venv resolves."""

    def test_package_is_invisible_to_the_server_env(self):
        import importlib.util

        assert importlib.util.find_spec("secondvenv_only_pkg") is None

    def test_scan_resolves_package_from_second_venv(self, second_venv):
        doc = scan_package_subprocess(
            "secondvenv_only_pkg", python=str(second_venv)
        )
        assert "secondvenv_only_pkg:greet" in doc.symbols
