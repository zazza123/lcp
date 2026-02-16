"""Tests for the AI hierarchy module."""

from __future__ import annotations

import pytest

from lcp.ai.hierarchy import ModuleTree, SymbolNode, build_hierarchy


class TestSymbolNode:
    """Tests for SymbolNode dataclass."""

    def test_defaults(self):
        node = SymbolNode(
            symbol={"kind": "function", "module": "mod", "entity": "func"},
            kind="function",
            level=0,
            children=[],
        )
        assert node.docstring is None
        assert node.status == "pending"
        assert node.children == []

    def test_symbol_id(self):
        node = SymbolNode(
            symbol={"kind": "function", "module": "mod", "entity": "func"},
            kind="function",
            level=0,
            children=[],
        )
        assert node.symbol_id == "mod:func"


class TestBuildHierarchy:
    """Tests for build_hierarchy function."""

    def test_single_function(self):
        undocumented = [
            {"kind": "function", "module": "pkg.mod", "entity": "my_func", "source_file": "/path/mod.py"},
        ]
        trees = build_hierarchy(undocumented)

        assert "pkg.mod" in trees
        tree = trees["pkg.mod"]
        assert tree.module_name == "pkg.mod"
        assert tree.source_file == "/path/mod.py"
        # Function at level 0
        assert len(tree.levels[0]) == 1
        assert tree.levels[0][0].kind == "function"
        # Module root created as skipped (not in undocumented)
        assert tree.root.kind == "module"
        assert tree.root.status == "skipped"

    def test_class_with_methods(self):
        undocumented = [
            {"kind": "method", "module": "pkg.mod", "entity": "MyClass#method_a", "source_file": "/path/mod.py"},
            {"kind": "method", "module": "pkg.mod", "entity": "MyClass#method_b", "source_file": "/path/mod.py"},
            {"kind": "class", "module": "pkg.mod", "entity": "MyClass", "source_file": "/path/mod.py"},
        ]
        trees = build_hierarchy(undocumented)

        tree = trees["pkg.mod"]
        # 2 methods at level 0
        assert len(tree.levels[0]) == 2
        # 1 class at level 1
        assert len(tree.levels[1]) == 1
        class_node = tree.levels[1][0]
        assert class_node.kind == "class"
        assert len(class_node.children) == 2

    def test_method_with_documented_class(self):
        """Class is not in undocumented list (already documented)."""
        undocumented = [
            {"kind": "method", "module": "pkg.mod", "entity": "MyClass#method_a", "source_file": "/path/mod.py"},
        ]
        trees = build_hierarchy(undocumented)

        tree = trees["pkg.mod"]
        # Method at level 0
        assert len(tree.levels[0]) == 1
        # Class created as skipped container
        assert len(tree.levels[1]) == 1
        assert tree.levels[1][0].status == "skipped"
        assert tree.levels[1][0].children[0].kind == "method"

    def test_full_hierarchy(self):
        """Module, class, and methods all undocumented."""
        undocumented = [
            {"kind": "method", "module": "pkg.mod", "entity": "MyClass#do_thing", "source_file": "/path/mod.py"},
            {"kind": "class", "module": "pkg.mod", "entity": "MyClass", "source_file": "/path/mod.py"},
            {"kind": "function", "module": "pkg.mod", "entity": "helper", "source_file": "/path/mod.py"},
            {"kind": "module", "module": "pkg.mod", "entity": "pkg.mod", "source_file": "/path/mod.py"},
        ]
        trees = build_hierarchy(undocumented)

        tree = trees["pkg.mod"]
        # Level 0: method + function
        assert len(tree.levels[0]) == 2
        # Level 1: class
        assert len(tree.levels[1]) == 1
        # Level 2: module
        assert len(tree.levels[2]) == 1
        assert tree.root.status == "pending"

    def test_multiple_modules(self):
        undocumented = [
            {"kind": "function", "module": "pkg.a", "entity": "func_a", "source_file": "/path/a.py"},
            {"kind": "function", "module": "pkg.b", "entity": "func_b", "source_file": "/path/b.py"},
        ]
        trees = build_hierarchy(undocumented)

        assert len(trees) == 2
        assert "pkg.a" in trees
        assert "pkg.b" in trees

    def test_no_source_file_skipped(self):
        undocumented = [
            {"kind": "function", "module": "pkg.mod", "entity": "func"},
        ]
        trees = build_hierarchy(undocumented)
        assert len(trees) == 0

    def test_module_children_include_functions_and_classes(self):
        undocumented = [
            {"kind": "function", "module": "pkg.mod", "entity": "helper", "source_file": "/path/mod.py"},
            {"kind": "class", "module": "pkg.mod", "entity": "MyClass", "source_file": "/path/mod.py"},
            {"kind": "module", "module": "pkg.mod", "entity": "pkg.mod", "source_file": "/path/mod.py"},
        ]
        trees = build_hierarchy(undocumented)

        root = trees["pkg.mod"].root
        child_kinds = {c.kind for c in root.children}
        assert "function" in child_kinds
        assert "class" in child_kinds
