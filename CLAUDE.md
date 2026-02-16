# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python SDK for generating [Library Context Protocol (LCP)](https://lcp.dev) files from Python packages by introspecting installed modules using `inspect` and `ast`.

## Development Commands

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
lcp docgen <coverage.json> --provider openai  # AI docstring generation (hierarchical)
lcp docgen <coverage.json> --flat             # AI docstring generation (legacy sequential)
lcp docgen <coverage.json> --workers 8        # Configure parallel LLM calls
```

## Architecture

The SDK follows a three-stage pipeline: **scan → generate → validate**

### Pipeline Flow

1. **Scanner** (`src/lcp/scanner.py`) - Introspects Python packages using `inspect` module, producing `ScannedModule` with `ScannedSymbol` dataclasses
2. **Generator** (`src/lcp/generator.py`) - Converts scanned data to LCP format, producing Pydantic `LCPDocument`
3. **Validator** (`src/lcp/validator.py`) - Validates output against the JSON schema in `schema.json`
4. **MCP Server** (`src/lcp/mcp_server.py`) - FastMCP-based server exposing LCP manifests to AI agents
5. **AI DocGen** (`src/lcp/ai/`) - Optional module (`lcp[ai]`) that generates missing docstrings using LLM providers

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
| `ai/agent.py` | `DocGenAgent` orchestrator: flat mode via `run()`, hierarchical mode via `run_sync()`/`run_async()` |
| `ai/models.py` | Dataclasses: `TokenUsage`, `LLMResponse`, `DocGenConfig`, `HierarchicalConfig`, `SymbolResult`, `DocGenResult` |
| `ai/hierarchy.py` | `SymbolNode`, `ModuleTree`, `build_hierarchy()`, `build_context()` for bottom-up processing |
| `ai/provider.py` | `LLMProvider` ABC with sync `generate()` and async `agenerate()` |
| `ai/connectors/openai.py` | `OpenAIProvider` with standard and reasoning mode, sync and async clients |
| `ai/connectors/anthropic.py` | `AnthropicProvider` with cache token tracking, sync and async clients |
| `ai/prompts.py` | System prompt and level-specific user prompts (L0 flat, L1 class, L2 module) |
| `ai/writer.py` | AST-based docstring injection into Python source files |

### Key Data Structures

- `ScannedSymbol` / `ScannedModule` (dataclasses in scanner.py) - Internal representation of Python symbols
- `Symbol` / `LCPDocument` (Pydantic models in models.py) - LCP v1 specification models
- `LCPIndex` (in mcp_server.py) - In-memory index for fast symbol lookups
- `DocGenAgent` / `DocGenConfig` / `HierarchicalConfig` / `DocGenResult` (in ai/) - AI docstring generation orchestrator and results
- `SymbolNode` / `ModuleTree` (in ai/hierarchy.py) - Hierarchical symbol tree for bottom-up processing

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
- The `ai` module is optional; its dependencies (`openai`, `anthropic`) are lazy-imported with clear error messages
- LLM connectors extend `LLMProvider` ABC; new providers need `generate()`, `agenerate()`, and `name`
- The AI writer injects docstrings bottom-up (by descending line number) to avoid line offset issues in batch operations
- AI DocGen uses hierarchical bottom-up processing by default: L0 (methods) → L1 (classes) → L2 (modules), with `--flat` for legacy sequential mode
- `HierarchicalConfig` extends `DocGenConfig` with `max_workers`, `flat_mode`, and `failure_threshold`
