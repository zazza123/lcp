---
name: lcp-usage
description: This skill should be used when the user writes code against a Python library, asks "how do I use X", encounters an AttributeError or ImportError on a library symbol, or asks "what parameters does X.Y take". Detects whether the universal lcp server or a per-library lcp-LIBNAME server is connected and guides the agent to use the correct exploration workflow.
version: 0.1.0
---

# LCP Usage

Use Library Context Protocol (LCP) MCP servers as a ground-truth reference for Python library APIs. LCP captures every public symbol, signature, and docstring; the MCP server exposes it through browsable, searchable tools.

## Two server modes

### 1. Universal server (`lcp serve-all`)

The `lcp` MCP server (provided by this plugin) handles **any** library:

1. Call `resolve_library("package_name")` to load a library.
2. Use the standard tools to explore it.
3. The last resolved library is the implicit default; pass `library=` to target a specific one.

### 2. Per-library server (`lcp serve`)

If a dedicated server is connected, it follows the naming convention `lcp-<library-name>` (e.g. `lcp-requests`, `lcp-numpy`). These servers don't require `resolve_library` — they're pre-loaded with one library's manifest.

## Detection order

1. Check if the `lcp` universal server is connected — use `resolve_library` + standard tools.
2. Check if a per-library `lcp-<name>` server is connected — use standard tools directly (no `resolve_library`).
3. If neither: suggest the user run `claude mcp add lcp -- lcp serve-all`.

## Recommended workflow

### Universal server

```
resolve_library("requests")          # step 1: always required
get_manifest()                       # step 2: confirm version
list_modules()                       # step 3: find relevant area
list_symbols(module="requests")      # step 4: browse candidates
get_symbol("requests:get")           # step 5: verify exact signature
```

### Per-library server

```
get_manifest()                       # step 1: confirm library + version
list_modules()                       # step 2: find relevant area
list_symbols(module="...", kind="class")
get_symbol("module:Symbol")          # step 3: verify exact signature
```

## Tool reference

| Tool | Purpose |
|------|---------|
| `resolve_library(name)` | Universal server only — load a library (cache or live scan) |
| `list_libraries()` | Universal server only — list all loaded libraries |
| `get_usage_guide()` | Workflow, tips, and common mistakes |
| `get_manifest(library?)` | Library name, version, language |
| `list_modules(library?)` | All module paths |
| `list_symbols(library?, module?, kind?)` | Browse symbols |
| `get_symbol(id, library?)` | Full signature — **verify before every API call** |
| `get_class_members(id, library?)` | All methods/attributes of a class |
| `explore_return_type(id, library?)` | Methods available on returned objects |
| `search_symbols(query, library?)` | Text search (expensive) |
| `get_suggestions(task, library?)` | Task-based suggestions |

## Common mistakes

- Forgetting `resolve_library` when using the universal `lcp` server.
- Starting with `search_symbols` instead of `list_modules` → `list_symbols`.
- Using a symbol without calling `get_symbol` first — wrong parameters guaranteed.
- Inventing methods on returned objects — always check `explore_return_type`.
