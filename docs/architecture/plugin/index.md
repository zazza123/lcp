# Claude Code Plugin

## Overview

The LCP Claude Code plugin integrates the Library Context Protocol into the Claude Code agent environment. Once installed, Claude Code automatically starts `lcp serve-all` as an MCP server, making any pip-installed Python library available on demand without pre-built manifests. The plugin is distributed through the Claude Code marketplace, which is the recommended installation path.

## Key Features

- **Marketplace distribution** — installable from `zazza123/lcp` via the Claude Code plugin marketplace in a single command
- Automatic MCP server startup when Claude Code opens a session, with a probed launcher-resolution chain (config → project venv → active venv → `uv`/PATH fallbacks)
- On-demand library resolution via `resolve_library("package")` — any pip-installed package, no setup per library
- Three guided skills (`lcp-universal`, `lcp-usage`, `lcp-configure`) that instruct the agent when and how to use LCP tools and how to repair the configuration
- Quick command shortcuts (`/lcp:resolve`, `/lcp:scan`, `/lcp:configure`) for explicit library and setup operations
- Dedicated `library-explorer` subagent for deep read-only API research
- `SessionStart` hook that seeds `.lcp-config.json` from install-time `userConfig` values when absent
- `PreToolUse` hook that holds the session's first unverified Python-file write with a reminder to consult LCP
- `userConfig` fields (`registries`, `lcpCommand`, `pythonPath`) for private registries and non-PATH installs

## Documents

- [Architecture](architecture.md) - Plugin structure, marketplace layout, MCP server startup flow, skills and hooks design

## Plugin Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Marketplace catalog | `.claude-plugin/marketplace.json` | Registers the repository as a Claude Code marketplace; lists available plugins and their source paths |
| Plugin manifest | `plugin/lcp/.claude-plugin/plugin.json` | Plugin metadata, keywords, `userConfig` schema; read by Claude Code during `plugin install` |
| MCP config | `plugin/lcp/.mcp.json` | Declares the MCP server entry pointing to the wrapper script |
| Wrapper script | `plugin/lcp/bin/serve.sh` | Probes launcher candidates with `--version`, builds `lcp serve-all` args from `.lcp-config.json`, starts the server |
| Hook declarations | `plugin/lcp/hooks/hooks.json` | Declares the `SessionStart` and `PreToolUse` hooks |
| Config seeding hook | `plugin/lcp/hooks/generate-config.sh` | `SessionStart`: generates `.lcp-config.json` from `userConfig` values when absent |
| Verification reminder hook | `plugin/lcp/hooks/verify_reminder.py` | `PreToolUse`: holds the first Python-file write until LCP was consulted (once per session) |
| `lcp-universal` skill | `plugin/lcp/skills/lcp-universal/SKILL.md` | Teaches the agent to proactively call `resolve_library` before writing library code |
| `lcp-usage` skill | `plugin/lcp/skills/lcp-usage/SKILL.md` | General LCP usage guidance for development workflows |
| `lcp-configure` skill | `plugin/lcp/skills/lcp-configure/SKILL.md` | Guided `.lcp-config.json` setup and repair; auto-triggers on server/resolve failures |
| Resolve command | `plugin/lcp/commands/resolve.md` | `/lcp:resolve <package>` shortcut |
| Scan command | `plugin/lcp/commands/scan.md` | `/lcp:scan <package>` — scans and summarises a library |
| Configure command | `plugin/lcp/commands/configure.md` | `/lcp:configure [symptom]` — runs the configuration wizard or targeted repair |
| Library explorer agent | `plugin/lcp/agents/library-explorer.md` | Read-only subagent (haiku model) for deep API research |

## Installation

### Marketplace (recommended)

The plugin is published to the Claude Code marketplace under the `zazza123/lcp` namespace. After adding the marketplace, installing the plugin registers the MCP server, skills, commands, hooks, and the `library-explorer` subagent in one step.

```
/plugin marketplace add zazza123/lcp
/plugin install lcp@lcp
```

### Local plugin directory (development)

When working on the plugin itself, the local directory can be loaded directly without going through the marketplace:

```bash
claude --plugin-dir /path/to/lcp/plugin/lcp
```

### MCP-only (other clients)

If only the MCP server is needed without skills, hooks, or commands (e.g. Cursor, Claude Desktop), the server can be wired directly via the client's MCP configuration pointing to `lcp serve-all`.

## Related Documentation

- [MCP Server](../mcp_server/index.md) — The underlying MCP server that powers the plugin
- [Registry Publish](../publish/index.md) — Publishing manifests to a registry used as plugin fallback

---
**Last Updated:** July 2026
**Status:** Implemented
