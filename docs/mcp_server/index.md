# MCP Server

## Overview

The MCP Server module exposes a compiled LCP manifest to AI agents via the [Model Context Protocol](https://modelcontextprotocol.io/). Given a `.lcp.json` file, it starts a FastMCP server that lets any MCP-compatible AI agent browse, search, and retrieve detailed symbol information from the library — without reading source code.

## Key Features

- Serves a pre-built LCP manifest over the MCP protocol
- In-memory `LCPIndex` for fast symbol lookups by module, kind, and class membership
- Nine tools covering the full exploration workflow: from usage guidance to fine-grained symbol detail
- Guided workflow embedded in `get_usage_guide` to help agents avoid expensive operations
- Task-aware entry point via `get_suggestions` that maps a natural-language task description to relevant modules and symbols

## Documents

- [Architecture](architecture.md) - Server structure, index design, tool inventory, and data flow

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `LCPIndex` | `src/lcp/mcp_server.py` | In-memory lookup index built from an `LCPDocument` |
| `create_server()` | `src/lcp/mcp_server.py` | Constructs and returns a configured `FastMCP` instance |
| `run_server()` | `src/lcp/mcp_server.py` | Loads the manifest and starts the MCP server |
| `load_lcp_document()` | `src/lcp/mcp_server.py` | Reads and validates a `.lcp.json` file into an `LCPDocument` |
| CLI `serve` command | `src/lcp/cli.py` | Thin wrapper that calls `run_server()` |

## Related Documentation

- [Architecture](architecture.md) - Detailed tool inventory and index design
- [AI DocGen](../ai_docgen/index.md) - Generates the docstrings that make manifests more useful to the MCP server

---
**Last Updated:** February 2026
**Status:** Implemented
