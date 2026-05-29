# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python SDK for generating [Library Context Protocol (LCP)](https://github.com/zazza123/lcp) files from Python packages by introspecting installed modules using `inspect` and `ast`.

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
lcp docgen <coverage.json> --provider openai  # AI docstring generation
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
| `ai/agent.py` | `DocGenAgent` orchestrator: hierarchical mode via `run_sync()`/`run_async()` |
| `ai/models.py` | Dataclasses: `TokenUsage`, `LLMResponse`, `DocGenConfig`, `HierarchicalConfig`, `SymbolResult`, `DocGenResult` |
| `ai/hierarchy.py` | `SymbolNode`, `ModuleTree`, `build_hierarchy()`, `build_context()` for bottom-up processing |
| `ai/provider.py` | `LLMProvider` ABC with sync `generate()` and async `agenerate()` |
| `ai/connectors/openai.py` | `OpenAIProvider` with standard and reasoning mode, sync and async clients |
| `ai/connectors/anthropic.py` | `AnthropicProvider` with cache token tracking, sync and async clients |
| `ai/prompts.py` | System prompt and level-specific user prompts (L0, L1 class, L2 module) |
| `ai/writer.py` | AST-based docstring injection into Python source files |

### Claude Code Plugin

The plugin lives in `plugin/lcp/` and packages `lcp serve-all` as a Claude Code plugin:

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin manifest with `userConfig.registries` schema |
| `.mcp.json` | MCP server declaration; points to `bin/serve.sh` |
| `bin/serve.sh` | Startup wrapper: validates PATH, injects `--registry`, starts `lcp serve-all` |
| `hooks/hooks.json` | `SessionStart` hook: warns if `lcp` is not found |
| `skills/lcp-universal/SKILL.md` | Auto-invoked skill for proactive library resolution |
| `skills/lcp-usage/SKILL.md` | Auto-invoked skill for general LCP guidance |
| `commands/resolve.md` | `/lcp:resolve <pkg>` shortcut |
| `commands/scan.md` | `/lcp:scan <pkg>` shortcut |
| `agents/library-explorer.md` | Read-only haiku subagent for deep library research |

### Key Data Structures

- `ScannedSymbol` / `ScannedModule` (dataclasses in scanner.py) - Internal representation of Python symbols
- `Symbol` / `LCPDocument` (Pydantic models in models.py) - LCP v1 Specification models
- `LCPIndex` (in mcp_server.py) - In-memory index for fast symbol lookups
- `DocGenAgent` / `DocGenConfig` / `HierarchicalConfig` / `DocGenResult` (in ai/) - AI docstring generation orchestrator and results
- `SymbolNode` / `ModuleTree` (in ai/hierarchy.py) - Hierarchical symbol tree for bottom-up processing

### Symbol ID Format

Symbol IDs use the format: `module_path:entity_path`
- Functions/classes: `json:loads`, `pathlib:Path`
- Class members use `#` separator: `pathlib:Path#resolve`, `pathlib:Path#exists`

## Documentation

All documentation lives under `docs/`, the MkDocs source tree (`docs_dir: docs`) published to GitHub Pages via the `pages` workflow. It is organized into three areas with **different** conventions:

| Area | Location | Notes |
|------|----------|-------|
| Architecture | `docs/architecture/` | Conceptual/design docs for contributors; no code snippets, `snake_case`, `index.md` + `architecture.md` per topic |
| User-facing | `docs/guides/`, `docs/spec/`, `docs/{introduction,quickstart,cli}.md` | Task-oriented user docs; `kebab-case.md`, CLI/code examples expected |
| API Reference | `docs/api/` | Auto-generated by `mkdocstrings` from source docstrings — do not hand-write; improve the docstrings in `src/lcp/` instead |

**When writing or updating any documentation in this project, use the `lcp-writing-documentation` skill** — it is the authoritative guideline for these conventions, including which rules apply to each area and how to keep `mkdocs.yml` nav and `index.md` files in sync.

Build the site locally with `mkdocs build --strict` (install deps via `pip install -e ".[docs]"`).

## Conventions

- Use `src/` layout with `lcp` package
- Tests use `tests/sample_module.py` fixture for testing introspection
- Private symbols (prefixed with `_`) are excluded by default; controlled via `include_private` flag
- Public dunder methods (`__init__`, `__call__`, `__iter__`, `__getitem__`, operators) are considered public API
- Pydantic models use `ConfigDict(extra="allow")` for forward compatibility with LCP spec extensions
- The `ai` module is optional; its dependencies (`openai`, `anthropic`) are lazy-imported with clear error messages
- LLM connectors extend `LLMProvider` ABC; new providers need `generate()`, `agenerate()`, and `name`
- The AI writer injects docstrings bottom-up (by descending line number) to avoid line offset issues in batch operations
- AI DocGen uses hierarchical bottom-up processing: L0 (methods) → L1 (classes) → L2 (modules)
- `HierarchicalConfig` extends `DocGenConfig` with `max_workers` and `failure_threshold`
