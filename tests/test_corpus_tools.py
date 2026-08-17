"""Tests for the corpus diff tools under tools/corpus/.

The tools are standalone scripts, not part of the lcp package, so they are
loaded by path rather than imported.
"""

from __future__ import annotations

import importlib.util
import json
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

    def test_records_signature_type_fields(self, tiny_corpus, tmp_path):
        """Type fields are recorded per signature, keyed by field id (#77)."""
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

        types = result["libraries"]["tinylib"]["symbols"]["tinylib:hello"]["types"]
        assert types["sig0.param[name]"] == "str"
        assert types["sig0.returns"] == "str"

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

    def test_unknown_tier_raises(self, tmp_path):
        snapshot = _load("snapshot.py")
        libraries = tmp_path / "libraries.txt"
        libraries.write_text("core\tnope\tdefinitely_not_installed_xyz\n", encoding="utf-8")

        with pytest.raises(ValueError, match="bogus"):
            snapshot.read_libraries(libraries, "bogus")

        with pytest.raises(ValueError, match="bogus"):
            snapshot.build_snapshot(src=str(REPO_ROOT / "src"), libraries_path=libraries, tier="bogus")

    def test_second_call_with_different_src_uses_that_checkout(self, tmp_path):
        """A second build_snapshot() call with a *different* --src must not
        silently keep measuring the first checkout's cached lcp.scanner /
        lcp.generator (sys.path only affects imports that haven't happened
        yet; sys.modules caching would otherwise hide the switch)."""
        snapshot = _load("snapshot.py")

        # Captured before either call, so the assertions below prove the
        # save/evict/restore contract holds even across two calls with two
        # different --src values, not just a single call. Deleting the
        # `finally` block in build_snapshot would leave this suite green
        # without these assertions.
        lcp_before = sys.modules.get("lcp")

        stub_root = tmp_path / "stub_src"
        stub_lcp = stub_root / "lcp"
        stub_lcp.mkdir(parents=True)
        (stub_lcp / "__init__.py").write_text("", encoding="utf-8")
        (stub_lcp / "scanner.py").write_text(
            textwrap.dedent(
                """
                def scan_package(name, **kwargs):
                    return None
                """
            ),
            encoding="utf-8",
        )
        (stub_lcp / "generator.py").write_text(
            textwrap.dedent(
                """
                from types import SimpleNamespace


                def generate_lcp(scanned):
                    symbol = SimpleNamespace(
                        kind=SimpleNamespace(value="function"),
                        module="stublib",
                        semantics=SimpleNamespace(summary="stub sentinel"),
                    )
                    return SimpleNamespace(symbols={"stublib:SENTINEL_65": symbol})
                """
            ),
            encoding="utf-8",
        )

        libraries = tmp_path / "libraries.txt"
        libraries.write_text("core\tstublib\tstublib\n", encoding="utf-8")

        # First call: the real checkout. "stublib" isn't importable through
        # it, so this scan records an error entry -- that's fine, its only
        # purpose is to get the real lcp.scanner/lcp.generator cached in
        # sys.modules the way a real first invocation would.
        snapshot.build_snapshot(
            src=str(REPO_ROOT / "src"), libraries_path=libraries, tier="core"
        )

        # Second call: a different checkout (the stub). If lcp.scanner /
        # lcp.generator stayed cached from the first call, this result would
        # NOT contain the sentinel symbol -- it would instead reflect the
        # real checkout's (error) behavior.
        result = snapshot.build_snapshot(
            src=str(stub_root), libraries_path=libraries, tier="core"
        )

        symbols = result["libraries"]["stublib"]["symbols"]
        assert "stublib:SENTINEL_65" in symbols

        # The save/restore contract: after both calls, sys.modules["lcp"] is
        # back to whatever object it was before this test touched anything,
        # and the second call's inserted --src is off sys.path again.
        assert sys.modules.get("lcp") is lcp_before
        assert str(stub_root.resolve()) not in sys.path

    def test_wrong_src_is_rejected_rather_than_silently_measured(self, tmp_path):
        """If --src does not actually supply the ``lcp`` that ends up
        imported -- e.g. because some other ``lcp`` is already importable in
        this interpreter and wins over the sys.path insertion -- the run
        must fail loudly rather than quietly measure the wrong checkout
        while reporting *src*'s SHA in provenance."""
        snapshot = _load("snapshot.py")

        # This directory does not contain an `lcp` package at all. After
        # eviction, `import lcp` falls through to whatever `lcp` is already
        # importable in this interpreter (the repo's own dev install), which
        # is NOT inside this --src -- exactly the mismatch this check exists
        # to catch.
        empty_src = tmp_path / "empty_src"
        empty_src.mkdir()
        libraries = tmp_path / "libraries.txt"
        libraries.write_text("core\tnope\tdefinitely_not_installed_xyz\n", encoding="utf-8")

        with pytest.raises(RuntimeError, match="empty_src"):
            snapshot.build_snapshot(src=str(empty_src), libraries_path=libraries, tier="core")

        # Even on the error path, the finally block must still restore state.
        assert str(empty_src.resolve()) not in sys.path

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
        status = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if status:
            expected += "-dirty"
        assert provenance["lcp_sha"] == expected

        # lcp_file records exactly what got imported, so a stale snapshot
        # (one whose reported SHA doesn't match what was actually measured)
        # can be audited after the fact.
        assert provenance["lcp_file"] == str((REPO_ROOT / "src" / "lcp" / "__init__.py").resolve())

    def test_dirty_working_tree_is_marked(self, tmp_path):
        """Snapshotting an uncommitted edit must not carry the same SHA as a
        snapshot of the clean commit it's based on."""
        snapshot = _load("snapshot.py")
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "lcp").mkdir()
        (repo / "src" / "lcp" / "__init__.py").write_text("", encoding="utf-8")

        def run(*args):
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        run("init", "-q")
        run("config", "user.email", "test@example.com")
        run("config", "user.name", "test")
        run("add", "-A")
        run("commit", "-q", "-m", "initial")

        clean_sha = snapshot._lcp_sha(str(repo / "src"))
        assert not clean_sha.endswith("-dirty")

        (repo / "src" / "lcp" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
        dirty_sha = snapshot._lcp_sha(str(repo / "src"))
        assert dirty_sha == f"{clean_sha}-dirty"

    def test_scan_one_propagates_keyboard_interrupt(self, monkeypatch):
        """Ctrl-C must stop the run, not be recorded as a per-library error
        and swallowed like every other exception scan_one catches."""
        import lcp.scanner

        snapshot = _load("snapshot.py")

        def _raise_interrupt(name):
            raise KeyboardInterrupt

        monkeypatch.setattr(lcp.scanner, "scan_package", _raise_interrupt)

        with pytest.raises(KeyboardInterrupt):
            snapshot.scan_one("whatever")

    def test_main_returns_zero_and_writes_snapshot(self, tiny_corpus, tmp_path):
        snapshot = _load("snapshot.py")
        output = tmp_path / "out.json"
        sys.path.insert(0, str(tiny_corpus["site"]))
        try:
            rc = snapshot.main(
                [
                    "--src", str(REPO_ROOT / "src"),
                    "-o", str(output),
                    "--tier", "core",
                    "--libraries", str(tiny_corpus["libraries"]),
                ]
            )
        finally:
            sys.path.remove(str(tiny_corpus["site"]))

        assert rc == 0
        assert output.exists()
        assert "tinylib" in output.read_text(encoding="utf-8")


def _snap(libraries, tier="core"):
    """Build a minimal snapshot document for diff tests."""
    return {
        "provenance": {"lcp_sha": "abc1234", "python": "3.12.0",
                       "tier": tier, "versions": {}},
        "libraries": libraries,
    }


def _sym(kind="constant", summary="Box constant.", module="rich", types=None):
    """A recorded symbol. ``types`` defaults to an empty mapping, not to a
    missing key: an absent ``types`` key means the snapshot predates type
    recording, which compare.py treats as "not comparable" rather than as
    zero type changes."""
    return {
        "kind": kind,
        "module": module,
        "summary": summary,
        "types": {} if types is None else types,
    }


class TestCompare:
    def test_reports_removed_symbols(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym(), "rich:B": _sym()}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym()}}})

        diff = compare.diff_snapshots(before, after)

        assert [d["id"] for d in diff["removed"]] == ["rich:B"]
        assert diff["added"] == []

    def test_reports_kind_changes_separately_from_add_and_remove(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym(kind="constant")}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym(kind="function")}}})

        diff = compare.diff_snapshots(before, after)

        assert diff["removed"] == []
        assert diff["added"] == []
        assert diff["kind_changed"] == [
            {"library": "rich", "id": "rich:A", "before": "constant", "after": "function"}
        ]

    def test_groups_additions_by_object_type(self):
        compare = _load("compare.py")
        before = _snap({"numpy": {"symbols": {}}})
        after = _snap({"numpy": {"symbols": {
            "numpy:a": _sym(summary="ufunc constant.", module="numpy"),
            "numpy:b": _sym(summary="ufunc constant.", module="numpy"),
            "numpy:c": _sym(summary="ndarray constant.", module="numpy"),
        }}})

        diff = compare.diff_snapshots(before, after)
        rendered = compare.render(diff)

        assert "ufunc x2" in rendered
        assert "ndarray x1" in rendered

    def test_a_failed_scan_is_not_reported_as_removals(self):
        """A library that crashed must never look like it lost every symbol."""
        compare = _load("compare.py")
        before = _snap({"scipy": {"symbols": {"scipy:A": _sym(), "scipy:B": _sym()}}})
        after = _snap({"scipy": {"error": "ImportError: boom"}})

        diff = compare.diff_snapshots(before, after)

        assert diff["removed"] == []
        assert diff["coverage"] == [{"library": "scipy", "state": "failed_in_after"}]

    def test_a_library_missing_from_one_side_is_a_coverage_difference(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym()}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym()}},
                       "numpy": {"symbols": {"numpy:x": _sym()}}})

        diff = compare.diff_snapshots(before, after)

        assert diff["added"] == []
        assert diff["coverage"] == [{"library": "numpy", "state": "only_in_after"}]

    def test_render_orders_removals_before_additions(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:GONE": _sym()}}})
        after = _snap({"rich": {"symbols": {"rich:NEW": _sym()}}})

        rendered = compare.render(compare.diff_snapshots(before, after))

        assert rendered.index("REMOVED") < rendered.index("ADDED")

    # -- FIX 1: the diff must not be blind to `module` and `summary` -------

    def test_detects_summary_change_without_touching_other_sections(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym(summary="Box constant.")}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym(summary="A styled box.")}}})

        diff = compare.diff_snapshots(before, after)

        assert diff["summary_changed"] == [
            {"library": "rich", "id": "rich:A", "before": "Box constant.", "after": "A styled box."}
        ]
        assert diff["removed"] == []
        assert diff["added"] == []
        assert diff["kind_changed"] == []
        assert diff["module_changed"] == []

    def test_detects_module_change_without_touching_other_sections(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym(module="rich.box")}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym(module="rich._box")}}})

        diff = compare.diff_snapshots(before, after)

        assert diff["module_changed"] == [
            {"library": "rich", "id": "rich:A", "before": "rich.box", "after": "rich._box"}
        ]
        assert diff["removed"] == []
        assert diff["added"] == []
        assert diff["kind_changed"] == []
        assert diff["summary_changed"] == []

    def test_detects_type_change_without_touching_other_sections(self):
        compare = _load("compare.py")
        before = _snap({"anyio": {"symbols": {"anyio:A": _sym(
            module="anyio", types={"sig0.param[encoding]": "dataclasses.InitVar[str]"}
        )}}})
        after = _snap({"anyio": {"symbols": {"anyio:A": _sym(
            module="anyio", types={"sig0.param[encoding]": "InitVar[str]"}
        )}}})

        diff = compare.diff_snapshots(before, after)

        assert diff["type_changed"] == [
            {
                "library": "anyio",
                "id": "anyio:A",
                "field": "sig0.param[encoding]",
                "before": "dataclasses.InitVar[str]",
                "after": "InitVar[str]",
            }
        ]
        assert diff["removed"] == []
        assert diff["added"] == []
        assert diff["kind_changed"] == []
        assert diff["module_changed"] == []
        assert diff["summary_changed"] == []

    def test_type_changed_section_sits_between_module_changed_and_summary_changed(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym(
            types={"sig0.returns": "str"}
        )}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym(
            types={"sig0.returns": "bytes"}
        )}}})

        rendered = compare.render(compare.diff_snapshots(before, after))

        assert (
            rendered.index("MODULE CHANGED")
            < rendered.index("TYPE CHANGED")
            < rendered.index("SUMMARY CHANGED")
        )

    def test_a_returns_only_change_is_reported(self):
        compare = _load("compare.py")
        before = _snap({"c": {"symbols": {"c:f": _sym(
            module="c", types={"sig0.returns": "<c._Shim object>"}
        )}}})
        after = _snap({"c": {"symbols": {"c:f": _sym(
            module="c", types={"sig0.returns": "DHPrivateNumbers"}
        )}}})

        diff = compare.diff_snapshots(before, after)

        assert [d["field"] for d in diff["type_changed"]] == ["sig0.returns"]

    def test_old_snapshot_without_types_is_not_reported_as_zero_type_changes(self):
        """A snapshot predating type recording must not read as "no impact".

        Reporting ``TYPE CHANGED (0)`` there would recreate the exact false
        reassurance this section exists to remove: before types were
        recorded, a scanner change that moved only type hints produced a
        wholly empty report.
        """
        compare = _load("compare.py")
        legacy = {"kind": "function", "module": "rich", "summary": "A box."}
        before = _snap({"rich": {"symbols": {"rich:A": legacy}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym(
            kind="function", summary="A box.", types={"sig0.returns": "str"}
        )}}})

        diff = compare.diff_snapshots(before, after)
        rendered = compare.render(diff)

        assert diff["types_recorded"] is False
        assert diff["type_changed"] == []
        assert "TYPE CHANGED (not comparable)" in rendered
        assert "TYPE CHANGED (0)" not in rendered

    def test_symbol_with_several_changed_fields_appears_in_each_section_once(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {
            "rich:A": _sym(kind="constant", module="rich.box", summary="Box constant."),
        }}})
        after = _snap({"rich": {"symbols": {
            "rich:A": _sym(kind="function", module="rich._box", summary="A styled box."),
        }}})

        diff = compare.diff_snapshots(before, after)

        assert len(diff["kind_changed"]) == 1
        assert len(diff["module_changed"]) == 1
        assert len(diff["summary_changed"]) == 1
        assert diff["kind_changed"][0]["id"] == "rich:A"
        assert diff["module_changed"][0]["id"] == "rich:A"
        assert diff["summary_changed"][0]["id"] == "rich:A"

    def test_proven_regression_two_snapshots_differing_only_in_summary(self):
        """Reproduces the exact failure this fix targets: before this fix,
        two snapshots whose *every* symbol summary differs rendered as
        REMOVED (0) / KIND CHANGED (0) / ADDED (0) -- a silent pass."""
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {
            "rich:A": _sym(summary="old summary A"),
            "rich:B": _sym(summary="old summary B"),
        }}})
        after = _snap({"rich": {"symbols": {
            "rich:A": _sym(summary="new summary A"),
            "rich:B": _sym(summary="new summary B"),
        }}})

        diff = compare.diff_snapshots(before, after)
        rendered = compare.render(diff)

        assert diff["removed"] == []
        assert diff["added"] == []
        assert diff["kind_changed"] == []
        assert len(diff["summary_changed"]) == 2
        assert "SUMMARY CHANGED (2)" in rendered
        assert "REMOVED (0)" in rendered
        assert "ADDED (0)" in rendered

    def test_summary_changed_section_is_between_kind_changed_and_added(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {
            "rich:A": _sym(kind="constant"),
            "rich:B": _sym(summary="old"),
        }}})
        after = _snap({"rich": {"symbols": {
            "rich:A": _sym(kind="function"),
            "rich:B": _sym(summary="new"),
            "rich:NEW": _sym(),
        }}})

        rendered = compare.render(compare.diff_snapshots(before, after))

        assert (
            rendered.index("KIND CHANGED")
            < rendered.index("SUMMARY CHANGED")
            < rendered.index("ADDED")
        )

    def test_changed_field_section_samples_at_most_three_ids(self):
        compare = _load("compare.py")
        symbols_before = {f"numpy:s{i}": _sym(summary=f"old {i}") for i in range(5)}
        symbols_after = {f"numpy:s{i}": _sym(summary=f"new {i}") for i in range(5)}
        before = _snap({"numpy": {"symbols": symbols_before}})
        after = _snap({"numpy": {"symbols": symbols_after}})

        rendered = compare.render(compare.diff_snapshots(before, after))

        assert "SUMMARY CHANGED (5)" in rendered
        assert rendered.count("numpy:s") == 3
        assert "..." in rendered

    # -- FIX 7: provenance drift ---------------------------------------------

    def test_diff_provenance_reports_python_and_library_version_drift(self):
        compare = _load("compare.py")
        before = _snap({})
        after = _snap({})
        before["provenance"]["python"] = "3.11.0"
        after["provenance"]["python"] = "3.12.0"
        before["provenance"]["versions"] = {"numpy": "1.26.0"}
        after["provenance"]["versions"] = {"numpy": "2.0.0"}

        diffs = compare.diff_provenance(before, after)

        assert {"item": "python", "before": "3.11.0", "after": "3.12.0"} in diffs
        assert {"item": "numpy", "before": "1.26.0", "after": "2.0.0"} in diffs

    def test_render_provenance_shows_a_version_difference(self):
        compare = _load("compare.py")
        diffs = [{"item": "numpy", "before": "1.26.0", "after": "2.0.0"}]

        rendered = compare.render_provenance(diffs)

        assert "PROVENANCE DIFFERENCES (1)" in rendered
        assert "numpy" in rendered
        assert "1.26.0 -> 2.0.0" in rendered

    def test_render_provenance_empty_when_no_drift(self):
        compare = _load("compare.py")
        assert compare.render_provenance([]) == ""

    def test_main_prints_provenance_banner_and_still_exits_zero(self, tmp_path):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym()}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym()}}})
        before["provenance"]["versions"] = {"numpy": "1.26.0"}
        after["provenance"]["versions"] = {"numpy": "2.0.0"}

        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"
        before_path.write_text(json.dumps(before), encoding="utf-8")
        after_path.write_text(json.dumps(after), encoding="utf-8")

        rc = compare.main([str(before_path), str(after_path)])

        assert rc == 0

    # -- FIX 10: main() and the _object_type None path -----------------------

    def test_main_returns_zero(self, tmp_path):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {"rich:A": _sym()}}})
        after = _snap({"rich": {"symbols": {"rich:A": _sym()}}})

        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"
        before_path.write_text(json.dumps(before), encoding="utf-8")
        after_path.write_text(json.dumps(after), encoding="utf-8")

        assert compare.main([str(before_path), str(after_path)]) == 0

    def test_object_type_is_none_for_ordinary_prose(self):
        compare = _load("compare.py")
        assert compare._object_type("Return the mean of the array.") is None
        assert compare._object_type(None) is None

    def test_added_symbol_falls_back_to_kind_when_object_type_is_none(self):
        compare = _load("compare.py")
        before = _snap({"rich": {"symbols": {}}})
        after = _snap({"rich": {"symbols": {
            "rich:new_func": _sym(kind="function", summary="Return the mean of the array."),
        }}})

        diff = compare.diff_snapshots(before, after)
        rendered = compare.render(diff)

        assert diff["added"][0]["type"] is None
        assert "function x1" in rendered
