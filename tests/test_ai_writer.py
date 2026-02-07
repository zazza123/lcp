"""Tests for the AI writer module."""

import tempfile
from pathlib import Path

import pytest

from lcp.ai.writer import (
    _find_node,
    _format_docstring,
    _get_insertion_point,
    _has_docstring,
    inject_docstring,
    inject_docstrings_batch,
)
import ast


SAMPLE_SOURCE = '''\
def undocumented_func(x, y):
    return x + y


class MyClass:
    def undocumented_method(self, val):
        return val * 2

    def documented_method(self):
        """Already documented."""
        pass


def another_func():
    pass
'''

SAMPLE_WITH_MODULE_DOC = '''\
"""This module has a docstring."""

def foo():
    pass
'''


@pytest.fixture
def source_file(tmp_path):
    """Create a temporary Python file with sample source."""
    path = tmp_path / "sample.py"
    path.write_text(SAMPLE_SOURCE, encoding="utf-8")
    return path


@pytest.fixture
def source_file_with_module_doc(tmp_path):
    path = tmp_path / "sample_mod.py"
    path.write_text(SAMPLE_WITH_MODULE_DOC, encoding="utf-8")
    return path


class TestFindNode:
    """Tests for _find_node."""

    def test_find_function(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "function", "undocumented_func")
        assert node is not None
        assert isinstance(node, ast.FunctionDef)
        assert node.name == "undocumented_func"

    def test_find_class(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "class", "MyClass")
        assert node is not None
        assert isinstance(node, ast.ClassDef)

    def test_find_method(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "method", "MyClass#undocumented_method")
        assert node is not None
        assert isinstance(node, ast.FunctionDef)
        assert node.name == "undocumented_method"

    def test_find_module(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "module", "")
        assert node is not None
        assert isinstance(node, ast.Module)

    def test_find_nonexistent(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "function", "nonexistent")
        assert node is None

    def test_find_nonexistent_method(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "method", "MyClass#nonexistent")
        assert node is None

    def test_find_method_nonexistent_class(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "method", "NoClass#method")
        assert node is None


class TestHasDocstring:
    """Tests for _has_docstring."""

    def test_no_docstring(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "function", "undocumented_func")
        assert _has_docstring(node) is False

    def test_has_docstring(self):
        tree = ast.parse(SAMPLE_SOURCE)
        node = _find_node(tree, "method", "MyClass#documented_method")
        assert _has_docstring(node) is True

    def test_module_without_docstring(self):
        tree = ast.parse(SAMPLE_SOURCE)
        assert _has_docstring(tree) is False

    def test_module_with_docstring(self):
        tree = ast.parse(SAMPLE_WITH_MODULE_DOC)
        assert _has_docstring(tree) is True


class TestFormatDocstring:
    """Tests for _format_docstring."""

    def test_single_line(self):
        result = _format_docstring("A simple function.", "    ")
        assert result == '    """A simple function."""\n'

    def test_multi_line(self):
        content = "A function.\n\nArgs:\n    x: The value."
        result = _format_docstring(content, "    ")
        assert '"""A function.' in result
        assert '    Args:' in result
        assert '    """' in result

    def test_no_indent(self):
        result = _format_docstring("Module docstring.", "")
        assert result == '"""Module docstring."""\n'


class TestGetInsertionPoint:
    """Tests for _get_insertion_point."""

    def test_function_insertion(self):
        tree = ast.parse(SAMPLE_SOURCE)
        source_lines = SAMPLE_SOURCE.splitlines()
        node = _find_node(tree, "function", "undocumented_func")
        line_idx, indent = _get_insertion_point(node, source_lines)
        # Should insert after the def line
        assert line_idx == 1
        assert indent == "    "

    def test_module_insertion(self):
        tree = ast.parse(SAMPLE_SOURCE)
        source_lines = SAMPLE_SOURCE.splitlines()
        node = _find_node(tree, "module", "")
        line_idx, indent = _get_insertion_point(node, source_lines)
        assert line_idx == 0
        assert indent == ""


class TestInjectDocstring:
    """Tests for inject_docstring."""

    def test_inject_function(self, source_file):
        result = inject_docstring(
            str(source_file), "function", "undocumented_func", "Add two values."
        )
        assert result is True

        content = source_file.read_text(encoding="utf-8")
        assert '"""Add two values."""' in content

    def test_inject_class(self, source_file):
        result = inject_docstring(
            str(source_file), "class", "MyClass", "A sample class."
        )
        assert result is True

        content = source_file.read_text(encoding="utf-8")
        assert '"""A sample class."""' in content

    def test_inject_method(self, source_file):
        result = inject_docstring(
            str(source_file),
            "method",
            "MyClass#undocumented_method",
            "Multiply a value by 2.",
        )
        assert result is True

        content = source_file.read_text(encoding="utf-8")
        assert '"""Multiply a value by 2."""' in content

    def test_skip_documented(self, source_file):
        result = inject_docstring(
            str(source_file),
            "method",
            "MyClass#documented_method",
            "New docstring.",
        )
        assert result is False

    def test_skip_nonexistent(self, source_file):
        result = inject_docstring(
            str(source_file), "function", "nonexistent", "A docstring."
        )
        assert result is False

    def test_inject_module_docstring(self, source_file):
        result = inject_docstring(
            str(source_file), "module", "", "A sample module."
        )
        assert result is True

        content = source_file.read_text(encoding="utf-8")
        assert '"""A sample module."""' in content

    def test_skip_module_with_existing_docstring(self, source_file_with_module_doc):
        result = inject_docstring(
            str(source_file_with_module_doc), "module", "", "New module doc."
        )
        assert result is False

    def test_invalid_syntax(self, tmp_path):
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(\n", encoding="utf-8")

        result = inject_docstring(str(bad_file), "function", "broken", "A doc.")
        assert result is False


class TestInjectDocstringsBatch:
    """Tests for inject_docstrings_batch."""

    def test_batch_inject(self, source_file):
        injections = [
            ("function", "undocumented_func", "Add two values."),
            ("method", "MyClass#undocumented_method", "Multiply by 2."),
            ("function", "another_func", "Another function."),
        ]

        results = inject_docstrings_batch(str(source_file), injections)

        assert results == [True, True, True]

        content = source_file.read_text(encoding="utf-8")
        assert '"""Add two values."""' in content
        assert '"""Multiply by 2."""' in content
        assert '"""Another function."""' in content

    def test_batch_partial_failure(self, source_file):
        injections = [
            ("function", "undocumented_func", "Add two values."),
            ("function", "nonexistent", "No target."),
            ("method", "MyClass#documented_method", "Already has one."),
        ]

        results = inject_docstrings_batch(str(source_file), injections)

        assert results[0] is True
        assert results[1] is False
        assert results[2] is False

    def test_batch_invalid_syntax(self, tmp_path):
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(\n", encoding="utf-8")

        results = inject_docstrings_batch(
            str(bad_file), [("function", "broken", "A doc.")]
        )
        assert results == [False]
