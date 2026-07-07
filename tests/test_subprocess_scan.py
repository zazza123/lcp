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
