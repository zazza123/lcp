# Claude Code plugin

The LCP Claude Code plugin turns any pip-installed Python library into live, queryable documentation inside your agent session. Install it once from the Claude Code marketplace and Claude automatically knows how to look up functions, classes, signatures, and docstrings for every library your project uses — without pre-built manifests, without per-project setup.

## What's included

When you install the plugin, Claude Code gets:

| Component | What it does |
|-----------|-------------|
| **MCP Server** | `lcp serve-all` starts automatically on every session and exposes your Python environment's libraries as browsable MCP tools |
| **`lcp-universal` skill** | Teaches Claude to call `resolve_library()` before writing code that uses a third-party library — proactive, not reactive |
| **`lcp-usage` skill** | Guides Claude on when and how to use LCP tools for library research |
| **`/lcp:resolve <pkg>`** | Slash command: resolve a library and get a summary of its public API |
| **`/lcp:scan <pkg>`** | Slash command: scan a package and produce a structured module and symbol overview |
| **Library explorer subagent** | A read-only Claude Haiku subagent for deep API research; runs independently so it doesn't consume your session's context |
| **Session hook** | Warns immediately at session start if `lcp` is not on `PATH`, instead of failing silently |
| **Registry support** | Optional `userConfig.registries` field for connecting to a private or team registry with pre-built manifests |

## Installation

### Prerequisites

- [Claude Code](https://claude.com/claude-code) installed
- `lcp` installed and available on your `PATH`:

```bash
pip install lcp
lcp --version
```

### Install from the marketplace

The plugin is published to the Claude Code marketplace under the `zazza123/lcp` namespace. Add the marketplace and install the plugin in two commands:

```
/plugin marketplace add zazza123/lcp
/plugin install lcp@lcp
```

That's it. Claude Code reads the plugin manifest, registers the MCP server, the skills, the commands, and the subagent. Open a new session and the server starts automatically.

!!! tip "Configuring a private registry at install time"
    During `plugin install`, you can set the `registries` option to point to a team registry:

    ```
    /plugin install lcp@lcp registries="https://your-registry.example.com"
    ```

### Alternative: local directory

If you have a local clone of the repository and want to load the plugin directly — for example when developing the plugin itself:

```bash
claude --plugin-dir /path/to/lcp/plugin/lcp
```

### Alternative: MCP-only (Cursor, Claude Desktop)

If you only need the MCP server without skills, hooks, or commands, add the server directly to your client's MCP config:

=== "Claude Code"

    ```bash
    claude mcp add lcp -- lcp serve-all
    ```

=== "Cursor / Claude Desktop"

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

## How it works

Once the plugin is active, the typical interaction looks like this:

```
User: "Set up FastAPI routes with proper dependency injection"

Claude:
  1. resolve_library("fastapi")                → scanned + cached
  2. list_modules()                            → finds fastapi.routing
  3. list_symbols(module="fastapi.routing")    → finds APIRouter, Depends
  4. get_symbol("fastapi.routing:APIRouter")   → full signature
  5. get_class_members("fastapi:Depends")      → understands dependencies
  6. Writes accurate, idiomatic code
```

The `lcp-universal` skill drives this flow automatically: whenever Claude detects that a task involves an external Python library, it calls `resolve_library("package")` first. The MCP server checks `~/.lcp/cache/` for a cached manifest; if none is found, it scans the pip-installed package on the fly and caches the result. Subsequent calls to the same library in the same session are instant.

The skills, commands, and subagent are guidance and convenience layers on top of the MCP server — they don't change what the server does, they change how Claude uses it.

## Configuring a private registry

By default, `lcp serve-all` resolves libraries from your local Python environment. If your team maintains a private registry with pre-built manifests for internal packages, configure the plugin to use it:

```bash
claude plugin config lcp registries "https://your-registry.example.com"
```

Multiple registries can be listed comma-separated; only the first is used as the active registry. The option maps to the `--registry` flag passed to `lcp serve-all` at startup.

## Troubleshooting

!!! warning "`lcp` command not found"
    Both the session hook and the startup wrapper check for `lcp` on `PATH`. Install it with `pip install lcp` and confirm `lcp --version` works in the same shell environment Claude Code uses.

!!! warning "MCP server not starting"
    Run `lcp serve-all` manually in your terminal to check for errors. On Unix systems, `bin/serve.sh` must be executable — run `chmod +x plugin/lcp/bin/serve.sh` if needed. Confirm Claude Code shows `lcp` in its active MCP servers list.

!!! warning "Library not resolving"
    The package must be pip-installed in the Python environment `lcp` uses. Run `lcp scan <package>` manually to verify the library can be introspected. If scanning succeeds but the MCP tool still fails, restart the Claude Code session to reload the server.

## See also

- [MCP Server](mcp-server.md) — the underlying server the plugin wraps
- [CLI reference](../cli.md) — `serve-all` flags and all other commands
- [Publishing](publishing.md) — contributing manifests to the central registry
