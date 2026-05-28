"""Tests for the AI hierarchy module."""

from __future__ import annotations

import textwrap


from lcp.ai.hierarchy import (
    ModuleTree,
    SymbolNode,
    build_context,
    build_hierarchy,
    LEVEL_LEAF,
    LEVEL_CLASS,
    LEVEL_MODULE,
)


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


SAMPLE_MODULE_SOURCE = textwrap.dedent('''\
    """Existing module docstring."""

    import os
    from pathlib import Path

    MAX_SIZE = 100

    def helper(x: int) -> int:
        """Add one to x."""
        return x + 1

    class MyClass:
        """A sample class."""

        name: str

        def __init__(self, name: str):
            self.name = name

        def greet(self) -> str:
            return f"Hello {self.name}"

        def farewell(self) -> str:
            """Say goodbye."""
            return f"Bye {self.name}"
''')


class TestBuildContext:
    """Tests for build_context function."""

    def _make_tree(self, source_file: str) -> ModuleTree:
        """Helper to create a ModuleTree."""
        root = SymbolNode(
            symbol={"kind": "module", "module": "pkg.mod", "entity": "pkg.mod", "source_file": source_file},
            kind="module",
            level=LEVEL_MODULE,
        )
        tree = ModuleTree(
            module_name="pkg.mod",
            source_file=source_file,
            root=root,
        )
        return tree

    def test_level0_function_context(self, tmp_path):
        """Level 0 context returns source code of the function."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE_SOURCE, encoding="utf-8")

        tree = self._make_tree(str(src))
        node = SymbolNode(
            symbol={"kind": "function", "module": "pkg.mod", "entity": "helper", "source_file": str(src)},
            kind="function",
            level=LEVEL_LEAF,
        )
        context = build_context(node, tree)
        assert "def helper(x: int) -> int:" in context
        assert "return x + 1" in context

    def test_level1_class_context_with_child_docstrings(self, tmp_path):
        """Level 1 context includes child docstrings for documented methods."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE_SOURCE, encoding="utf-8")

        tree = self._make_tree(str(src))

        child_greet = SymbolNode(
            symbol={"kind": "method", "module": "pkg.mod", "entity": "MyClass#greet", "source_file": str(src)},
            kind="method",
            level=LEVEL_LEAF,
            docstring="Return a greeting message with the instance name.",
            status="updated",
        )
        child_farewell = SymbolNode(
            symbol={"kind": "method", "module": "pkg.mod", "entity": "MyClass#farewell", "source_file": str(src)},
            kind="method",
            level=LEVEL_LEAF,
            docstring="Say goodbye.",
            status="skipped",
        )

        class_node = SymbolNode(
            symbol={"kind": "class", "module": "pkg.mod", "entity": "MyClass", "source_file": str(src)},
            kind="class",
            level=LEVEL_CLASS,
            children=[child_greet, child_farewell],
        )

        context = build_context(class_node, tree)
        assert "class MyClass" in context
        assert "Return a greeting message" in context
        assert "Say goodbye" in context

    def test_level1_class_context_failed_child_shows_signature(self, tmp_path):
        """Failed children show only their signature, not docstring."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE_SOURCE, encoding="utf-8")

        tree = self._make_tree(str(src))

        child_greet = SymbolNode(
            symbol={"kind": "method", "module": "pkg.mod", "entity": "MyClass#greet", "source_file": str(src)},
            kind="method",
            level=LEVEL_LEAF,
            status="failed",
        )
        class_node = SymbolNode(
            symbol={"kind": "class", "module": "pkg.mod", "entity": "MyClass", "source_file": str(src)},
            kind="class",
            level=LEVEL_CLASS,
            children=[child_greet],
        )

        context = build_context(class_node, tree)
        assert "class MyClass" in context
        assert "greet" in context

    def test_level2_module_context_uses_summaries(self, tmp_path):
        """Level 2 context uses only summary lines, not full docstrings."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE_SOURCE, encoding="utf-8")

        tree = self._make_tree(str(src))

        child_class = SymbolNode(
            symbol={"kind": "class", "module": "pkg.mod", "entity": "MyClass", "source_file": str(src)},
            kind="class",
            level=LEVEL_CLASS,
            docstring="A sample class that greets people.\n\nIt supports multiple languages.",
            status="updated",
        )
        child_func = SymbolNode(
            symbol={"kind": "function", "module": "pkg.mod", "entity": "helper", "source_file": str(src)},
            kind="function",
            level=LEVEL_LEAF,
            docstring="Add one to x.",
            status="updated",
        )
        tree.root.children = [child_class, child_func]

        context = build_context(tree.root, tree)
        # Should include top-of-file
        assert "import os" in context
        # Should use summary line only (first line of docstring)
        assert "A sample class that greets people." in context
        assert "It supports multiple languages." not in context
        assert "Add one to x." in context
