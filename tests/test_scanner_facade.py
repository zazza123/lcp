"""Tests for facade thin cross-distribution re-export capture (#67)."""

import types

import facade_fixtures as fx
from lcp import scanner
from lcp.scanner import (
    _capture_reexport,
    _followable_top_levels,
    _is_followable_reexport,
    _normalize_dist,
    _reexport_kind,
)


def test_normalize_dist_collapses_separators():
    assert _normalize_dist("Fake_Dep.Name") == "fake-dep-name"
    assert _normalize_dist("Flask") == "flask"


def test_followable_top_levels_from_declared_deps(monkeypatch):
    pkg_dists = {
        "facade": ["Facade-Dist"],
        "fakedep": ["Fake-Dep"],
        "unrelated": ["Unrelated-Dist"],
    }
    monkeypatch.setattr("importlib.metadata.packages_distributions", lambda: pkg_dists)
    monkeypatch.setattr(
        "importlib.metadata.requires",
        lambda dist: ["fake-dep>=1.0"] if dist == "Facade-Dist" else [],
    )
    assert _followable_top_levels("facade") == frozenset({"fakedep"})


def test_followable_top_levels_handles_compatible_release_specifier(monkeypatch):
    pkg_dists = {"facade": ["Facade-Dist"], "fakedep": ["Fake-Dep"]}
    monkeypatch.setattr("importlib.metadata.packages_distributions", lambda: pkg_dists)
    monkeypatch.setattr(
        "importlib.metadata.requires",
        lambda dist: ["fake-dep~=1.4"] if dist == "Facade-Dist" else [],
    )
    assert _followable_top_levels("facade") == frozenset({"fakedep"})


def test_followable_top_levels_empty_when_dist_unknown(monkeypatch):
    monkeypatch.setattr("importlib.metadata.packages_distributions", lambda: {})
    assert _followable_top_levels("facade") == frozenset()


def test_is_followable_reexport_rules():
    tops = frozenset({"fakedep"})
    assert _is_followable_reexport("fakedep.core", tops) is True
    assert _is_followable_reexport("os.path", tops) is False  # stdlib
    assert _is_followable_reexport("other.mod", tops) is False  # not a declared dep
    assert _is_followable_reexport("fakedep.core", None) is False  # feature inert


def test_reexport_kind_class():
    assert _reexport_kind("ReexportedClass", fx.ReexportedClass) == "class"


def test_reexport_kind_function():
    assert _reexport_kind("reexported_function", fx.reexported_function) == "function"


def test_reexport_kind_noncallable_value():
    assert _reexport_kind("reexported_signal", fx.reexported_signal) == "value"


def test_reexport_kind_callable_signature_raises_is_value():
    assert _reexport_kind("reexported_proxy", fx.reexported_proxy) == "value"


def test_reexport_kind_callable_with_signature_defers():
    assert _reexport_kind("reexported_cfunc", fx.reexported_cfunc) == "defer"


def test_capture_reexport_value_is_constant():
    sym = _capture_reexport("reexported_proxy", fx.reexported_proxy, "facade", False)
    assert sym.kind == "constant"
    assert sym.module_path == "facade"
    assert sym.qualified_name == "reexported_proxy"
    assert sym.summary == "_ProxyType constant."


def test_capture_reexport_class_keeps_own_methods():
    sym = _capture_reexport("ReexportedClass", fx.ReexportedClass, "facade", False)
    assert sym.kind == "class"
    assert sym.module_path == "facade"
    assert any(m.qualified_name == "ReexportedClass#method" for m in sym.members)


def test_capture_reexport_defer_returns_none():
    assert (
        _capture_reexport("reexported_cfunc", fx.reexported_cfunc, "facade", False)
        is None
    )


def _make_facade():
    facade = types.ModuleType("facade")
    facade.__doc__ = "A facade package."
    facade.ReexportedClass = fx.ReexportedClass
    facade.reexported_function = fx.reexported_function
    facade.reexported_signal = fx.reexported_signal
    facade.reexported_proxy = fx.reexported_proxy
    facade.reexported_cfunc = fx.reexported_cfunc
    return facade


def test_scan_module_follows_declared_reexports():
    symbols = scanner.scan_module(
        _make_facade(),
        _package_root="facade",
        _followable_tops=frozenset({"fakedep"}),
    )
    by_id = {(s.module_path, s.qualified_name): s for s in symbols}
    assert by_id[("facade", "reexported_proxy")].kind == "constant"
    assert by_id[("facade", "reexported_signal")].kind == "constant"
    assert by_id[("facade", "reexported_function")].kind == "function"
    assert by_id[("facade", "ReexportedClass")].kind == "class"
    cls_sym = by_id[("facade", "ReexportedClass")]
    member_qns = {m.qualified_name for m in cls_sym.members}
    assert "ReexportedClass#method" in member_qns
    assert "ReexportedClass#inherited_method" in member_qns  # only kept if origin_root (fakedep), not facade, is used
    # signature-recoverable callable is deferred to #63, not captured
    assert ("facade", "reexported_cfunc") not in by_id


def test_scan_module_inert_without_followable_tops():
    symbols = scanner.scan_module(_make_facade(), _package_root="facade")
    ids = {(s.module_path, s.qualified_name) for s in symbols}
    assert ("facade", "reexported_proxy") not in ids
    assert ("facade", "ReexportedClass") not in ids


def test_scan_package_follows_reexports_in_entry_module_only(monkeypatch):
    sentinel = frozenset({"sentinel"})
    monkeypatch.setattr(scanner, "_followable_top_levels", lambda root: sentinel)

    calls = []
    real_scan_module = scanner.scan_module

    def recording(module, include_private=False, _visited=None, _package_root=None,
                  _alias_records=None, _followable_tops=None):
        calls.append((module.__name__, _followable_tops))
        return real_scan_module(module, include_private, _visited, _package_root,
                                _alias_records, _followable_tops)

    monkeypatch.setattr(scanner, "scan_module", recording)
    scanner.scan_package("sample_package")

    entry = [ft for name, ft in calls if name == "sample_package"]
    subs = [ft for name, ft in calls if name != "sample_package"]
    assert entry == [sentinel]          # entry module receives the computed set
    assert subs and all(ft is None for ft in subs)  # every submodule is inert
