# MCP server

The `lcp` package ships an [MCP](https://modelcontextprotocol.io/) server that exposes one or more LCP manifests as tools an AI agent can call. This guide shows how to start the server and connect a client.

## What is MCP?

Model Context Protocol (MCP) is an open standard for connecting AI assistants to external data sources and tools. It defines a uniform wire format so that any MCP-compatible client — Claude Code, Cursor, GitHub Copilot CLI, and others — can consume data from any MCP server without client-specific integration work. LCP provides the structured library data; MCP provides the communication channel. Together they allow an agent to query accurate, version-specific API information on demand rather than relying on training-time knowledge.

## How it works

When `lcp serve` or `lcp serve-all` starts, it builds an in-memory `LCPIndex` from one or more LCP manifests. The index organises every symbol by module path, kind, and class membership so that tool calls can be answered without scanning the whole document each time.

The server communicates over **stdio** using the MCP protocol. The client process spawns `lcp serve …` as a subprocess and exchanges JSON-RPC messages with it. Each MCP tool the server registers appears as a callable function in the agent's tool list. The agent calls these tools to browse library structure (`list_modules`, `list_symbols`), fetch individual symbol details (`get_symbol`), or search by text (`search_symbols`).

`lcp serve` targets a single pre-built manifest and exposes a fixed set of exploration tools for that one library. `lcp serve-all` is the universal variant: it starts with no manifests loaded and exposes two additional tools — `resolve_library` and `list_libraries` — that allow the agent to load any pip-installed (or registry-available) library at runtime and then query it using the same exploration tools.

## Single-library mode

Serve a single manifest:

```bash
lcp serve requests.lcp.json
```

The server runs over stdio and exits when the client disconnects. All exploration tools operate on the manifest passed on the command line. Use `--name` to override the server name shown to the client (default: `lcp-{library-name}`).

### Client configuration

=== "Claude Code"

    Add to your project's `.mcp.json` or to user-level `~/.claude/mcp.json`:

    ```json
    {
      "mcpServers": {
        "lcp-requests": {
          "command": "lcp",
          "args": ["serve", "/absolute/path/to/requests.lcp.json"]
        }
      }
    }
    ```

    Or use the CLI shortcut:

    ```bash
    claude mcp add lcp-requests -- lcp serve /absolute/path/to/requests.lcp.json
    ```

=== "Cursor / generic MCP client"

    Most clients accept the same `mcpServers` shape. Point `command` to the `lcp` executable and pass `serve <manifest>` as the `args` array. Consult your client's documentation for the config file location.

## Universal mode (registry-backed)

For a single server that resolves any requested library, use universal mode:

```bash
lcp serve-all
```

By default the server caches resolved manifests under `~/.lcp/cache/`. Pass `--cache-dir` to redirect the cache, or `--registry` to add a remote registry that is tried when a package is not installed locally:

```bash
lcp serve-all --cache-dir /tmp/lcp-cache \
    --registry https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main
```

Resolution happens in this order for each `resolve_library` call: local cache → live scan of the pip-installed package → registry fetch. See [CLI reference](../cli.md) for all flags.

### Client configuration

=== "Claude Code"

    ```bash
    # Add the universal server (resolves any library on demand)
    claude mcp add lcp-universal -- lcp serve-all

    # With registry fallback
    claude mcp add lcp-universal -- lcp serve-all \
        --registry https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main
    ```

    Or edit `.mcp.json` manually:

    ```json
    {
      "mcpServers": {
        "lcp-universal": {
          "command": "lcp",
          "args": ["serve-all"]
        }
      }
    }
    ```

=== "Cursor / generic MCP client"

    ```json
    {
      "mcpServers": {
        "lcp-universal": {
          "command": "lcp",
          "args": ["serve-all"]
        }
      }
    }
    ```

## Tools exposed by the server

The table below lists every tool registered by the server. Tools marked **universal only** are available only when running `lcp serve-all`; all others are available in both modes. In universal mode, tools that operate on a library accept an optional `library` parameter to target a specific loaded library; when omitted, the most recently resolved library is used as the default.

| Tool | Mode | Description |
|---|---|---|
| `resolve_library(name)` | Universal only | Scan or fetch a library by pip package name, cache the result, and make it available for exploration. Returns manifest summary and symbol count. |
| `list_libraries()` | Universal only | List all libraries currently loaded in the server, with version and symbol counts. |
| `get_usage_guide()` | Both | Return the recommended exploration workflow, cost-optimisation tips, and common mistakes to avoid. Call this first. |
| `get_manifest()` | Both | Return library metadata: name, version, language, schema version, and compatibility info. |
| `list_modules()` | Both | Return a sorted list of all module paths in the library. Use this to orient before browsing symbols. |
| `list_symbols(module, kind)` | Both | Return symbol summaries, optionally filtered by module path and/or kind (`function`, `class`, `method`, `attribute`, `module`, `constant`). |
| `get_symbol(symbol_id)` | Both | Return the full record for one symbol: signatures, parameter types, return type, semantics, and usage hints. Always call this before writing a call site. |
| `search_symbols(query, fields)` | Both | Case-insensitive text search across symbol names, summaries, and descriptions. Prefer `list_modules` + `list_symbols` when the target area is known. |
| `get_class_members(class_id)` | Both | Return all methods and attributes belonging to a class. |
| `explore_return_type(symbol_id)` | Both | Analyse the return type of a function or method and suggest related classes to explore with `get_class_members`. |
| `get_suggestions(task_description)` | Both | Match a plain-language task description against module names and symbol summaries, and return suggested starting points. |

### Recommended workflow

The `get_usage_guide` tool encodes the intended call order explicitly, but the short version is:

1. `resolve_library` (universal mode only) — load the library.
2. `list_modules` — find the relevant area of the library.
3. `list_symbols(module=…, kind=…)` — browse candidates.
4. `get_symbol` — verify the exact signature before writing code.
5. `get_class_members` / `explore_return_type` — understand return objects.

## Programmatic usage

You can create and start the server from Python directly:

```python
from lcp.mcp_server import create_server, create_universal_server, run_server

# Single-library mode
server = create_server(
    "path/to/requests.lcp.json",
    name="lcp-requests",          # optional; defaults to lcp-{library-name}
)
server.run()

# Universal mode
server = create_universal_server(
    name="lcp-universal",
    cache_dir="~/.lcp/cache",     # optional
    registry_url="https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main",  # optional
)
server.run()

# Convenience wrapper (single-library)
run_server("path/to/requests.lcp.json")
```

`create_server` and `create_universal_server` both return a `FastMCP` instance. You can register additional tools on it before calling `.run()`.

## See also

- [Claude Code plugin](claude-code-plugin.md) — packaged version of `lcp serve-all` for Claude Code.
- [CLI reference](../cli.md) — all flags for `serve` and `serve-all`.
