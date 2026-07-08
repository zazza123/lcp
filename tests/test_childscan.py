"""Tests for the isolated child entry point (lcp/_childscan.py).

The module is loaded by file path in production (never imported as
lcp._childscan), so tests load it the same way and hand it the real scanner.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import lcp.scanner as scanner

_CHILDSCAN = Path(scanner.__file__).parent / "_childscan.py"


def _load_childscan():
    spec = importlib.util.spec_from_file_location("_lcp_childscan_test", _CHILDSCAN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestChildScan:
    def test_happy_path_prints_scanned_module_json(self, capsys):
        child = _load_childscan()
        child.main(scanner, ["json"])
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["name"] == "json"
        assert any(s["module_path"].startswith("json") for s in payload["symbols"])

    def test_import_failure_exits_3(self, capsys):
        child = _load_childscan()
        with pytest.raises(SystemExit) as ei:
            child.main(scanner, ["definitely_not_installed_xyz"])
        assert ei.value.code == 3
        err = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
        assert err["type"] == "import_failure"

    def test_no_pydantic_or_lcp_imports(self):
        import ast

        tree = ast.parse(_CHILDSCAN.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "pydantic" not in imported
        assert "lcp" not in imported
