# Claude Code Plugin

## Overview

The LCP Claude Code plugin integrates the Library Context Protocol into the Claude Code agent environment. Once installed, Claude Code automatically starts `lcp serve-all` as an MCP server, making any pip-installed Python library available on demand without pre-built manifests.

## Key Features

- Automatic MCP server startup when Claude Code opens a session
- On-demand library resolution via `resolve_library("package")` — any pip-installed package, no setup per library
- Two guided skills (`lcp-universal`, `lcp-usage`) that instruct the agent when and how to use LCP tools
- Quick command shortcuts (`/lcp:resolve`, `/lcp:scan`) for explicit library operations
- Dedicated `library-explorer` subagent for deep read-only API research
- `SessionStart` hook that warns if `lcp` is not found on PATH
- `userConfig.registries` field for configuring private or team registry URLs

## Documents

- [Architecture](architecture.md) - Plugin structure, MCP server startup flow, skills and hooks design

## Plugin Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Plugin manifest | `plugin/lcp/.claude-plugin/plugin.json` | Metadata, keywords, `userConfig` schema |
| MCP config | `plugin/lcp/.mcp.json` | Declares the MCP server entry pointing to the wrapper script |
| Wrapper script | `plugin/lcp/bin/serve.sh` | Validates `lcp` on PATH; injects `--registry` from `userConfig`; starts `lcp serve-all` |
| Hooks | `plugin/lcp/hooks/hooks.json` | `SessionStart` check for missing `lcp` installation |
| `lcp-universal` skill | `plugin/lcp/skills/lcp-universal/SKILL.md` | Teaches the agent to proactively call `resolve_library` before writing library code |
| `lcp-usage` skill | `plugin/lcp/skills/lcp-usage/SKILL.md` | General LCP usage guidance for development workflows |
| Resolve command | `plugin/lcp/commands/resolve.md` | `/lcp:resolve <package>` shortcut |
| Scan command | `plugin/lcp/commands/scan.md` | `/lcp:scan <package>` — scans and summarizes a library |
| Library explorer agent | `plugin/lcp/agents/library-explorer.md` | Read-only subagent (haiku model) for deep API research |

## Installation

```bash
# From the lcp repository root
claude plugin install plugin/lcp
```

After installation, Claude Code reads `plugin/lcp/.mcp.json` and starts the `lcp serve-all` server automatically. The `userConfig.registries` value can be set during `claude plugin install` or updated later via `claude plugin config`.

## Related Documentation

- [MCP Server](../mcp_server/index.md) — The underlying MCP server that powers the plugin
- [Registry Publish](../publish/index.md) — Publishing manifests to a registry used as plugin fallback

---
**Last Updated:** March 2026
**Status:** Implemented
