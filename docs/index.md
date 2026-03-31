# LCP Python SDK - Documentation

## Overview

Documentation for the LCP Python SDK, a tool for generating Library Context Protocol files from Python packages by introspecting installed modules.

## Table of Contents

### Features

- [Manifest Generation](manifest/index.md) - Scans an installed Python package and produces a structured `.lcp.json` manifest via a scan → generate → validate pipeline
- [MCP Server](mcp_server/index.md) - Serves LCP manifests to AI agents via the Model Context Protocol, with guided exploration tools
- [Coverage](coverage/index.md) - Measures documentation completeness across a package; produces JSON and Markdown reports
- [Version Diff](diff/index.md) - Compares two LCP manifests to detect removed symbols and generate deprecation entries
- [Registry Publish](publish/index.md) - Submits LCP manifests to the registry via GitHub Pull Request with structured metadata
- [AI Documentation Generation](ai_docgen/index.md) - Automatic docstring generation using LLM providers, with hierarchical bottom-up processing
- [Claude Code Plugin](plugin/index.md) - Packages `lcp serve-all` as a Claude Code plugin with skills, commands, hooks, and a library-explorer subagent

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Scanner | `src/lcp/scanner.py` | Introspects Python packages into `ScannedModule` |
| Generator | `src/lcp/generator.py` | Converts scanned data to LCP format |
| Validator | `src/lcp/validator.py` | Validates output against JSON schema |
| MCP Server | `src/lcp/mcp_server.py` | Serves LCP manifests to AI agents via MCP |
| Coverage | `src/lcp/coverage.py` | Analyzes documentation completeness |
| Diff | `src/lcp/diff.py` | Compares LCP versions and detects deprecations |
| Publish | `src/lcp/publish.py` | Submits manifests to the registry via GitHub PR |
| AI DocGen | `src/lcp/ai/` | Generates missing docstrings using LLMs |
| Claude Code Plugin | `plugin/lcp/` | Packages the MCP server as a Claude Code plugin with skills, hooks, commands, and subagent |

---
**Last Updated:** March 2026
**Status:** Implemented
