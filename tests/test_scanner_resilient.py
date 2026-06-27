"""Scanner must not abort when a member access raises (e.g. lazy/moved attrs).

Regression for packages like google-adk that use PEP 562 module ``__getattr__``
to lazily resolve submodules; a moved/removed submodule raises
``ModuleNotFoundError`` on attribute access, which previously aborted the whole
scan instead of skipping the single bad member.
"""

import sys
import textwrap
import types

import pytest

from lcp.scanner import (
    _is_member_from_package,
    _parse_docstring,
    scan_package,
)


@pytest.fixture
def poison_module():
    """A package-like module whose ``dir()`` exposes an attribute that raises."""
    mod = types.ModuleType("poisonpkg")
    mod.__path__ = []  # mark as a package

    def __getattr__(name):
        if name == "moved_thing":
            raise ModuleNotFoundError("poisonpkg.moved_thing is moved to elsewhere")
        raise AttributeError(name)

    def __dir__():
        return ["GOOD", "moved_thing"]

    mod.__getattr__ = __getattr__
    mod.__dir__ = __dir__
    mod.GOOD = 42  # a real public constant the scan SHOULD capture
    sys.modules["poisonpkg"] = mod
    try:
        yield mod
    finally:
        sys.modules.pop("poisonpkg", None)


@pytest.fixture
def poison_class_module():
    """A module exposing a class whose ``dir()`` lists a member that raises.

    Uses a metaclass ``__getattr__``/``__dir__`` so that ``getattr(cls, "broken")``
    raises ``AttributeError`` during ``inspect.getmembers(cls)`` — the
    class-level analogue of a moved/removed lazy attribute.
    """
    mod = types.ModuleType("poisonclspkg")

    class Meta(type):
        def __getattr__(cls, name):
            if name == "broken":
                raise AttributeError("Widget.broken backend is gone")
            raise AttributeError(name)

        def __dir__(cls):
            return list(super().__dir__()) + ["broken"]

    class Widget(metaclass=Meta):
        """A widget."""

        def ok_method(self):
            """Fine."""
            return 1

    Widget.__module__ = "poisonclspkg"  # so it isn't filtered as re-exported
    mod.Widget = Widget
    sys.modules["poisonclspkg"] = mod
    try:
        yield mod
    finally:
        sys.modules.pop("poisonclspkg", None)


def test_scan_does_not_abort_on_raising_module_member(poison_module):
    result = scan_package("poisonpkg")
    names = {s.name for s in result.symbols}
    assert "GOOD" in names  # real symbol still captured
    assert "moved_thing" not in names  # the raising attr is skipped, not fatal


def test_scan_does_not_abort_on_raising_class_member(poison_class_module):
    # Must not raise; the class is scanned, the raising property skipped.
    result = scan_package("poisonclspkg")
    names = {s.name for s in result.symbols}
    assert "Widget" in names


@pytest.fixture
def hostile_isinstance_module():
    """A module whose member raises merely on being *classified*.

    Mirrors ``django.conf.settings`` (a lazy object): fetching the member is
    fine, but ``inspect.ismodule()`` / ``isinstance()`` triggers its
    ``__getattribute__`` and raises (``ImproperlyConfigured`` in django). The
    fetch guard (``_safe_getmembers``) does not cover this later step.
    """
    mod = types.ModuleType("hostilepkg")

    class Hostile:
        def __getattribute__(self, name):
            raise RuntimeError("settings are not configured")

    mod.settings = Hostile()
    mod.GOOD = 7  # a real public constant the scan SHOULD capture
    sys.modules["hostilepkg"] = mod
    try:
        yield mod
    finally:
        sys.modules.pop("hostilepkg", None)


def test_scan_does_not_abort_when_member_classification_raises(hostile_isinstance_module):
    # Must not raise; the hostile member is skipped, the healthy one kept.
    result = scan_package("hostilepkg")
    names = {s.name for s in result.symbols}
    assert "GOOD" in names
    assert "settings" not in names


def _build_pkg(tmp_path, name, files):
    """Write a real on-disk package and put it on ``sys.path``.

    Returns the package name; caller's modules are cleaned up by the fixture.
    """
    pkg_dir = tmp_path / name
    pkg_dir.mkdir()
    for filename, content in files.items():
        (pkg_dir / filename).write_text(textwrap.dedent(content))
    sys.path.insert(0, str(tmp_path))
    return name


@pytest.fixture
def cleanup_imports():
    """Remove any test packages we imported and restore ``sys.path``."""
    original_path = list(sys.path)
    imported_before = set(sys.modules)
    try:
        yield
    finally:
        sys.path[:] = original_path
        for mod_name in set(sys.modules) - imported_before:
            sys.modules.pop(mod_name, None)


def test_scan_survives_submodule_raising_systemexit(tmp_path, cleanup_imports):
    """A submodule that calls ``sys.exit()`` at import must not kill the scan.

    Many real packages ship submodules that run a CLI on import (e.g.
    ``numpy.f2py.__main__``, ``flask.__main__``) or call ``pytest.importorskip``
    inside ``tests/`` — these raise ``SystemExit`` / ``Skipped``, which are
    ``BaseException`` subclasses, not ``Exception``.
    """
    name = _build_pkg(tmp_path, "sysexitpkg", {
        "__init__.py": "GOOD = 1\n",
        "good.py": "def real_function():\n    '''A real function.'''\n    return 1\n",
        "boom.py": "import sys\nsys.exit(7)\n",
    })
    result = scan_package(name)  # must not raise SystemExit
    names = {s.name for s in result.symbols}
    assert "real_function" in names  # healthy submodule still scanned
    assert not any("boom" in n for n in names)  # the exiting one is skipped


def test_scan_skips_dunder_main_module(tmp_path, cleanup_imports):
    """``__main__`` submodules are entry-point scripts, never public API.

    Importing them runs arbitrary CLI code at import time, so they must be
    skipped entirely (not merely survived).
    """
    sentinel = tmp_path / "main_was_executed"
    name = _build_pkg(tmp_path, "mainpkg", {
        "__init__.py": "GOOD = 1\n",
        "good.py": "def real_function():\n    '''A real function.'''\n    return 1\n",
        "__main__.py": f"open({str(sentinel)!r}, 'w').close()\n",
    })
    result = scan_package(name)
    names = {s.name for s in result.symbols}
    assert not any("__main__" in n for n in names)
    assert "real_function" in names  # healthy submodule still scanned
    assert not sentinel.exists()  # __main__ body must never have run


def test_parse_docstring_handles_non_string_doc():
    """A class can define ``__doc__`` as a ``property`` (e.g. sympy).

    ``cls.__doc__`` then returns the property object, not a string;
    ``_parse_docstring`` must treat any non-string as 'no docstring'.
    """
    class PropDoc:
        @property
        def __doc__(self):  # pragma: no cover - only its type matters here
            return "dynamic"

    assert _parse_docstring(PropDoc.__doc__) == (None, None)


def test_is_member_from_package_handles_non_string_module():
    """A base class can expose ``__module__`` as a non-string descriptor.

    C-level slots (e.g. zope.interface) make ``base.__module__`` a
    ``member_descriptor``; the package-membership check must not assume str.
    """
    class HasSlot:
        __slots__ = ("x",)

    member_descriptor = HasSlot.__dict__["x"]

    class WeirdBase:
        def shared_method(self):
            return 1

    WeirdBase.__module__ = member_descriptor  # non-string __module__

    class Child(WeirdBase):
        pass

    Child.__module__ = "mypkg"

    # Must not raise; a non-string module simply isn't within the package root.
    assert _is_member_from_package(Child, "shared_method", "mypkg") is False
