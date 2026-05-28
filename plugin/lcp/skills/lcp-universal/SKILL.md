---
name: lcp-universal
description: This skill should be used when the user writes code that imports or uses a Python library, asks to "look up the X API", "check how to use X", "what's the signature of X.Y", "resolve library X", or encounters import errors or API misuse. Activates the lcp MCP server's resolve_library workflow for on-demand introspection of any pip-installed package.
---

# LCP Universal — On-demand Python Library Documentation

This plugin starts the `lcp serve-all` MCP server automatically. It can scan any pip-installed Python library and expose its full public API — every function, class, method, signature, and docstring — as browsable MCP tools.

## Quick start

If a library name is provided via arguments, resolve it immediately:

```
resolve_library("$ARGUMENTS")
```

Then follow the workflow below to explore it.

## Step 1: Resolve the library

Before using any other tool, load the library:

```
resolve_library("requests")    # → scanned, cached, ready
resolve_library("fastapi")     # → scanned, cached, ready
resolve_library("numpy")       # → scanned, cached, ready
```

Returns `{ status: "loaded", symbol_count: ..., source: "cache"|"scan" }`.

The last resolved library becomes the **implicit default** for all other tools — no need to pass `library=` on every call.

## Step 2: Explore the API

```
get_manifest()                                # name, version, language
list_modules()                                # all module paths
list_symbols(module="fastapi.routing", kind="class")
get_symbol("fastapi.routing:APIRouter")       # full signature + params
get_class_members("fastapi.routing:APIRouter")
explore_return_type("fastapi.routing:APIRouter#add_api_route")
search_symbols(query="middleware")            # text search (expensive)
get_suggestions("handle HTTP routing")        # task-based suggestions
```

## Working with multiple libraries

All tools accept an optional `library=` parameter:

```
resolve_library("httpx")
resolve_library("aiohttp")
list_symbols(library="httpx", kind="class")
list_symbols(library="aiohttp", kind="function")
list_libraries()                              # see all loaded libraries
```

## Recommended workflow

1. `resolve_library("pkg")` — load the library (checks cache first)
2. `get_manifest()` — confirm name/version
3. `list_modules()` — browse module structure
4. `list_symbols(module="...", kind="...")` — browse candidates
5. `get_symbol("module:Symbol")` — **always verify signature before writing code**
6. `get_class_members("module:Class")` or `explore_return_type("module:func")` — understand returned objects

## Tool reference

| Tool | Purpose |
|------|---------|
| `resolve_library(name)` | **Call first** — load a library (cache or live scan) |
| `list_libraries()` | List all currently loaded libraries |
| `get_usage_guide()` | Full workflow and common mistakes |
| `get_manifest(library?)` | Library name, version, language |
| `list_modules(library?)` | All module paths |
| `list_symbols(library?, module?, kind?)` | Browse symbols (filter by module and/or kind) |
| `get_symbol(id, library?)` | Full signature, params, return type — **verify before every API call** |
| `get_class_members(id, library?)` | All methods/attributes of a class |
| `explore_return_type(id, library?)` | Discover available methods on a returned object |
| `search_symbols(query, library?)` | Text search across all symbols (expensive) |
| `get_suggestions(task, library?)` | Task-based module and symbol recommendations |

## Key rules

- **Never assume** a parameter name, type, or default — always call `get_symbol` first.
- **Never invent** methods on returned objects — always call `explore_return_type` or `get_class_members`.
- Prefer `list_modules` → `list_symbols` over `search_symbols` (search scans everything, is slower).
- Private packages work too — any pip-installed package can be scanned.
