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

### Option A — Claude Code CLI (recommended)

```bash
# From the lcp repository root
claude mcp add lcp -- lcp serve-all
```

Or install this plugin directory directly:

```bash
claude plugin install /path/to/lcp/plugin/lcp
```

### Option B — Manual MCP configuration

Add to your `.claude/settings.json` or project-level MCP config:

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

### Option C — Cursor / Claude Desktop

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
