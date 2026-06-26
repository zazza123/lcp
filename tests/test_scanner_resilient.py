"""Scanner must not abort when a member access raises (e.g. lazy/moved attrs).

Regression for packages like google-adk that use PEP 562 module ``__getattr__``
to lazily resolve submodules; a moved/removed submodule raises
``ModuleNotFoundError`` on attribute access, which previously aborted the whole
scan instead of skipping the single bad member.
"""

import sys
import types

import pytest

from lcp.scanner import scan_package


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
