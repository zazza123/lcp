"""Tests for the corpus diff tools under tools/corpus/.

The tools are standalone scripts, not part of the lcp package, so they are
loaded by path rather than imported.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools" / "corpus"


def _load(script_name: str):
    """Load a tools/corpus script by path."""
    path = TOOLS / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tiny_corpus(tmp_path):
    """A libraries.txt plus one importable synthetic package."""
    pkg = tmp_path / "site" / "tinylib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(
            '''
            """A tiny library."""

            MAX = 3


            def hello(name: str) -> str:
                """Greet someone."""
                return f"hi {name}"
            '''
        ),
        encoding="utf-8",
    )
    libraries = tmp_path / "libraries.txt"
    libraries.write_text("core\ttinylib\ttinylib\n", encoding="utf-8")
    return {"libraries": libraries, "site": tmp_path / "site"}


class TestSnapshot:
    def test_records_symbols_for_each_library(self, tiny_corpus, tmp_path):
        snapshot = _load("snapshot.py")
        sys.path.insert(0, str(tiny_corpus["site"]))
        try:
            result = snapshot.build_snapshot(
                src=str(REPO_ROOT / "src"),
                libraries_path=tiny_corpus["libraries"],
                tier="core",
            )
        finally:
            sys.path.remove(str(tiny_corpus["site"]))

        symbols = result["libraries"]["tinylib"]["symbols"]
        assert "tinylib:hello" in symbols
        assert symbols["tinylib:hello"]["kind"] == "function"
        assert symbols["tinylib:MAX"]["kind"] == "constant"

    def test_records_an_error_instead_of_aborting(self, tmp_path):
        snapshot = _load("snapshot.py")
        libraries = tmp_path / "libraries.txt"
        libraries.write_text("core\tnope\tdefinitely_not_installed_xyz\n", encoding="utf-8")

        result = snapshot.build_snapshot(
            src=str(REPO_ROOT / "src"), libraries_path=libraries, tier="core"
        )

        entry = result["libraries"]["nope"]
        assert "error" in entry
        assert "symbols" not in entry

    def test_tier_filter_excludes_full_entries(self, tmp_path):
        snapshot = _load("snapshot.py")
        libraries = tmp_path / "libraries.txt"
        libraries.write_text(
            "core\tnope\tdefinitely_not_installed_xyz\n"
            "full\talso_nope\talso_definitely_not_installed_xyz\n",
            encoding="utf-8",
        )

        core = snapshot.build_snapshot(
            src=str(REPO_ROOT / "src"), libraries_path=libraries, tier="core"
        )
        full = snapshot.build_snapshot(
            src=str(REPO_ROOT / "src"), libraries_path=libraries, tier="full"
        )

        assert set(core["libraries"]) == {"nope"}
        assert set(full["libraries"]) == {"nope", "also_nope"}

    def test_provenance_records_the_measured_checkout(self, tiny_corpus):
        snapshot = _load("snapshot.py")
        result = snapshot.build_snapshot(
            src=str(REPO_ROOT / "src"),
            libraries_path=tiny_corpus["libraries"],
            tier="core",
        )

        provenance = result["provenance"]
        assert provenance["tier"] == "core"
        assert provenance["python"].startswith("3.")
        # NOTE: assert against the real SHA, not just a length. _lcp_sha falls
        # back to the literal "unknown", which is itself 7 characters, so a
        # length check would pass even when provenance was never resolved.
        expected = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert provenance["lcp_sha"] == expected
