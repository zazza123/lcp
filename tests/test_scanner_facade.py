"""Tests for facade thin cross-distribution re-export capture (#67)."""

import facade_fixtures as fx
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
