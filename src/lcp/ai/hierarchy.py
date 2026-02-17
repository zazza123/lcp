"""Hierarchy builder for bottom-up documentation generation."""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# Level constants
LEVEL_LEAF = 0      # functions, methods
LEVEL_CLASS = 1     # classes
LEVEL_MODULE = 2    # modules

KIND_TO_LEVEL = {
    "function": LEVEL_LEAF,
    "method": LEVEL_LEAF,
    "class": LEVEL_CLASS,
    "module": LEVEL_MODULE,
}


@dataclass
class SymbolNode:
    """A node in the hierarchical symbol tree."""

    symbol: dict
    kind: str
    level: int
    children: list[SymbolNode] = field(default_factory=list)
    docstring: str | None = None
    status: str = "pending"

    @property
    def symbol_id(self) -> str:
        return f"{self.symbol.get('module', '')}:{self.symbol.get('entity', '')}"

    @property
    def entity(self) -> str:
        return self.symbol.get("entity", "")

    @property
    def module(self) -> str:
        return self.symbol.get("module", "")


@dataclass
class ModuleTree:
    """Hierarchical tree for a single module."""

    module_name: str
    source_file: str
    root: SymbolNode
    levels: dict[int, list[SymbolNode]] = field(default_factory=dict)


def _extract_class_name(entity: str) -> str | None:
    """Extract the class name from a method entity like 'MyClass#method'."""
    if "#" in entity:
        return entity.split("#", 1)[0]
    return None


def build_hierarchy(undocumented: list[dict]) -> dict[str, ModuleTree]:
    """Build a hierarchy of symbol trees from a flat list of undocumented symbols.

    Groups symbols by module, identifies parent-child relationships,
    and organizes them into levels for bottom-up processing.

    Args:
        undocumented: List of symbol dicts from coverage JSON.

    Returns:
        Dict mapping module name to ModuleTree.
    """
    # Filter out symbols without source files
    with_source = [s for s in undocumented if s.get("source_file")]

    # Group by module
    by_module: dict[str, list[dict]] = defaultdict(list)
    for sym in with_source:
        by_module[sym["module"]].append(sym)

    trees: dict[str, ModuleTree] = {}

    for module_name, symbols in by_module.items():
        tree = _build_module_tree(module_name, symbols)
        if tree is not None:
            trees[module_name] = tree

    return trees


def _build_module_tree(module_name: str, symbols: list[dict]) -> ModuleTree | None:
    """Build a ModuleTree for a single module's symbols."""
    if not symbols:
        return None

    source_file = symbols[0]["source_file"]

    # Create nodes for all undocumented symbols
    nodes: dict[str, SymbolNode] = {}
    for sym in symbols:
        entity = sym.get("entity", "")
        kind = sym.get("kind", "")
        level = KIND_TO_LEVEL.get(kind, LEVEL_LEAF)
        node = SymbolNode(symbol=sym, kind=kind, level=level)
        nodes[entity] = node

    # Identify class parents for methods
    class_names: set[str] = set()
    for sym in symbols:
        class_name = _extract_class_name(sym.get("entity", ""))
        if class_name:
            class_names.add(class_name)

    # Create skipped class nodes for classes not in undocumented list
    for class_name in class_names:
        if class_name not in nodes:
            placeholder = {
                "kind": "class",
                "module": module_name,
                "entity": class_name,
                "source_file": source_file,
            }
            node = SymbolNode(
                symbol=placeholder,
                kind="class",
                level=LEVEL_CLASS,
                status="skipped",
            )
            nodes[class_name] = node

    # Link methods to their parent classes
    for entity, node in list(nodes.items()):
        class_name = _extract_class_name(entity)
        if class_name and class_name in nodes:
            nodes[class_name].children.append(node)

    # Create or find module root
    if module_name in nodes and nodes[module_name].kind == "module":
        root = nodes[module_name]
    else:
        placeholder = {
            "kind": "module",
            "module": module_name,
            "entity": module_name,
            "source_file": source_file,
        }
        root = SymbolNode(
            symbol=placeholder,
            kind="module",
            level=LEVEL_MODULE,
            status="skipped",
        )

    # Link top-level symbols (classes, functions) to module root
    for entity, node in nodes.items():
        if node is root:
            continue
        # Only direct children: classes and top-level functions (no # in entity)
        if node.kind in ("class", "function"):
            root.children.append(node)

    # Build levels dict
    levels: dict[int, list[SymbolNode]] = defaultdict(list)
    for entity, node in nodes.items():
        levels[node.level].append(node)

    # Ensure root is in levels if pending
    if root.status == "pending" and root not in levels.get(LEVEL_MODULE, []):
        levels[LEVEL_MODULE].append(root)

    return ModuleTree(
        module_name=module_name,
        source_file=source_file,
        root=root,
        levels=dict(levels),
    )


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _read_file_source(source_file: str) -> str:
    """Read a source file, returning empty string on error."""
    try:
        return Path(source_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _parse_ast(source: str) -> ast.Module | None:
    """Parse source code into AST, returning None on error."""
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _find_ast_node(tree: ast.Module, kind: str, entity: str) -> ast.AST | None:
    """Find an AST node by kind and entity name."""
    if kind == "module":
        return tree

    if "#" in entity:
        class_name, method_name = entity.split("#", 1)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name == method_name:
                            return item
        return None

    for node in ast.iter_child_nodes(tree):
        if kind == "class" and isinstance(node, ast.ClassDef) and node.name == entity:
            return node
        if kind in ("function", "method") and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if node.name == entity:
                return node

    return None


def _get_node_source(source_lines: list[str], node: ast.AST, max_lines: int = 50) -> str:
    """Extract source lines for an AST node."""
    start = node.lineno - 1
    end = getattr(node, "end_lineno", start + 1)
    end = min(end, start + max_lines)
    return "\n".join(source_lines[start:end])


def _get_node_signature(source_lines: list[str], node: ast.AST) -> str:
    """Extract just the signature line(s) of a def/class node."""
    start = node.lineno - 1
    for i in range(start, min(start + 20, len(source_lines))):
        if source_lines[i].rstrip().endswith(":"):
            return "\n".join(source_lines[start : i + 1])
    return source_lines[start] if start < len(source_lines) else ""


def _get_summary_line(docstring: str) -> str:
    """Extract the first line (summary) from a docstring."""
    if not docstring:
        return ""
    return docstring.strip().split("\n")[0].strip()


def build_context(node: SymbolNode, tree: ModuleTree) -> str:
    """Build the LLM context for a symbol based on its level.

    Level 0 (functions/methods): source code of the symbol.
    Level 1 (classes): class structure + full docstrings of children.
    Level 2 (modules): top-of-file + summary lines of children.

    Args:
        node: The symbol node to build context for.
        tree: The module tree containing this node.

    Returns:
        Context string to pass to the LLM prompt.
    """
    source = _read_file_source(tree.source_file)
    if not source:
        return ""

    ast_tree = _parse_ast(source)
    if ast_tree is None:
        return ""

    source_lines = source.splitlines()

    if node.level == LEVEL_LEAF:
        return _build_leaf_context(node, ast_tree, source_lines)
    elif node.level == LEVEL_CLASS:
        return _build_class_context(node, ast_tree, source_lines)
    elif node.level == LEVEL_MODULE:
        return _build_module_context(node, ast_tree, source_lines)

    return ""


def _build_leaf_context(
    node: SymbolNode, ast_tree: ast.Module, source_lines: list[str]
) -> str:
    """Build context for a function or method (level 0)."""
    ast_node = _find_ast_node(ast_tree, node.kind, node.entity)
    if ast_node is None:
        return ""
    return _get_node_source(source_lines, ast_node, max_lines=50)


def _build_class_context(
    node: SymbolNode, ast_tree: ast.Module, source_lines: list[str]
) -> str:
    """Build context for a class (level 1)."""
    ast_node = _find_ast_node(ast_tree, "class", node.entity)
    if ast_node is None:
        return ""

    parts: list[str] = []

    # Class signature
    parts.append(_get_node_signature(source_lines, ast_node))

    # Collect class attributes
    if isinstance(ast_node, ast.ClassDef):
        for item in ast_node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                line_idx = item.lineno - 1
                if line_idx < len(source_lines):
                    parts.append(f"    {source_lines[line_idx].strip()}")
            elif isinstance(item, ast.Assign):
                line_idx = item.lineno - 1
                if line_idx < len(source_lines):
                    parts.append(f"    {source_lines[line_idx].strip()}")

        # __init__ source
        for item in ast_node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "__init__"
            ):
                init_source = _get_node_source(source_lines, item, max_lines=30)
                parts.append("")
                parts.append(init_source)
                break

    # Children docstrings
    if node.children:
        parts.append("")
        parts.append("# Methods:")
        for child in node.children:
            method_name = (
                child.entity.split("#", 1)[-1] if "#" in child.entity else child.entity
            )
            if child.docstring and child.status in ("updated", "skipped"):
                parts.append(f"    def {method_name}(...):")
                parts.append(f'        """{child.docstring}"""')
            else:
                child_ast = _find_ast_node(ast_tree, child.kind, child.entity)
                if child_ast is not None:
                    sig = _get_node_signature(source_lines, child_ast)
                    parts.append(f"    {sig.strip()}")
                    parts.append("        # [no documentation]")
                else:
                    parts.append(f"    def {method_name}(...):")
                    parts.append("        # [no documentation]")

    return "\n".join(parts)


def _build_module_context(
    node: SymbolNode, ast_tree: ast.Module, source_lines: list[str]
) -> str:
    """Build context for a module (level 2)."""
    parts: list[str] = []

    # Top of file (first 30 lines)
    top_lines = "\n".join(source_lines[:30])
    parts.append(top_lines)

    # Children summaries
    if node.children:
        parts.append("")
        parts.append("# Module components:")
        for child in node.children:
            if child.docstring and child.status in ("updated", "skipped"):
                summary = _get_summary_line(child.docstring)
                parts.append(f'- {child.kind} {child.entity}: "{summary}"')
            else:
                child_ast = _find_ast_node(ast_tree, child.kind, child.entity)
                if child_ast is not None:
                    sig = _get_node_signature(source_lines, child_ast).strip()
                    parts.append(f"- {child.kind} {child.entity}: {sig}")
                else:
                    parts.append(f"- {child.kind} {child.entity}")

    return "\n".join(parts)
