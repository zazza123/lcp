"""Tests for structured docstring extraction (lcp.docstrings)."""

import pytest

from lcp.docstrings import extract_structured

GOOGLE = '''Do a thing.

Longer prose here.

Args:
    x (int): The x value.
    missing: Documented but not introspected.

Returns:
    str: The rendered result.

Raises:
    ValueError: If x is negative.
    KeyError: If lookup fails.
'''

NUMPY = '''Compute stuff.

Parameters
----------
x : int
    The x value.

Returns
-------
DataFrame
    A new frame.

Raises
------
ValueError
    If x is bad.
'''


class TestExtractStructured:
    """Google + NumPy extraction of params, raises and returns."""

    def test_google_params(self):
        extras = extract_structured(GOOGLE)
        assert extras.param_descriptions["x"] == "The x value."
        assert (
            extras.param_descriptions["missing"]
            == "Documented but not introspected."
        )

    def test_google_raises(self):
        extras = extract_structured(GOOGLE)
        assert ("ValueError", "If x is negative.") in extras.raises
        assert ("KeyError", "If lookup fails.") in extras.raises

    def test_google_returns_description(self):
        extras = extract_structured(GOOGLE)
        assert extras.returns_description == "The rendered result."

    def test_numpy_style(self):
        extras = extract_structured(NUMPY)
        assert extras.param_descriptions["x"] == "The x value."
        assert extras.returns_description == "A new frame."
        assert extras.raises == [("ValueError", "If x is bad.")]

    def test_indented_docstring_is_cleaned(self):
        # Raw __doc__ keeps the def-site indentation; extraction must cope.
        indented = (
            "Do a thing.\n\n        Args:\n            x: The x value.\n        "
        )
        extras = extract_structured(indented)
        assert extras.param_descriptions["x"] == "The x value."

    def test_variadic_names_normalized(self):
        doc = "Sum.\n\nArgs:\n    *args: Positional.\n    **kwargs: Keyword.\n"
        extras = extract_structured(doc)
        assert extras.param_descriptions == {
            "args": "Positional.",
            "kwargs": "Keyword.",
        }

    @pytest.mark.parametrize("value", [None, "", "   ", 42, object(), b"bytes"])
    def test_non_string_or_empty_returns_none(self, value):
        assert extract_structured(value) is None

    def test_unstructured_docstring_returns_none(self):
        assert extract_structured("Just a summary.\n\nProse only.") is None

    def test_raises_entry_without_type_is_skipped(self):
        # RaisesEntry.type is schema-required; a typeless entry is dropped.
        doc = "Boom.\n\nRaises\n------\n\n    Vague failure text.\n"
        extras = extract_structured(doc)
        assert extras is None or all(t for t, _ in extras.raises)

    def test_fail_open_on_parser_exception(self, monkeypatch):
        import lcp.docstrings as docstrings_mod

        def boom(text):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(docstrings_mod, "_parse", boom)
        assert extract_structured(GOOGLE) is None
