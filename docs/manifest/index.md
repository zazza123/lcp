# Manifest Generation

## Overview

The core purpose of the SDK is to generate an **LCP manifest** — a `.lcp.json` file that describes a Python package's public API in a structured, machine-readable format. The manifest contains every public symbol (functions, classes, methods, attributes, modules, constants) with their signatures, docstrings, and source locations.

The pipeline runs in three stages: **scan → generate → validate**.

```mermaid
flowchart LR
    A["Installed Python package"] --> B["scan_package()"]
    B --> C["ScannedModule"]
    C --> D["generate_lcp()"]
    D --> E["LCPDocument"]
    E --> F["validate_or_raise()"]
    F --> G[".lcp.json file"]
```

See [Architecture](architecture.md) for a deep dive into each stage.

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `scan()` | `src/lcp/__init__.py` | Main SDK entry point: runs all three stages in one call |
| `scan_package()` | `src/lcp/scanner.py` | Introspects an installed package into `ScannedModule` |
| `generate_lcp()` | `src/lcp/generator.py` | Converts `ScannedModule` to `LCPDocument` |
| `validate_or_raise()` | `src/lcp/validator.py` | Validates `LCPDocument` against the JSON Schema |
| `LCPDocument` | `src/lcp/models.py` | Pydantic model for the complete LCP document |
| `Symbol` | `src/lcp/models.py` | Pydantic model for a single documented symbol |
| `schema.json` | `src/lcp/schema.json` | LCP v1 JSON Schema used for validation |

## CLI Usage

### Generating a manifest

The `lcp scan` command accepts a package name and writes the manifest to a file or stdout. Validation against the LCP schema runs by default and can be disabled with `--no-validate`. A coverage report can be written alongside the manifest in the same pass via `--coverage`, reusing the scan result without reimporting the package.

| Flag | Default | Purpose |
|------|---------|---------|
| `<package>` | *(required)* | Name of an installed Python package |
| `-o` / `--output` | stdout | Output `.lcp.json` file path |
| `--include-private` | off | Include symbols whose names start with `_` |
| `--no-recursive` | off | Only scan the top-level module |
| `--validate / --no-validate` | on | Validate against LCP schema before writing |
| `--indent` | `2` | JSON indentation level |
| `--coverage` | off | Also write a coverage report to this path |

### Validating an existing manifest

The `lcp validate` command reads a `.lcp.json` file, checks it against the LCP v1 schema, and prints each violation. It exits with code 0 on success and 1 on failure.

## Python API

`scan()` in `src/lcp/__init__.py` is the main SDK entry point. It accepts a package name plus `include_private`, `recursive`, and `validate` flags, runs all three pipeline stages, and returns an `LCPDocument`. `LCPValidationError` is raised if validation is enabled and the output does not conform to the schema.

For cases where the stages need to run independently — for example, to produce both a manifest and a coverage report from a single scan — `scan_package()`, `generate_lcp()`, and `validate_or_raise()` are all available as separate public functions. The `LCPDocument` returned by `generate_lcp()` can be serialized with `to_json()` or written directly to disk with `to_file()`.

The validator is also available standalone: `validate_file()` checks a file on disk, `validate_document()` checks an `LCPDocument` in memory, and `is_valid()` provides a boolean shorthand for both.

## Symbol ID Format

Every symbol in the manifest has a unique string ID following the format `module_path:entity_path`:

| Example ID | Refers to |
|------------|-----------|
| `json:` | The `json` module itself |
| `json:loads` | Top-level function `loads` in `json` |
| `pathlib:Path` | Class `Path` in `pathlib` |
| `pathlib:Path#resolve` | Method `resolve` on `pathlib.Path` |
| `http.client:HTTPResponse#read` | Method `read` on `http.client.HTTPResponse` |

These IDs are the keys of the `symbols` dict in the LCP document and are the same identifiers used by the [MCP Server](../mcp_server/index.md) tools.

## What Gets Scanned

By default the scanner includes:

- All **public** symbols — names that do not start with `_`
- **Public dunder methods** that form part of the Python data model: `__init__`, `__call__`, `__iter__`, `__getitem__`, `__setitem__`, `__delitem__`, `__len__`, `__contains__`, `__str__`, `__repr__`, `__eq__`, `__hash__`, `__bool__`, and arithmetic/comparison operators
- If a module defines `__all__`, only those names are included (re-exports from other modules are otherwise skipped)
- **Class members**: methods and `property` descriptors belonging to the scanned package (members inherited from external packages are excluded; members inherited from classes within the same package are kept)
- **Constants**: `UPPER_CASE` names bound to simple immutable types

With `--include-private`, names starting with `_` (except `__dunder__`) are also included.

## Integration with Other Features

| Feature | How it connects |
|---------|----------------|
| [Coverage](../coverage/index.md) | `generate_coverage_from_scanned()` reuses the `ScannedModule` to avoid a second scan |
| [MCP Server](../mcp_server/index.md) | `lcp serve` loads the `.lcp.json` file and exposes it as MCP tools |
| [AI DocGen](../ai_docgen/index.md) | The coverage JSON produced alongside the manifest feeds the docstring generation pipeline |

## Related Documentation

- [Architecture](architecture.md) - Scanner internals, generator logic, LCP models, and validator

---
**Last Updated:** February 2026
**Status:** Implemented
