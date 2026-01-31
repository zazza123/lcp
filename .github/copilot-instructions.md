# Copilot Instructions for lcp-python-sdk

Python SDK for generating [Library Context Protocol (LCP)](https://lcp.dev) files from Python packages by introspecting installed modules using `inspect` and `ast`.

## Commands

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
lcp-python scan <package> -o output.lcp.json
lcp-python validate <file.lcp.json>
```

## Architecture

The SDK follows a three-stage pipeline: **scan → generate → validate**

### Pipeline Flow

1. **Scanner** (`scanner.py`) - Introspects Python packages using `inspect` module, producing `ScannedModule` with `ScannedSymbol` objects
2. **Generator** (`generator.py`) - Converts scanned data to LCP format, producing Pydantic `LCPDocument`
3. **Validator** (`validator.py`) - Validates output against the JSON schema in `schema.json`

### Key Data Structures

- `ScannedSymbol` / `ScannedModule` (dataclasses in scanner.py) - Internal representation of Python symbols
- `Symbol` / `LCPDocument` (Pydantic models in models.py) - LCP v1 specification models
- Symbol IDs use format: `module_path:entity_path` (e.g., `json:loads`, `pathlib:Path#resolve`)

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `__init__.py` | Public API exports and main `scan()` function |
| `cli.py` | Click-based CLI (`scan` and `validate` commands) |
| `models.py` | Pydantic models matching LCP v1 spec |
| `scanner.py` | Python introspection logic |
| `generator.py` | Scanned data → LCP conversion |
| `validator.py` | JSON Schema validation |

## Conventions

- Use `src/` layout with `lcp_python_sdk` package
- Tests use a `sample_module.py` fixture (in `tests/`) for testing introspection
- Private symbols (prefixed with `_`) are excluded by default; controlled via `include_private` flag
- Public dunder methods (`__init__`, `__call__`, etc.) are considered public API
- Pydantic models use `ConfigDict(extra="allow")` for forward compatibility with LCP spec extensions
