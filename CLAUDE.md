# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python SDK for generating [Library Context Protocol (LCP)](https://lcp.dev) files from Python packages by introspecting installed modules using `inspect` and `ast`.

## Development Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_scanner.py

# Run a single test class or function
pytest tests/test_scanner.py::TestScanClass
pytest tests/test_scanner.py::TestScanClass::test_scan_class

# Run with verbose output
pytest -v

# CLI usage (after installation)
lcp scan <package> -o output.lcp.json
lcp validate <file.lcp.json>
lcp serve <manifest.lcp.json>  # Start MCP server
```

## Architecture

The SDK follows a three-stage pipeline: **scan → generate → validate**

### Pipeline Flow

1. **Scanner** (`src/lcp/scanner.py`) - Introspects Python packages using `inspect` module, producing `ScannedModule` with `ScannedSymbol` dataclasses
2. **Generator** (`src/lcp/generator.py`) - Converts scanned data to LCP format, producing Pydantic `LCPDocument`
3. **Validator** (`src/lcp/validator.py`) - Validates output against the JSON schema in `schema.json`
4. **MCP Server** (`src/lcp/mcp_server.py`) - FastMCP-based server exposing LCP manifests to AI agents

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `__init__.py` | Public API exports and main `scan()` function |
| `cli.py` | Click-based CLI (`scan`, `validate`, `serve` commands) |
| `models.py` | Pydantic models matching LCP v1 spec |
| `scanner.py` | Python introspection logic |
| `generator.py` | Scanned data → LCP conversion |
| `validator.py` | JSON Schema validation |
| `mcp_server.py` | MCP server for AI agent integration |

### Key Data Structures

- `ScannedSymbol` / `ScannedModule` (dataclasses in scanner.py) - Internal representation of Python symbols
- `Symbol` / `LCPDocument` (Pydantic models in models.py) - LCP v1 specification models
- `LCPIndex` (in mcp_server.py) - In-memory index for fast symbol lookups

### Symbol ID Format

Symbol IDs use the format: `module_path:entity_path`
- Functions/classes: `json:loads`, `pathlib:Path`
- Class members use `#` separator: `pathlib:Path#resolve`, `pathlib:Path#exists`

## Conventions

- Use `src/` layout with `lcp` package
- Tests use `tests/sample_module.py` fixture for testing introspection
- Private symbols (prefixed with `_`) are excluded by default; controlled via `include_private` flag
- Public dunder methods (`__init__`, `__call__`, `__iter__`, `__getitem__`, operators) are considered public API
- Pydantic models use `ConfigDict(extra="allow")` for forward compatibility with LCP spec extensions
