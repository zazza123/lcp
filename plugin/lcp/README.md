# LCP Plugin for Claude Code

Universal Python library documentation for AI coding agents via the [Library Context Protocol](https://github.com/zazza123/lcp).

## What it does

When you install this plugin, Claude Code automatically starts `lcp serve-all` as an MCP server. You (or the agent) can then call `resolve_library("package")` to load any pip-installed Python library on demand — no pre-built manifests required.

The server exposes every public function, class, method, signature, and docstring through browsable MCP tools. Manifests are cached under `~/.lcp/cache/` so subsequent loads are instant.

## Prerequisites

```bash
pip install lcp
```

The `lcp` command must be on your PATH. Verify with:

```bash
lcp --version
```

## Installation

### Option A — Claude Code marketplace (recommended)

Add the LCP marketplace and install the plugin:

```
/plugin marketplace add zazza123/lcp
/plugin install lcp@lcp
```

This installs the plugin, registers the MCP server, the skills, the commands (`/lcp:resolve`, `/lcp:scan`, `/lcp:configure`), and the `library-explorer` subagent in one step.

### Option B — Local plugin directory (development)

```bash
claude --plugin-dir /path/to/lcp/plugin/lcp
```

### Option C — Manual MCP configuration

If you only want the MCP server (no skills, hooks, or commands), add to your `.claude/settings.json` or project-level MCP config:

```json
{
  "mcpServers": {
    "lcp": {
      "command": "lcp",
      "args": ["serve-all"]
    }
  }
}
```

Or via the Claude Code CLI:

```bash
claude mcp add lcp -- lcp serve-all
```

### Option D — Cursor / Claude Desktop

Add to `.cursor/mcp.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lcp": {
      "command": "lcp",
      "args": ["serve-all"]
    }
  }
}
```

## Usage

Once connected, Claude Code uses the `lcp-universal` skill to guide the agent. The typical workflow:

```
# Agent interaction
User: "Set up FastAPI routes with proper dependency injection"

Agent:
  1. resolve_library("fastapi")                → scanned + cached
  2. list_modules()                            → finds fastapi.routing
  3. list_symbols(module="fastapi.routing")    → finds APIRouter, Depends
  4. get_symbol("fastapi.routing:APIRouter")   → full signature
  5. get_class_members("fastapi:Depends")      → understands dependencies
  6. Writes accurate code
```

## Options

```bash
lcp serve-all --cache-dir /custom/path    # custom cache directory
lcp serve-all --no-cache                  # disable caching
lcp serve-all --name my-lcp              # custom server name
```

## Skills included

| Skill | Trigger |
|-------|---------|
| `lcp-universal` | Any task involving Python library usage — auto-loads via `resolve_library` |
| `lcp-usage` | Detecting and using either the universal or a per-library LCP server |
| `lcp-configure` | Setting up or repairing `.lcp.json` — when the MCP server won't start, libraries don't resolve, or you want to set a registry / expose / preload |

## Configuration (`.lcp.json`)

Most setups need no configuration — the plugin auto-detects a runnable `lcp` and
uses the official registry. When it doesn't (e.g. `lcp` lives in a virtualenv off
your `PATH`, you run a private registry, or you want to restrict/warm specific
libraries), the server reads an optional `.lcp.json` (project root, falling back
to `~/.lcp/config.json`):

| Field | Effect |
|-------|--------|
| `command` | Full path to an `lcp` executable to launch the server with |
| `python` | Path to a Python interpreter that has `lcp` (run as `python -m lcp`) |
| `registries` | Registry base URLs — only the first is active; empty = official registry |
| `expose` | Whitelist of library names the server will serve; empty = any |
| `preload` | Libraries to resolve at startup for an instant first lookup |

Run **`/lcp:configure`** for a guided, step-by-step setup that fills this file in
and verifies the server actually starts — or pass it a symptom
(`/lcp:configure server won't start`) to jump straight to repair. The
`lcp-configure` skill also triggers automatically when the server fails to start
or a library won't resolve.

## How it works

```
claude code agent
      │
      ▼
resolve_library("requests")
      │
      ├─ 1. Check ~/.lcp/cache/requests/{version}.lcp.json
      ├─ 2. pip-installed scan via lcp.scan("requests")
      │       └─ save to cache
      └─ 3. Error if not installed
      │
      ▼
LCPIndex (in-memory)
      │
      ▼
list_symbols / get_symbol / get_class_members / ...
```

## Works with private packages

Any pip-installed package works — including private, internal, or unpublished packages:

```bash
pip install -e ./my-private-lib
```

Then in the agent session:

```
resolve_library("my-private-lib")
```

## More information

- [LCP repository](https://github.com/zazza123/lcp)
- [Architecture docs](../../docs/mcp_server/architecture.md)
