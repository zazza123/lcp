"""Tests for facade thin cross-distribution re-export capture (#67)."""

from lcp.scanner import (
    _followable_top_levels,
    _is_followable_reexport,
    _normalize_dist,
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
