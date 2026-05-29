# MCP Server

## Overview

The MCP Server module exposes Python library documentation to AI agents via the [Model Context Protocol](https://modelcontextprotocol.io/).

Two modes are supported:

- **Single-manifest server** (`lcp serve`) – given a pre-built `.lcp.json` or `.lcp.json.gz` file, starts a FastMCP server for one library.
- **Universal server** (`lcp serve-all`) – no manifest required; agents call `resolve_library("package")` to load any pip-installed package on the fly. Resolved manifests are cached as `.lcp.json.gz` files under `~/.lcp/cache/`.

## Key Features

- `lcp serve-all` command: single, always-on MCP server for any Python library
- On-demand library resolution with three-tier fallback: local cache → live scan → remote registry
- Optional remote registry fallback via `--registry` for packages that cannot be scanned locally
- `MultiLibraryIndex`: holds multiple libraries simultaneously; agents work across libraries in one session
- In-memory `LCPIndex` for fast symbol lookups by module, kind, and class membership
- Eleven tools covering the full exploration workflow from library loading to fine-grained symbol detail
- Guided workflow embedded in `get_usage_guide` to help agents avoid expensive operations
- All standard tools accept an optional `library` parameter for explicit multi-library targeting

## Documents

- [Architecture](architecture.md) - Server structure, index design, tool inventory, and data flow

## CLI Commands

| Command | Purpose |
|---------|---------|
| `lcp serve-all` | Start the universal multi-library MCP server (recommended) |
| `lcp serve <manifest.lcp.json>` | Start a single-library server from a pre-built manifest |

### `lcp serve-all` options

| Option | Default | Description |
|--------|---------|-------------|
| `--cache-dir PATH` | `~/.lcp/cache/` | Root directory for cached manifests |
| `--name TEXT` | `lcp-universal` | Server name for MCP identification |
| `--no-cache` | off | Disable reading from and writing to the local cache |
| `--registry TEXT` | *(none)* | Base URL of a remote LCP registry used as a final fallback when local scanning fails |

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
| `MultiLibraryIndex` | `src/lcp/mcp_server.py` | Holds multiple `LCPIndex` instances; tracks the default library |
| `resolve_library_document()` | `src/lcp/mcp_server.py` | Resolves a library via cache, live scan, or remote registry fetch |
| `create_server()` | `src/lcp/mcp_server.py` | Constructs a single-library `FastMCP` instance |
| `run_server()` | `src/lcp/mcp_server.py` | Loads a manifest and starts the single-library server |
| `create_universal_server()` | `src/lcp/mcp_server.py` | Constructs the multi-library `FastMCP` instance |
| `run_universal_server()` | `src/lcp/mcp_server.py` | Starts the universal server |
| CLI `serve` command | `src/lcp/cli.py` | Thin wrapper that calls `run_server()` |
| CLI `serve-all` command | `src/lcp/cli.py` | Thin wrapper that calls `run_universal_server()` |

## Related Documentation

- [Architecture](architecture.md) - Detailed tool inventory and index design
- [AI DocGen](../ai_docgen/index.md) - Generates the docstrings that make manifests more useful to the MCP server

---
**Last Updated:** March 2026
**Status:** Implemented
