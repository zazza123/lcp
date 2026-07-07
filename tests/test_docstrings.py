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
        def boom(text):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr("lcp.docstrings._parse", boom)
        assert extract_structured(GOOGLE) is None


GOOGLE_EXAMPLES = '''Do a thing.

Examples:
    Basic usage:

    >>> do_thing(1)
    'ok'
    >>> do_thing(2)
    'ok2'
'''

NUMPY_EXAMPLES = '''Compute stuff.

Examples
--------
>>> compute(3)
9
'''

VERBATIM = '''Run it.

Examples:
    result = run(cfg)
    print(result)
'''


class TestExamples:
    """Doctest and verbatim extraction from Examples sections."""

    def test_google_doctest_block(self):
        extras = extract_structured(GOOGLE_EXAMPLES)
        assert len(extras.examples) == 1
        code, description = extras.examples[0]
        assert ">>> do_thing(1)" in code
        assert "'ok'" in code  # expected output preserved
        assert ">>> do_thing(2)" in code
        assert description == "Basic usage:"

    def test_numpy_doctest_block(self):
        extras = extract_structured(NUMPY_EXAMPLES)
        assert len(extras.examples) == 1
        code, _ = extras.examples[0]
        assert ">>> compute(3)" in code
        assert "9" in code

    def test_multiline_doctest_statement(self):
        doc = (
            "T.\n\nExamples:\n"
            "    >>> for i in range(2):\n"
            "    ...     print(i)\n"
            "    0\n"
            "    1\n"
        )
        code, _ = extract_structured(doc).examples[0]
        assert ">>> for i in range(2):" in code
        assert "...     print(i)" in code

    def test_non_doctest_block_verbatim(self):
        extras = extract_structured(VERBATIM)
        code, description = extras.examples[0]
        assert code == "result = run(cfg)\nprint(result)"
        assert description is None

    def test_malformed_doctest_does_not_kill_params(self, monkeypatch):
        import doctest

        def boom(self, text, name="<string>"):
            raise ValueError("bad doctest")

        monkeypatch.setattr(doctest.DocTestParser, "parse", boom)
        extras = extract_structured(GOOGLE + "\nExamples:\n    >>> x(1)\n")
        assert extras.param_descriptions["x"] == "The x value."
        assert extras.examples == []
