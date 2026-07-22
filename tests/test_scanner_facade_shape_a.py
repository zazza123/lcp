"""Tests for facade shape A — full sibling implementation package (#68)."""

from pathlib import PurePosixPath

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
