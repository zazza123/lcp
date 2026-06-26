"""`lcp --version` must report the installed package version, not a hardcode."""

import importlib.metadata
import subprocess
import sys


def test_version_reports_installed_package_version():
    expected = importlib.metadata.version("lcp")
    out = subprocess.run(
        [sys.executable, "-m", "lcp", "--version"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert expected in out.stdout, f"expected {expected!r} in {out.stdout!r}"
