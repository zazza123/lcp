# Manifest Generation - Architecture

## Overview

This document covers the internals of the three-stage scan → generate → validate pipeline that produces an LCP manifest.

---

## Stage 1: Scanner

**Module:** `src/lcp/scanner.py`

The scanner uses Python's `inspect` module to introspect a live, imported package. It never parses source files directly for symbol discovery — it relies on the runtime object graph. Source files are accessed only to retrieve file paths and line number ranges via `inspect.getfile()` / `inspect.getsourcelines()`.

### Internal Data Structures

| Dataclass | Purpose |
|-----------|---------|
| `ScannedParam` | One parameter: name, type hint string, default value, kind (`positional`, `keyword_only`, `rest`, …) |
| `ScannedSignature` | Callable signature: list of `ScannedParam`, return type string, `is_async` flag |
| `ScannedSymbol` | One symbol: name, qualified name, module path, kind, summary/description, signature, members list, source location |
| `ScannedModule` | Top-level result: package name, version, flat list of all `ScannedSymbol` objects |

Class members (methods, properties) are stored inline inside the parent `ScannedSymbol.members` list. The generator later flattens this into the top-level `symbols` dict.

### Entry Points

- `scan_package(package_name, include_private, recursive)` — top-level function; imports the package, calls `scan_module()` on the root module, then iterates over submodules if `recursive=True`
- `scan_module(module, include_private, _visited)` — scans one `ModuleType`; uses a `_visited` set of object IDs to avoid processing the same module twice (handles circular imports)

### Submodule Discovery

`_iter_submodules()` uses `pkgutil.iter_modules()` for standard packages. It also handles namespace packages (directories without `__init__.py`) by iterating the package's `__path__` entries directly and trying to import any subdirectory that is a valid Python identifier.

Modules that fail to import are silently skipped.

### Public Symbol Rules

`_is_public(name, include_private)` controls what names are emitted:

1. If `include_private=True`, all names pass.
2. Names in the **public dunders allowlist** always pass (e.g. `__init__`, `__call__`, operators). See [index.md](index.md#what-gets-scanned) for the full list.
3. All other names starting with `_` are excluded.

When a module defines `__all__`, that set takes precedence: only names listed there are scanned (after applying the public-name check). Re-exported symbols — where `obj.__module__` differs from the current module's name — are also skipped to avoid documenting the same symbol in multiple places.

### Docstring Parsing

`_parse_docstring()` splits a raw docstring into:
- **summary** — the first paragraph (consecutive non-empty lines joined with a space)
- **description** — everything after the first blank line, stripped

Both fields may be `None` if no docstring exists.

### Type Hint Resolution

`_type_to_string()` converts a runtime type hint to a readable string:
- Uses `typing.get_origin()` / `typing.get_args()` for generics (`List[str]`, `Optional[int]`, `Union[…]`)
- Collapses `Union[X, None]` to `Optional[X]`
- Falls back to `__name__` or `str()` for plain types

`get_type_hints()` is preferred over `inspect.Parameter.annotation` because it resolves string annotations (`from __future__ import annotations`).

---

## Stage 2: Generator

**Module:** `src/lcp/generator.py`

The generator converts the `ScannedModule` tree into an `LCPDocument`. All logic is pure transformation — no I/O, no imports.

### Symbol ID Construction

`_build_symbol_id(scanned)` produces `"{module_path}:{entity_path}"`:
- Module symbols have an empty `qualified_name`, producing `"json:"`.
- Functions and classes use their plain name: `"json:loads"`, `"pathlib:Path"`.
- Methods use `Class#method` notation in `qualified_name`: `"pathlib:Path#resolve"`.

### Symbol Conversion

`_convert_symbol(scanned)` maps each `ScannedSymbol` to a `(symbol_id, Symbol)` pair:

1. **Semantics**: `summary` from the parsed docstring, or a fallback `"{kind} {name}"` string; `description` if present.
2. **Signatures**: constructed only for `function`, `method`, and `class` kinds. The class signature is the `__init__` signature captured by the scanner.
3. **Kind mapping**: scanner strings (`"function"`, `"class"`, …) → `SymbolKind` enum values.

### Class Member Flattening

`generate_lcp()` iterates `scanned_module.symbols` (the flat list including class symbols). For each class symbol it also iterates `scanned.members` and converts each member independently, adding them as top-level entries in the `symbols` dict under their `Class#method` IDs. Members do not appear nested inside the class entry in the output.

### Detailed Index

For symbols that have source location data (`source_file` and `source_lines`), `_build_detailed_index_entry()` creates a `DetailedIndexEntry` with an `Artifact` pointing to the file path and `[start_line, end_line]`. These entries are collected in `detailed_index` and included in the final document.

### Manifest Header

The manifest is populated with:
- `schema_version`: `"1.0"`
- `library.name` / `library.version` from `ScannedModule`
- `library.language`: `"python"` (hardcoded)
- `distribution`: `"pypi"`
- `generation.tool`: `"lcp"`, `generation.date`: current UTC timestamp

---

## Stage 3: Validator

**Module:** `src/lcp/validator.py`

The validator checks a completed `LCPDocument` against the bundled `schema.json` using `jsonschema` (Draft 2020-12).

### Validation Functions

| Function | Input | Output |
|----------|-------|--------|
| `validate_document(doc)` | `LCPDocument` | `list[str]` of error messages |
| `validate_dict(data)` | `dict` | `list[str]` of error messages |
| `validate_file(path)` | file path | `list[str]` of error messages |
| `is_valid(doc)` | `LCPDocument` or `dict` | `bool` |
| `validate_or_raise(doc)` | `LCPDocument` or `dict` | raises `LCPValidationError` |

`LCPValidationError` collects all errors and formats the first ten in its message. It is raised by `scan()` when `validate=True` (the default).

Each error message includes a dot-separated JSON path prefix (e.g. `symbols.json:loads.semantics`) pointing to the offending field.

---

## LCP Document Model

**Module:** `src/lcp/models.py`

All models use `ConfigDict(extra="allow")`, which means the SDK round-trips unknown fields transparently and remains forward-compatible with future LCP spec extensions.

### Document Structure

`LCPDocument` in `src/lcp/models.py` is the root model. It contains a `manifest` field of type `Manifest`, a `symbols` dict keyed by symbol ID, an optional `deprecations` dict, and an optional `detailed_index` dict.

`Manifest` holds the library name, version, and language via a nested `Library` model, plus `schema_version`, `distribution`, `symbol_resolution`, optional `compatibility` (Python version range and supported platforms), and `generation` metadata (tool name, version, UTC date).

Each `Symbol` in the `symbols` dict has a `kind` (`SymbolKind` enum), a `module` path, an optional list of `Signature` objects, and a required `semantics` field of type `Semantics`. `Semantics` holds the `summary` (required), an optional `description`, and optional `examples`. A `Signature` carries an `async` flag, an optional list of `Param` objects, an optional return type (`TypeRef` or string), and an optional list of `RaisesEntry` objects. Each `Param` records its name, type, `required` flag, default value, `variadic` flag, and `kind` (`ParamKind` enum).

The `detailed_index` dict maps symbol IDs to `DetailedIndexEntry` objects, each containing an `Artifact` with the source file path and a `[start_line, end_line]` pair.

### Serialization

`LCPDocument.to_dict()` calls `model_dump(mode="json", by_alias=True, exclude_none=True)`. The `by_alias=True` is needed because `Signature.async_` is stored internally as `async_` (to avoid the Python keyword) but serialized as `"async"` via a Pydantic `Field(alias="async")`.

---

## Related Documentation

- [Manifest Overview](index.md) - CLI usage, Python API, symbol IDs
- [Coverage](../coverage/index.md) - Uses the same `ScannedModule` to analyze doc completeness
- [MCP Server](../mcp_server/index.md) - Loads the `.lcp.json` output and exposes it over MCP

---
**Last Updated:** February 2026
**Status:** Implemented
