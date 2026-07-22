"""Tests for facade shape A — full sibling implementation package (#68)."""

from pathlib import PurePosixPath

from lcp import scanner
from lcp.scanner import _is_sibling_module, _own_distribution_modules


class _FakeDist:
    """Minimal stand-in for importlib.metadata.Distribution: only `.files`."""

    def __init__(self, files):
        self.files = [PurePosixPath(p) for p in files]


_FIRESTORE_FILES = [
    "google/cloud/firestore/__init__.py",
    "google/cloud/firestore_v1/__init__.py",
    "google/cloud/firestore_v1/client.py",
    "google/cloud/firestore_admin_v1/__init__.py",
]
_AUTH_FILES = [
    "google/auth/__init__.py",
    "google/auth/credentials.py",
]


def test_own_distribution_modules_collects_sibling_paths(monkeypatch):
    monkeypatch.setattr(
        "importlib.metadata.distributions",
        lambda: [_FakeDist(_FIRESTORE_FILES), _FakeDist(_AUTH_FILES)],
    )
    mods = _own_distribution_modules("google.cloud.firestore")
    assert "google.cloud.firestore_v1" in mods
    assert "google.cloud.firestore_v1.client" in mods
    assert "google.cloud.firestore_admin_v1" in mods
    # a different distribution's modules are not included
    assert "google.auth" not in mods
    assert "google.auth.credentials" not in mods


def test_own_distribution_modules_empty_on_failure(monkeypatch):
    def boom():
        raise RuntimeError("no metadata")

    monkeypatch.setattr("importlib.metadata.distributions", boom)
    assert _own_distribution_modules("google.cloud.firestore") == frozenset()


def test_own_distribution_modules_empty_when_unowned(monkeypatch):
    monkeypatch.setattr(
        "importlib.metadata.distributions", lambda: [_FakeDist(_AUTH_FILES)]
    )
    assert _own_distribution_modules("google.cloud.firestore") == frozenset()


def test_is_sibling_module_rules():
    siblings = frozenset(
        {"google.cloud.firestore_v1", "google.cloud.firestore_v1.client",
         "google.cloud.firestore_admin_v1"}
    )
    pkg = "google.cloud.firestore"
    # sibling in the same distribution, outside the scanned subtree -> follow
    assert _is_sibling_module("google.cloud.firestore_v1.client", pkg, siblings) is True
    assert _is_sibling_module("google.cloud.firestore_v1", pkg, siblings) is True
    # inside the scanned subtree -> not a sibling (normal recursion handles it)
    assert _is_sibling_module("google.cloud.firestore.batch", pkg, siblings) is False
    assert _is_sibling_module("google.cloud.firestore", pkg, siblings) is False
    # same distribution but not among the provided modules -> skip
    assert _is_sibling_module("google.auth.credentials", pkg, siblings) is False


def test_own_distribution_modules_survives_bad_distribution(monkeypatch):
    class _BadDist:
        @property
        def files(self):
            raise RuntimeError("malformed RECORD")

    monkeypatch.setattr(
        "importlib.metadata.distributions",
        lambda: [_BadDist(), _FakeDist(_FIRESTORE_FILES)],
    )
    mods = _own_distribution_modules("google.cloud.firestore")
    # the bad distribution is skipped; the good one still resolves
    assert "google.cloud.firestore_v1" in mods


def test_own_distribution_modules_filters_non_py_and_non_identifier(monkeypatch):
    files = [
        "google/cloud/firestore/__init__.py",
        "google/cloud/firestore/data.json",       # non-.py -> skipped
        "google/cloud/firestore-extra/mod.py",    # 'firestore-extra' not an identifier -> skipped
        "single_mod.py",                          # single top-level module
    ]
    monkeypatch.setattr("importlib.metadata.distributions", lambda: [_FakeDist(files)])
    mods = _own_distribution_modules("google.cloud.firestore")
    assert "google.cloud.firestore" in mods
    assert "single_mod" in mods
    assert not any("firestore-extra" in m for m in mods)
    assert not any("json" in m for m in mods)


def _thing_record():
    return scanner._AliasRecord(
        target_module="facadelib.impl.core",
        target_name="Thing",
        alias_module="facadelib.facade",
        alias_name="Thing",
    )


def test_synth_module_symbol_copies_docstring():
    sym = scanner._synth_module_symbol("facadelib.impl.core")
    assert sym.kind == "module"
    assert sym.module_path == "facadelib.impl.core"
    assert sym.qualified_name == ""
    assert "Implementation module" in (sym.summary or "")


def test_synth_module_symbol_bare_on_import_failure():
    sym = scanner._synth_module_symbol("facadelib.nope.missing")
    assert sym.kind == "module"
    assert sym.summary == "Module facadelib.nope.missing"


def test_capture_sibling_reexports_at_def_site():
    captured, synth = scanner._capture_sibling_reexports(
        [_thing_record()],
        existing=[],
        package_name="facadelib.facade",
        sibling_modules=frozenset({"facadelib.impl", "facadelib.impl.core"}),
        include_private=False,
    )
    assert len(captured) == 1
    thing = captured[0]
    assert thing.module_path == "facadelib.impl.core"
    assert thing.qualified_name == "Thing"
    assert thing.kind == "class"
    assert any(m.qualified_name == "Thing#method" for m in thing.members)
    assert [s.module_path for s in synth] == ["facadelib.impl.core"]
    assert synth[0].kind == "module"


def test_capture_sibling_reexports_skips_non_sibling():
    # target inside the scanned subtree -> not a sibling
    rec = scanner._AliasRecord(
        target_module="facadelib.facade.sub",
        target_name="Thing",
        alias_module="facadelib.facade",
        alias_name="Thing",
    )
    captured, synth = scanner._capture_sibling_reexports(
        [rec], [], "facadelib.facade",
        frozenset({"facadelib.facade.sub"}), False,
    )
    assert captured == [] and synth == []


def test_capture_sibling_reexports_dedups_by_canonical_key():
    # same object re-exported under two facade names -> captured once
    rec_a = _thing_record()
    rec_b = scanner._AliasRecord(
        target_module="facadelib.impl.core",
        target_name="Thing",
        alias_module="facadelib.facade",
        alias_name="ThingAlias",
    )
    captured, synth = scanner._capture_sibling_reexports(
        [rec_a, rec_b], [], "facadelib.facade",
        frozenset({"facadelib.impl.core"}), False,
    )
    assert len(captured) == 1
    assert len(synth) == 1


def test_capture_sibling_reexports_skips_already_scanned():
    existing = [
        scanner.ScannedSymbol(
            name="Thing", qualified_name="Thing",
            module_path="facadelib.impl.core", kind="class",
        )
    ]
    captured, synth = scanner._capture_sibling_reexports(
        [_thing_record()], existing, "facadelib.facade",
        frozenset({"facadelib.impl.core"}), False,
    )
    assert captured == [] and synth == []


def test_capture_sibling_reexports_defers_cfunc():
    rec = scanner._AliasRecord(
        target_module="facadelib.impl.deferred",
        target_name="cfunc",
        alias_module="facadelib.facade",
        alias_name="cfunc",
    )
    captured, synth = scanner._capture_sibling_reexports(
        [rec], [], "facadelib.facade",
        frozenset({"facadelib.impl.deferred"}), False,
    )
    assert captured == [] and synth == []  # deferred -> not captured, no module synthesized


def _scan_facade(monkeypatch):
    """Scan the fixture facade with the sibling distribution monkeypatched in."""
    monkeypatch.setattr(
        scanner,
        "_own_distribution_modules",
        lambda pkg: frozenset(
            {"facadelib.facade", "facadelib.impl", "facadelib.impl.core",
             "facadelib.impl.deferred"}
        ),
    )
    return scanner.scan_package("facadelib.facade")


def test_scan_package_captures_sibling_at_def_site_with_alias(monkeypatch):
    sm = _scan_facade(monkeypatch)
    by_key = {(s.module_path, s.qualified_name): s for s in sm.symbols}

    thing = by_key[("facadelib.impl.core", "Thing")]
    assert thing.kind == "class"
    assert any(m.qualified_name == "Thing#method" for m in thing.members)
    assert ("facadelib.facade", "Thing") in thing.aliases

    func = by_key[("facadelib.impl.core", "thing_func")]
    assert func.kind == "function"
    assert ("facadelib.facade", "thing_func") in func.aliases


def test_scan_package_captures_sibling_value_sentinel_at_facade(monkeypatch):
    sm = _scan_facade(monkeypatch)
    by_key = {(s.module_path, s.qualified_name): s for s in sm.symbols}
    # a name-less sentinel from the sibling is captured at the facade id (no alias)
    sentinel = by_key[("facadelib.facade", "SERVER_TS")]
    assert sentinel.kind == "constant"
    assert not sentinel.aliases
    # it is NOT also placed at the sibling def-site
    assert ("facadelib.impl.core", "SERVER_TS") not in by_key


def test_scan_package_synthesizes_sibling_module_entry(monkeypatch):
    sm = _scan_facade(monkeypatch)
    module_syms = [s for s in sm.symbols if s.kind == "module"]
    module_paths = {s.module_path for s in module_syms}
    assert "facadelib.impl.core" in module_paths


def test_scan_package_does_not_capture_foreign_or_deferred(monkeypatch):
    sm = _scan_facade(monkeypatch)
    keys = {(s.module_path, s.qualified_name) for s in sm.symbols}
    # foreign top-level (otherlib) is dropped, never captured
    assert ("otherlib.core", "Foreign") not in keys
    assert not any(s.qualified_name == "Foreign" for s in sm.symbols)
    # deferred C-style callable is not captured, and its module is not synthesized
    assert ("facadelib.impl.deferred", "cfunc") not in keys
    assert "facadelib.impl.deferred" not in {
        s.module_path for s in sm.symbols if s.kind == "module"
    }


def test_scan_package_reports_deferred_as_unresolved(monkeypatch):
    sm = _scan_facade(monkeypatch)
    # the deferred cfunc's record stays dangling -> reported, collapsed to depth 2
    # (package_name "facadelib.facade" has 2 segments, so
    # "facadelib.impl.deferred" collapses to "facadelib.impl")
    ancestors = {mod for mod, _names, _mods in sm.unresolved_reexports}
    assert "facadelib.impl" in ancestors
    # the captured names' module is NOT reported as lost (they resolved)
    assert "facadelib.impl.core" not in ancestors


def test_scan_package_generator_round_trip_carries_facade_alias(monkeypatch):
    # Closes the spec's resolve_library verification cheaply: the facade alias id
    # must reach the generated manifest, which is what LCPIndex.alias_to_canonical
    # and preferred_alias are built from.
    from lcp import generator

    sm = _scan_facade(monkeypatch)
    doc = generator.generate_lcp(sm)
    thing = doc.symbols["facadelib.impl.core:Thing"]
    assert "facadelib.facade:Thing" in (thing.aliases or [])


def test_scan_package_inert_when_no_out_of_subtree_reexport(monkeypatch):
    # sample_package re-exports only within itself; shape A must not fire and
    # _own_distribution_modules must not even be consulted.
    called = []
    monkeypatch.setattr(
        scanner, "_own_distribution_modules",
        lambda pkg: called.append(pkg) or frozenset(),
    )
    scanner.scan_package("sample_package")
    assert called == []  # guard skips the file-list walk for non-facade packages
