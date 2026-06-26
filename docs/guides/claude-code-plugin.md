# Claude Code plugin

The LCP Claude Code plugin turns any pip-installed Python library into live, queryable documentation inside your agent session. Install it once from the Claude Code marketplace and Claude automatically knows how to look up functions, classes, signatures, and docstrings for every library your project uses — including private packages installed in your project's virtualenv.

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
| **Session hook** | Auto-generates `.lcp.json` for the active project when absent, seeding it from `settings.json` `pluginConfigs` values |
| **Registry support** | `registries` field in `.lcp.json` for connecting to a private or team registry with pre-built manifests |

## Installation

### Prerequisites

- [Claude Code](https://claude.com/claude-code) installed
- `lcp` installed in your Python environment (see [Install `lcp`](#install-lcp) below)

### Install `lcp`

`lcp` introspects packages by importing them in-process, so it must run inside the **same Python environment** as your project's dependencies. For live introspection of project packages, install it in your project virtualenv:

```bash
# Inside your project virtualenv
uv pip install lcp      # recommended with uv
pip install lcp         # plain pip
```

The plugin auto-detects `.venv` under your project root — no extra configuration needed for the common case.

For a global install (public libraries via the registry; does not see project-specific packages unless also globally installed):

```bash
pipx install lcp        # recommended
uv tool install lcp
```

### Install from the marketplace

The plugin is published to the Claude Code marketplace under the `zazza123/lcp` namespace. Add the marketplace and install the plugin in two commands:

```
/plugin marketplace add zazza123/lcp
/plugin install lcp@lcp
```

That's it. Claude Code reads the plugin manifest, registers the MCP server, the skills, the commands, and the subagent. Open a new session and the server starts automatically.

!!! tip "Setting options at install time"
    During `/plugin install`, Claude Code prompts you to enter `userConfig` values such as
    `registries`. These are stored in `settings.json` under `pluginConfigs.lcp@lcp.options`
    and delivered to the hook at the next full session start, which seeds them into
    `.lcp.json` when the file does not yet exist.

    To change an option later, edit `.lcp.json` directly (preferred), or edit
    `pluginConfigs.lcp@lcp.options` in `settings.json` directly. To re-trigger the install
    prompt, run `claude plugin disable lcp && claude plugin enable lcp`.

### Alternative: local directory

If you have a local clone of the repository and want to load the plugin directly — for example when developing the plugin itself:

```bash
claude --plugin-dir /path/to/lcp/plugin/lcp
```

!!! tip "Reloading during development"
    Use `/reload-plugins` to hot-reload skills, agents, hooks, and MCP after edits.
    Run `claude plugin validate ./plugin/lcp` to validate the manifest.
    Changes to `userConfig` values require a **full restart** to be re-delivered to the hook
    and propagated into `.lcp.json`.

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

## Configuration: `.lcp.json`

The plugin reads a `.lcp.json` file to determine how to launch `lcp` for the current project. The `SessionStart` hook **auto-generates** this file from your `pluginConfigs` settings when it is absent; after that, edit the file directly.

### Locations

The wrapper checks these paths in order, using the first that exists:

1. `${CLAUDE_PROJECT_DIR}/.lcp.json` — per-project (safe to check in to the repository)
2. `~/.lcp/config.json` — global fallback

### Schema

All fields are optional:

```jsonc
{
  "command":    "/path/to/lcp",            // explicit lcp binary
  "python":     "/path/to/python",         // interpreter → `python -m lcp`
  "registries": ["https://..."],           // registry URLs → lcp serve-all --registry
  "expose":     ["fastapi", "pydantic"],   // allow-list; omitted/empty = expose all
  "preload":    ["fastapi"]                // packages resolved at server startup
}
```

`command` and `python` are mutually exclusive launch hints; `command` wins if both are set.

### Private registries

To use a team registry with pre-built manifests for internal packages, add its URL to `registries` in `.lcp.json`:

```jsonc
{
  "registries": ["https://raw.githubusercontent.com/your-org/lcp-registry/main"]
}
```

Only the first URL in the list is used as the active registry. The value maps to the `--registry` flag passed to `lcp serve-all` at startup.

### `expose` and `preload`

These two fields are per-project settings in `.lcp.json` only — they are not available as `userConfig` options.

- **`expose`**: An allow-list that restricts which packages `resolve_library` can expose. Useful in large monorepos to avoid noise. Omit or leave empty to expose all packages.
- **`preload`**: A list of packages that `lcp` scans at server startup so they are ready immediately, without waiting for the first `resolve_library` call.

```jsonc
{
  "expose":  ["mypackage", "fastapi"],
  "preload": ["mypackage"]
}
```

## Launcher resolution order

The wrapper probes each candidate with `--version` before use; the first that succeeds is used to run `lcp serve-all`:

1. `.lcp.json` → `command` (explicit binary path)
2. `.lcp.json` → `python` → `python -m lcp`
3. Auto-detected project venv under `${CLAUDE_PROJECT_DIR}`: `.venv/bin/lcp`, `.venv/bin/python -m lcp`, `venv/bin/lcp`, `venv/bin/python -m lcp`
4. Active virtualenv via `$VIRTUAL_ENV`: `$VIRTUAL_ENV/bin/lcp`, `$VIRTUAL_ENV/bin/python -m lcp`
5. `uv run --project <dir> --with lcp lcp` if `uv` is present — ephemeral, layers `lcp` onto the project env so it can see project packages without a permanent install
6. Global fallback: `lcp` on `PATH` → `uvx lcp` → `pipx run lcp`

If none of the above resolve, the plugin emits an actionable error explaining how to install or configure `lcp` — never a bare `-32000`.

!!! tip "Why the project venv matters"
    `lcp` introspects packages by importing them in-process via `importlib`. It can only
    document libraries installed in the **same environment it runs in**. Steps 1–4 specifically
    target your project's environment so private dependencies are reachable. Step 5 (global)
    is a fallback that covers publicly registered packages only.

## Troubleshooting

!!! warning "`lcp` not found or MCP server returns `-32000`"
    The wrapper tries six resolution strategies (see [Launcher resolution order](#launcher-resolution-order) above).
    The most common fixes:

    **Install `lcp` in your project virtualenv** (recommended for live introspection):
    ```bash
    uv pip install lcp   # or: pip install lcp
    ```
    The plugin auto-detects `.venv` — no extra config needed.

    **Or pin an explicit path in `.lcp.json`**:
    ```jsonc
    { "command": "/path/to/venv/bin/lcp" }
    ```
    or
    ```jsonc
    { "python": "/path/to/venv/bin/python" }
    ```

    **Or install globally** (public packages and registry-backed manifests only):
    ```bash
    pipx install lcp
    ```

!!! warning "MCP server not starting"
    Run `lcp serve-all` manually in your terminal to check for errors. On Unix systems, `bin/serve.sh` must be executable — run `chmod +x plugin/lcp/bin/serve.sh` if needed. Confirm Claude Code shows `lcp` in its active MCP servers list.

!!! warning "Library not resolving"
    The package must be installed in the Python environment `lcp` is running in. Run `lcp scan <package>` manually to verify the library can be introspected. If scanning succeeds but the MCP tool still fails, restart the Claude Code session to reload the server.

## See also

- [MCP Server](mcp-server.md) — the underlying server the plugin wraps
- [CLI reference](../cli.md) — `serve-all` flags and all other commands
- [Publishing](publishing.md) — contributing manifests to the central registry
