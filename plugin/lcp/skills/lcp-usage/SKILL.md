---
name: lcp-usage
description: This skill should be used when the user writes code against a Python library, asks "how do I use X", encounters an AttributeError or ImportError on a library symbol, or asks "what parameters does X.Y take". Guides the agent to verify APIs through the lcp MCP server's resolve → search → get_symbol workflow before writing code.
---

# LCP Usage

Use the LCP (Library Context Protocol) MCP server as the ground-truth
reference for Python library APIs. It introspects the installed package, so
it reflects the exact installed version — verify against it instead of
guessing from memory.

If a library name is provided via arguments, resolve it immediately:

```
resolve_library("$ARGUMENTS")
```

## When to reach for it

- Before importing or calling a library you haven't verified this session.
- On any `ImportError` / `AttributeError` involving a library symbol.
- Whenever you are about to write a signature you are not 100% sure of —
  a plausible guess is the top source of broken code.

## The 3-call workflow

```
resolve_library("requests")             # 1. always first
search("send get request")              # 2. ranked discovery + import lines
get_symbol(ids=["requests.api:get"])    # 3. exact signature before coding
```

`get_overview()` shows the module tree; `search("", module=..., kind=...)`
browses a module's contents.

## Tool reference

| Tool | Purpose |
|------|---------|
| `resolve_library(name, version?)` | Load a library (cache / scan / registry). Always call first. |
| `search(query, library?, module?, kind?, limit?)` | Ranked symbol search; empty query = browse. Hits include the import line and present the documented (re-export) id, with `resolved_via_alias` naming the definition site. |
| `get_symbol(ids, library?)` | Batch: full signatures, params with descriptions, return types + `returns_description`, `raises` conditions, docstring examples, import lines; classes inline member summaries. Accepts canonical and alias ids alike — the `import` line is the documented path, copy it as-is. |
| `get_overview(library?)` | Library identity + module tree with symbol counts. |

## Rules

- With ≥2 libraries loaded, pass `library=` on every call (an
  `ambiguous_library` error lists the loaded names if you forget).
- Errors are `{"error": {"code", "message", "hint", ...}}` — follow the hint.
- If no `lcp` server is connected, suggest:
  `claude mcp add lcp -- lcp serve-all`.
