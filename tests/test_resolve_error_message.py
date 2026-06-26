"""resolve_library_document must give an actionable, diagnostic error.

The old message conflated "not installed" with "scan failed" and suggested
`pip install <import-path>` (wrong when the import path differs from the
distribution name, e.g. `google.adk` → `google-adk`). The new message
distinguishes the cases and names the interpreter lcp is running under, so
environment mismatches (lcp scanning a different venv than where the package
lives) are obvious.
"""

import sys

import pytest

import lcp.mcp_server as mcp_server
from lcp.mcp_server import resolve_library_document


def test_missing_package_message_names_interpreter(tmp_path):
    with pytest.raises(ImportError) as ei:
        resolve_library_document(
            "definitely_not_a_real_pkg_xyz", cache_dir=tmp_path, no_cache=True
        )
    msg = str(ei.value)
    # Says it's not importable HERE, and names the interpreter (env mismatch hint)
    assert "not importable" in msg.lower()
    assert sys.executable in msg
    # Does NOT suggest the wrong `pip install <import-path>` form
    assert "pip install definitely_not_a_real_pkg_xyz" not in msg


def test_installed_but_scan_fails_message(tmp_path, monkeypatch):
    # Pretend the package IS installed (has a version) but scanning blows up.
    monkeypatch.setattr(mcp_server, "_installed_version", lambda name: "9.9.9")

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom during scan")

    monkeypatch.setattr("lcp.scanner.scan_package", boom)

    with pytest.raises(ImportError) as ei:
        resolve_library_document("somepkg", cache_dir=tmp_path, no_cache=True)
    msg = str(ei.value)
    # Must NOT claim it's not installed; must report the real scan failure + version
    assert "9.9.9" in msg
    assert "scan failed" in msg.lower()
    assert "kaboom during scan" in msg
    assert "not importable" not in msg.lower()
