---
name: lcp-serve-all
description: Use when writing or debugging code that depends on any pip-installed Python library. The `lcp serve-all` universal MCP server can resolve any library on-the-fly — call `resolve_library("package_name")` first, then use the standard LCP tools to explore its API. Triggers on any task involving third-party library usage, import errors, or API misuse when no per-library LCP server is connected.
---

# LCP Universal Server (serve-all)

The `lcp serve-all` command starts a universal MCP server that can resolve **any pip-installed Python library** on demand — no pre-built manifest required.

## Setup (one-time)

```bash
pip install lcp

# Claude Code
claude mcp add lcp -- lcp serve-all

# Cursor (.cursor/mcp.json)
# { "mcpServers": { "lcp": { "command": "lcp", "args": ["serve-all"] } } }

# Claude Desktop (claude_desktop_config.json)
# { "mcpServers": { "lcp": { "command": "lcp", "args": ["serve-all"] } } }
```

## Recommended Workflow

### Step 1: Resolve the library

Before using any other tool, load the library you need:

```
resolve_library("requests")     # scan + cache → loaded
resolve_library("fastapi")      # scan + cache → loaded
```

The result includes `name`, `version`, `symbol_count`, and `source` (`"cache"` or `"scan"`).
The last resolved library becomes the **implicit default** for all other tools.

### Step 2: Explore

```
get_manifest()                             # confirm library name & version
list_modules()                             # browse module structure
list_symbols(module="fastapi.routing", kind="class")  # browse symbols
get_symbol("fastapi.routing:APIRouter")    # full signature & params
get_class_members("fastapi.routing:APIRouter")  # all methods/attributes
explore_return_type("fastapi.routing:APIRouter#add_api_route")
```

### Step 3: Work with multiple libraries

All tools accept an optional `library=` parameter:

```
resolve_library("requests")
resolve_library("httpx")
list_modules(library="requests")
list_symbols(library="httpx", kind="class")
list_libraries()   # see all loaded libraries
```

## When to Use

### 1. During Development

Before writing code against a library:

1. Call `resolve_library("package_name")` to load its documentation.
2. Call `get_manifest()` to confirm the version.
3. Call `list_modules()` to find the relevant area.
4. Call `list_symbols(module=..., kind=...)` to browse candidates.
5. Call `get_symbol(symbol_id)` to verify the **exact** signature, required parameters, types, and return type **before** writing any call.
6. Call `get_class_members(class_id)` or `explore_return_type(symbol_id)` to understand returned objects.

**Key rule:** never assume a parameter name, type, or default — always verify with `get_symbol` first.

### 2. After a Build or Type-Check Failure

When a compilation, import, or type-check error references a library symbol:

1. Call `resolve_library("package_name")` if not already loaded.
2. Call `search_symbols(query=...)` or `list_symbols(module=...)` to find the correct symbol name.
3. Call `get_symbol(symbol_id)` to get the correct signature and fix the call site.

## Tool Quick Reference

| Tool | Use For |
|------|---------|
| `resolve_library(name)` | **Call first** — loads a library from cache or live scan |
| `list_libraries()` | List all currently loaded libraries |
| `get_usage_guide()` | Full recommended workflow and common mistakes |
| `get_manifest(library?)` | Confirm library name, version, language |
| `list_modules(library?)` | Browse all module paths |
| `list_symbols(library?, module?, kind?)` | Browse symbols filtered by module and/or kind |
| `get_symbol(symbol_id, library?)` | **Full signature, params, return type** — call before every API usage |
| `get_class_members(class_id, library?)` | All methods/attributes of a class |
| `explore_return_type(symbol_id, library?)` | Discover what you can do with a returned object |
| `search_symbols(query, library?)` | Text search (expensive — prefer browsing first) |
| `get_suggestions(task, library?)` | Describe your task to get starting-point recommendations |

## Cache Behaviour

Manifests are cached under `~/.lcp/cache/{package}/{version}.lcp.json`.
The cache is invalidated automatically when the installed package version changes.
Use `lcp serve-all --no-cache` to force fresh scans on every call.

## Common Mistakes to Avoid

- Forgetting to call `resolve_library` before using other tools.
- Starting with `search_symbols` instead of browsing (`list_modules` → `list_symbols`).
- Using a symbol without calling `get_symbol` first — leads to wrong parameter names or missing required args.
- Inventing methods on returned objects — always call `explore_return_type` or `get_class_members` to check.
