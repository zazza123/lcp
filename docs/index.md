# LCP Python SDK - Documentation

## Overview

Documentation for the LCP Python SDK, a tool for generating Library Context Protocol files from Python packages by introspecting installed modules.

## Table of Contents

### Features

- [AI Documentation Generation](ai_docgen/index.md) - Automatic docstring generation using LLM providers, with hierarchical bottom-up processing

### Internal

- [Design Documents](plans/) - Architecture and design plans for major features

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Scanner | `src/lcp/scanner.py` | Introspects Python packages into `ScannedModule` |
| Generator | `src/lcp/generator.py` | Converts scanned data to LCP format |
| Validator | `src/lcp/validator.py` | Validates output against JSON schema |
| MCP Server | `src/lcp/mcp_server.py` | Serves LCP manifests to AI agents via MCP |
| Coverage | `src/lcp/coverage.py` | Analyzes documentation completeness |
| AI DocGen | `src/lcp/ai/` | Generates missing docstrings using LLMs |

---
**Last Updated:** February 2026
**Status:** Implemented
