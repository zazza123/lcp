# MCP Server

## Overview

The MCP Server module exposes Python library documentation to AI agents via the [Model Context Protocol](https://modelcontextprotocol.io/).

The universal server (`lcp serve-all`) is the single implementation: agents call `resolve_library("package")` to load any pip-installed package on the fly, then `search` and `get_symbol` to explore it. Resolved manifests are cached as `.lcp.json.gz` files under `~/.lcp/cache/`. The single-manifest command (`lcp serve`) is deprecated and now wraps the same server, pre-loaded with the manifest.

## Key Features

- `lcp serve-all` command: single, always-on MCP server for any Python library
- Four-tool surface designed around a three-call workflow: `resolve_library` → `search` → `get_symbol` (+ `get_overview` for orientation)
- On-demand library resolution with three-tier fallback: local cache → live scan → remote registry
- Live scans run in a disposable child interpreter by default (crash isolation, no import-lock stalls) and can target a different virtualenv via `--scan-python`
- Ranked search with exact import lines in every hit; empty query browses deterministically
- Batch `get_symbol` with inline class-member summaries and exact return-type-to-class resolution
- Structured error dicts with stable shape and recovery hints on every failure path
- Byte-capped responses (`--max-response-bytes`) guarding against context blowouts
- `MultiLibraryIndex`: holds multiple libraries simultaneously; with several loaded, tools require an explicit `library` argument (no silent default)
- Usage guidance delivered through the MCP `instructions` field, reaching agents before any tool call

## Documents

- [Architecture](architecture.md) - Server structure, index design, error model, caps, tool inventory, and data flow

## CLI Commands

| Command | Purpose |
|---------|---------|
| `lcp serve-all` | Start the universal multi-library MCP server (recommended) |
| `lcp serve <manifest.lcp.json>` | Deprecated: starts the universal server pre-loaded with the manifest |

### `lcp serve-all` options

| Option | Default | Description |
|--------|---------|-------------|
| `--cache-dir PATH` | `~/.lcp/cache/` | Root directory for cached manifests |
| `--name TEXT` | `lcp-universal` | Server name for MCP identification |
| `--no-cache` | off | Disable reading from and writing to the local cache |
| `--registry TEXT` | *(none)* | Base URL of a remote LCP registry used as a final fallback when local scanning fails |
| `--expose TEXT` | all packages | Restrict `resolve_library` to these package names (repeatable) |
| `--preload TEXT` | *(none)* | Resolve these packages at startup (repeatable) |
| `--max-response-bytes INT` | `25000` | Byte budget for list-returning tool responses |
| `--scan-mode [subprocess\|inprocess]` | `subprocess` | Whether live scans run in a child interpreter or in the server process |
| `--scan-python TEXT` | server's interpreter | Interpreter whose environment live scans read |
| `--scan-timeout FLOAT` | `60.0` | Seconds before a subprocess scan is killed |

### Setup (one-time)

```bash
pip install lcp

# Claude Code
claude mcp add lcp -- lcp serve-all

# Cursor (.cursor/mcp.json) or Claude Desktop (claude_desktop_config.json)
# { "mcpServers": { "lcp": { "command": "lcp", "args": ["serve-all"] } } }
```

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `LCPIndex` | `src/lcp/mcp_server.py` | In-memory lookup index built from an `LCPDocument` |
| `MultiLibraryIndex` | `src/lcp/mcp_server.py` | Registry of loaded `LCPIndex` instances with per-library resolution source; enforces explicit-library disambiguation |
| `LCPServer` | `src/lcp/mcp_server.py` | Dataclass bundling the FastMCP instance, the index registry, and the raw tool callables |
| `resolve_library_document()` | `src/lcp/mcp_server.py` | Resolves a library via cache, live scan, or remote registry fetch |
| `scan_package_subprocess()` | `src/lcp/subprocess_scan.py` | Runs a live scan in a child interpreter and classifies failures as typed exceptions |
| `lcp.scanjson` | `src/lcp/scanjson.py` | Machine-mode scan entry point executed inside the scan interpreter (LCP JSON on stdout, structured errors on stderr, exit-code contract) |
| `_register_tools()` | `src/lcp/mcp_server.py` | Single registration path for the four tools, shared by all entry points |
| `create_universal_server()` | `src/lcp/mcp_server.py` | Constructs the universal `LCPServer` |
| `run_universal_server()` | `src/lcp/mcp_server.py` | Starts the universal server |
| `create_server()` / `run_server()` | `src/lcp/mcp_server.py` | Deprecated single-manifest wrappers over the universal server |
| CLI `serve-all` command | `src/lcp/cli.py` | Thin wrapper that calls `run_universal_server()` |
| CLI `serve` command | `src/lcp/cli.py` | Deprecated thin wrapper that warns and calls `run_server()` |

## Related Documentation

- [Architecture](architecture.md) - Detailed tool inventory, error model, and index design
- [AI DocGen](../ai_docgen/index.md) - Generates the docstrings that make manifests more useful to the MCP server

---
**Last Updated:** July 2026
**Status:** Implemented
