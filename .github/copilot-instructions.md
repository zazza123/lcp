# Copilot Instructions for lcp

Python SDK for generating [Library Context Protocol (LCP)](https://github.com/zazza123/lcp) files from Python packages by introspecting installed modules using `inspect` and `ast`.

## Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Install with AI extras (OpenAI + Anthropic)
pip install -e ".[ai,dev]"

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
lcp coverage <package> -o coverage.json  # Documentation coverage report
lcp docgen <coverage.json> --provider openai  # AI docstring generation
```

## Architecture

The SDK follows a three-stage pipeline: **scan → generate → validate**

### Pipeline Flow

1. **Scanner** (`scanner.py`) - Introspects Python packages using `inspect` module, producing `ScannedModule` with `ScannedSymbol` objects
2. **Generator** (`generator.py`) - Converts scanned data to LCP format, producing Pydantic `LCPDocument`
3. **Validator** (`validator.py`) - Validates output against the JSON schema in `schema.json`
4. **AI DocGen** (`ai/`) - Optional module (`lcp[ai]`) that generates missing docstrings using LLM providers

### Key Data Structures

- `ScannedSymbol` / `ScannedModule` (dataclasses in scanner.py) - Internal representation of Python symbols
- `Symbol` / `LCPDocument` (Pydantic models in models.py) - LCP v1 specification models
- `DocGenAgent` / `DocGenConfig` / `DocGenResult` (in ai/) - AI docstring generation orchestrator and results
- Symbol IDs use format: `module_path:entity_path` (e.g., `json:loads`, `pathlib:Path#resolve`)

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `__init__.py` | Public API exports and main `scan()` function |
| `cli.py` | Click-based CLI (`scan`, `validate`, `serve`, `coverage`, `docgen` commands) |
| `models.py` | Pydantic models matching LCP v1 spec |
| `scanner.py` | Python introspection logic |
| `generator.py` | Scanned data → LCP conversion |
| `validator.py` | JSON Schema validation |
| `mcp_server.py` | MCP server for AI agent integration |
| `coverage.py` | Documentation coverage analysis |
| `ai/` | Optional AI module for docstring generation (`lcp[ai]`) |
| `ai/agent.py` | `DocGenAgent` orchestrator: loads coverage, generates docstrings, writes files |
| `ai/models.py` | Dataclasses: `TokenUsage`, `LLMResponse`, `DocGenConfig`, `SymbolResult`, `DocGenResult` |
| `ai/provider.py` | `LLMProvider` abstract base class for LLM connectors |
| `ai/connectors/` | `OpenAIProvider` and `AnthropicProvider` implementations |
| `ai/prompts.py` | System and user prompt templates for docstring generation |
| `ai/writer.py` | AST-based docstring injection into Python source files |

## Conventions

- Use `src/` layout with `lcp` package
- Tests use a `sample_module.py` fixture (in `tests/`) for testing introspection
- Private symbols (prefixed with `_`) are excluded by default; controlled via `include_private` flag
- Public dunder methods (`__init__`, `__call__`, etc.) are considered public API
- Pydantic models use `ConfigDict(extra="allow")` for forward compatibility with LCP spec extensions
- The `ai` module is optional; its dependencies (`openai`, `anthropic`) are lazy-imported with clear error messages
- LLM connectors extend `LLMProvider` ABC; new providers only need `generate()` and `name`
- The AI writer injects docstrings bottom-up (by descending line number) to avoid line offset issues in batch operations
