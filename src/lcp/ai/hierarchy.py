"""Hierarchy builder for bottom-up documentation generation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


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
