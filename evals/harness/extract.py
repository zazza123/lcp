"""Extract code blocks from agent output and library-symbol usage from code."""

import ast
import re
from dataclasses import dataclass, field

_CODE_BLOCK_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code_blocks(text: str) -> list[str]:
    """Return the contents of fenced code blocks (```python / ```py / bare)."""
    return [m.strip() for m in _CODE_BLOCK_RE.findall(text)]


@dataclass
class CodeUsage:
    dotted_paths: set[str] = field(default_factory=set)
    method_names: set[str] = field(default_factory=set)


def _attr_chain(node: ast.AST) -> list[str] | None:
    """Return ['pl', 'read_csv'] for pl.read_csv; None if not rooted at a Name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def extract_usage(code: str, library: str) -> CodeUsage:
    """Collect usage of `library` symbols in `code`.

    dotted_paths: attribute chains rooted at an import of the library,
    canonicalized to the real module path. method_names: attribute names on
    any non-module receiver (variables, call results), excluding chains
    rooted at an import of a *different* module, plus method names defined
    in classes that subclass a library class (framework override pattern).
    """
    tree = ast.parse(code)
    root = library.split(".")[0]
    aliases: dict[str, str] = {}  # local name -> canonical dotted prefix
    from_import_names: set[str] = set()  # names bound via `from library import ...`
    foreign_names: set[str] = set()  # local names bound by imports of OTHER modules

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] != root:
                    foreign_names.add(a.asname or a.name.split(".")[0])
                    continue
                if a.asname:
                    aliases[a.asname] = a.name
                else:
                    aliases[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or not node.module:
                continue
            if node.module.split(".")[0] == root:
                for a in node.names:
                    name = a.asname or a.name
                    aliases[name] = f"{node.module}.{a.name}"
                    from_import_names.add(name)
            else:
                for a in node.names:
                    foreign_names.add(a.asname or a.name)

    usage = CodeUsage()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain = _attr_chain(node)
            if chain is not None and chain[0] in aliases:
                usage.dotted_paths.add(".".join([aliases[chain[0]], *chain[1:]]))
            elif chain is not None and chain[0] in foreign_names:
                pass  # attribute access on another module; not a method call
            else:
                usage.method_names.add(node.attr)
        elif isinstance(node, ast.Name) and node.id in from_import_names:
            usage.dotted_paths.add(aliases[node.id])
        elif isinstance(node, ast.ClassDef):
            bases = (_attr_chain(b) for b in node.bases)
            if any(c is not None and c[0] in aliases for c in bases):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        usage.method_names.add(item.name)
    return usage
