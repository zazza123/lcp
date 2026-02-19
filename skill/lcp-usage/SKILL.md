---
name: lcp-usage
description: Use when writing or debugging code that depends on a third-party Python library. Before implementing against a library, check whether an LCP MCP server is connected for that library (servers follow the naming convention lcp-LIBRARY_NAME, e.g. lcp-google-adk, lcp-requests). If available, query it to discover correct APIs, signatures, and parameter types — both proactively during development and reactively when a build or type-check fails. Triggers on any task involving library usage, import errors, or API misuse.
---

# LCP Usage

Use Library Context Protocol (LCP) MCP servers as a ground-truth reference for third-party library APIs. An LCP manifest captures every public symbol, signature, and docstring of a library; the MCP server exposes it through browsable, searchable tools so you never have to guess at an API.

## Detecting Available Servers

LCP MCP servers follow the naming convention `lcp-<library-name>` (e.g. `lcp-requests`, `lcp-google-adk`, `lcp-numpy`). Before implementing code that depends on a library, check whether the corresponding MCP server is connected by looking at the available MCP tools. If a tool prefixed with `lcp-<library-name>` exists, use it.

When the library name contains dots (e.g. `google.adk`), try the hyphenated form `lcp-google-adk`.

## When to Use

### 1. During Development

Before writing code against a library:

1. Call `get_usage_guide` to learn the recommended exploration workflow.
2. Call `get_manifest` to confirm the library name and version.
3. Call `list_modules` to find the relevant area.
4. Call `list_symbols(module=..., kind=...)` to browse candidates.
5. Call `get_symbol(symbol_id)` to verify the **exact** signature, required parameters, types, and return type **before** writing any call.
6. Call `get_class_members(class_id)` or `explore_return_type(symbol_id)` to understand what methods are available on returned objects.

**Key rule:** never assume a parameter name, type, or default — always verify with `get_symbol` first.

### 2. After a Build or Type-Check Failure

When a compilation, import, or type-check error references a library symbol:

1. Identify the symbol from the error (e.g. `AttributeError: module 'requests' has no attribute 'get_json'`).
2. Call `search_symbols(query=...)` or `list_symbols(module=...)` to find the correct symbol name.
3. Call `get_symbol(symbol_id)` to get the correct signature and fix the call site.
4. If the error involves a wrong method on a returned object, call `explore_return_type(symbol_id)` on the function that produced the object to discover what methods actually exist.

## Tool Quick Reference

| Tool | Use For |
|------|---------|
| `get_usage_guide` | Recommended workflow and common mistakes |
| `get_manifest` | Confirm library name, version, language |
| `list_modules` | Browse all module paths |
| `list_symbols` | Browse symbols filtered by module and/or kind |
| `get_symbol` | **Full signature, params, return type** — call before every API usage |
| `get_class_members` | All methods/attributes of a class |
| `explore_return_type` | Discover what you can do with a returned object |
| `search_symbols` | Text search (expensive — prefer browsing first) |
| `get_suggestions` | Describe your task to get starting-point recommendations |

## Common Mistakes to Avoid

- Starting with `search_symbols` instead of browsing (`list_modules` → `list_symbols`) — search scans everything and is slow.
- Using a symbol without calling `get_symbol` first — leads to wrong parameter names or missing required args.
- Inventing methods on returned objects — always call `explore_return_type` or `get_class_members` to check.