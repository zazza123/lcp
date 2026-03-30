---
name: lcp-usage
description: This skill should be used when the user writes code against a Python library, asks "how do I use X", encounters an AttributeError or ImportError on a library symbol, or asks "what parameters does X.Y take". Checks whether the universal lcp server (requires resolve_library first) or a per-library lcp-LIBNAME server is connected and uses it to discover correct APIs, signatures, and parameter types.
---

# LCP Usage

Use Library Context Protocol (LCP) MCP servers as a ground-truth reference for Python library APIs. LCP captures every public symbol, signature, and docstring; the MCP server exposes it through browsable, searchable tools so you never have to guess at an API.

## Detecting Available Servers

Two server types may be connected:

1. **Universal server** (`lcp` server from `lcp serve-all`) — resolves **any** pip-installed library on demand. Requires calling `resolve_library("package_name")` before using other tools.
2. **Per-library server** (naming convention `lcp-<library-name>`, e.g. `lcp-requests`, `lcp-numpy`) — pre-loaded with one library's manifest. No `resolve_library` call needed.

Detection order:
- If the `lcp` universal server is connected → call `resolve_library` first, then standard tools.
- If an `lcp-<name>` server is connected → use standard tools directly.
- If neither is connected → suggest running `claude mcp add lcp -- lcp serve-all`.

When the library name contains dots (e.g. `google.adk`), try the hyphenated form `lcp-google-adk`.

## Universal Server Workflow (`lcp serve-all`)

```
resolve_library("requests")          # required first step
get_manifest()                       # confirm name + version
list_modules()                       # browse module structure
list_symbols(module="requests")      # browse symbols
get_symbol("requests:get")           # verify exact signature
```

## Per-Library Server Workflow (`lcp serve`)

```
get_manifest()                       # confirm name + version
list_modules()                       # browse module structure
list_symbols(module="...", kind="class")
get_symbol("module:Symbol")          # verify exact signature
```

## When to Use

### 1. During Development

Before writing code against a library:

1. Resolve the library if using the universal server: `resolve_library("pkg")`
2. Call `get_manifest` to confirm the library name and version.
3. Call `list_modules` to find the relevant area.
4. Call `list_symbols(module=..., kind=...)` to browse candidates.
5. Call `get_symbol(symbol_id)` to verify the **exact** signature, required parameters, types, and return type **before** writing any call.
6. Call `get_class_members(class_id)` or `explore_return_type(symbol_id)` to understand returned objects.

**Key rule:** never assume a parameter name, type, or default — always verify with `get_symbol` first.

### 2. After a Build or Type-Check Failure

1. Identify the symbol from the error (e.g. `AttributeError: module 'requests' has no attribute 'get_json'`).
2. Call `search_symbols(query=...)` or `list_symbols(module=...)` to find the correct symbol name.
3. Call `get_symbol(symbol_id)` to get the correct signature and fix the call site.
4. If the error involves a wrong method on a returned object, call `explore_return_type(symbol_id)`.

## Tool Quick Reference

| Tool | Server | Use For |
|------|--------|---------|
| `resolve_library(name)` | Universal only | **Call first** — load a library from cache or live scan |
| `list_libraries()` | Universal only | List all loaded libraries |
| `get_usage_guide` | Both | Recommended workflow and common mistakes |
| `get_manifest` | Both | Confirm library name, version, language |
| `list_modules` | Both | Browse all module paths |
| `list_symbols` | Both | Browse symbols filtered by module and/or kind |
| `get_symbol` | Both | **Full signature, params, return type** — call before every API usage |
| `get_class_members` | Both | All methods/attributes of a class |
| `explore_return_type` | Both | Discover what you can do with a returned object |
| `search_symbols` | Both | Text search (expensive — prefer browsing first) |
| `get_suggestions` | Both | Describe your task to get starting-point recommendations |

## Common Mistakes to Avoid

- Forgetting `resolve_library` when using the universal `lcp` server.
- Starting with `search_symbols` instead of browsing (`list_modules` → `list_symbols`).
- Using a symbol without calling `get_symbol` first — leads to wrong parameter names or missing required args.
- Inventing methods on returned objects — always call `explore_return_type` or `get_class_members` to check.
