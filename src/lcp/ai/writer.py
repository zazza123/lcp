"""Docstring injection into Python source files via AST."""

from __future__ import annotations

import ast
from pathlib import Path


def _find_node(tree: ast.Module, kind: str, entity: str) -> ast.AST | None:
    """Find the AST node corresponding to a symbol.

    Args:
        tree: Parsed AST module.
        kind: Symbol kind (module, class, function, method, attribute).
        entity: Entity name. Methods use '#' separator (e.g. 'Class#method').

    Returns:
        The matching AST node, or None if not found.
    """
    if kind == "module":
        return tree

    # Handle methods: Class#method
    if "#" in entity:
        class_name, method_name = entity.split("#", 1)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name == method_name:
                            return item
        return None

    # Handle top-level classes and functions
    for node in ast.iter_child_nodes(tree):
        if kind == "class" and isinstance(node, ast.ClassDef) and node.name == entity:
            return node
        if kind == "function" and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if node.name == entity:
                return node

    return None


def _has_docstring(node: ast.AST) -> bool:
    """Check if a node already has a docstring."""
    if isinstance(node, ast.Module):
        body = node.body
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        body = node.body
    else:
        return False

    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return True
    return False


def _get_insertion_point(
    node: ast.AST, source_lines: list[str]
) -> tuple[int, str]:
    """Get the insertion point for a docstring.

    Returns:
        Tuple of (line_index, indentation) where line_index is the 0-based
        line index to insert before, and indentation is the whitespace prefix.
    """
    if isinstance(node, ast.Module):
        # Module docstring goes at line 0
        # Check for shebang or encoding declarations
        insert_line = 0
        for i, line in enumerate(source_lines):
            stripped = line.strip()
            if stripped.startswith("#!") or stripped.startswith("# -*-"):
                insert_line = i + 1
            else:
                break
        return insert_line, ""

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Insert after the def/class line
        # The body starts at the first statement in the body
        if node.body:
            body_node = node.body[0]
            body_line = body_node.lineno - 1  # 0-based

            # Determine indentation from the body
            if body_line < len(source_lines):
                line_text = source_lines[body_line]
                indent = line_text[: len(line_text) - len(line_text.lstrip())]
            else:
                # Fallback: use node indentation + 4 spaces
                node_line = source_lines[node.lineno - 1]
                base_indent = node_line[: len(node_line) - len(node_line.lstrip())]
                indent = base_indent + "    "

            # Find the line right after the def/class statement
            # Handle multi-line signatures by looking at the decorator end line
            # or the colon position
            def_end_line = node.lineno - 1  # 0-based, the line with def/class
            # Check for multi-line def: find the line with the colon
            for i in range(def_end_line, min(def_end_line + 50, len(source_lines))):
                if source_lines[i].rstrip().endswith(":"):
                    def_end_line = i
                    break

            return def_end_line + 1, indent

    # Fallback
    return node.lineno, "    "


def _format_docstring(content: str, indent: str) -> str:
    """Format a docstring with triple quotes and indentation.

    Args:
        content: Raw docstring text (without triple quotes).
        indent: Indentation to apply.

    Returns:
        Formatted docstring with triple quotes and proper indentation.
    """
    lines = content.strip().split("\n")

    if len(lines) == 1:
        return f'{indent}"""{lines[0]}"""\n'

    # Multi-line docstring
    result = [f'{indent}"""{lines[0]}']
    for line in lines[1:]:
        if line.strip():
            result.append(f"{indent}{line}")
        else:
            result.append("")
    result.append(f'{indent}"""')

    return "\n".join(result) + "\n"


def inject_docstring(
    file_path: str, kind: str, entity: str, docstring: str
) -> bool:
    """Inject a docstring into a Python source file.

    Args:
        file_path: Path to the Python source file.
        kind: Symbol kind (module, class, function, method).
        entity: Entity name (e.g. 'MyClass', 'my_func', 'MyClass#method').
        docstring: The docstring text to inject (without triple quotes).

    Returns:
        True if the docstring was injected, False otherwise.
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines(keepends=True)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    node = _find_node(tree, kind, entity)
    if node is None:
        return False

    if _has_docstring(node):
        return False

    insert_line, indent = _get_insertion_point(node, [line.rstrip("\n\r") for line in source_lines])

    formatted = _format_docstring(docstring, indent)

    source_lines.insert(insert_line, formatted)

    path.write_text("".join(source_lines), encoding="utf-8")
    return True


def inject_docstrings_batch(
    file_path: str, injections: list[tuple[str, str, str]]
) -> list[bool]:
    """Inject multiple docstrings into the same file.

    Processes injections bottom-up (by descending line number) to avoid
    line offset issues from earlier insertions.

    Args:
        file_path: Path to the Python source file.
        injections: List of (kind, entity, docstring) tuples.

    Returns:
        List of booleans indicating success for each injection.
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [False] * len(injections)

    source_lines_raw = source.splitlines(keepends=True)
    source_lines_stripped = [line.rstrip("\n\r") for line in source_lines_raw]

    # Collect all valid injections with their insertion points
    pending = []
    results = [False] * len(injections)

    for idx, (kind, entity, docstring) in enumerate(injections):
        node = _find_node(tree, kind, entity)
        if node is None:
            continue
        if _has_docstring(node):
            continue

        insert_line, indent = _get_insertion_point(node, source_lines_stripped)
        formatted = _format_docstring(docstring, indent)
        pending.append((insert_line, idx, formatted))

    if not pending:
        return results

    # Sort by line number descending (bottom-up) for safe insertion
    pending.sort(key=lambda x: x[0], reverse=True)

    for insert_line, idx, formatted in pending:
        source_lines_raw.insert(insert_line, formatted)
        results[idx] = True

    path.write_text("".join(source_lines_raw), encoding="utf-8")
    return results
