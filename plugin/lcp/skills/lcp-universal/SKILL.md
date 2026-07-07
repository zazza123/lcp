---
name: lcp-universal
description: This skill should be used when the user writes code that imports or uses a Python library, asks to "look up the X API", "check how to use X", "what's the signature of X.Y", "resolve library X", or encounters import errors or API misuse. Activates the lcp MCP server's resolve → search → get_symbol workflow for on-demand introspection of any pip-installed package.
---

# LCP Universal — On-demand Python Library Documentation

The `lcp` MCP server (started automatically by this plugin) serves
ground-truth API documentation for any pip-installed Python library —
every public symbol, signature, and docstring, introspected from the
installed version. Unlike training data, it is never stale.

**Before you write ANY import statement, your FIRST tool call is
`resolve_library("<package>")`.** This is unconditional — do it even when
you feel certain, because memory of library APIs is stale and unreliable.
Code written before `resolve_library` returns is guessed code. The whole
workflow is 3 calls.

If a library name is provided via arguments, resolve it immediately:

```
resolve_library("$ARGUMENTS")
```

## The 3-call workflow

```
resolve_library("polars")                  # 1. load (cache / scan / registry)
search("read csv", library="polars")       # 2. find symbols, ranked
get_symbol(ids=["polars:read_csv"])        # 3. exact signature + import line
```

1. **`resolve_library(name, version?)`** — always first. Loads the library
   and reports name, version, symbol count, and source.
2. **`search(query, library?, module?, kind?, limit?)`** — ranked discovery.
   Every hit carries the exact `import` line. An **empty query browses**:
   `search("", module="polars.io", kind="function")` lists a module's
   contents deterministically.
3. **`get_symbol(ids, library?)`** — batch verification. Full signatures,
   required/optional parameters (with docstring descriptions), return types
   plus `returns_description`, `raises` conditions, docstring usage examples,
   and the correct import line.
   Symbols re-exported at package level resolve under both the documented
   import path and the canonical id (`resolved_via_alias` names the
   definition site); the `import` line is always the documented path —
   copy it as-is.
   Classes inline all members as one-line summaries; fetch
   `"module:Class#member"` for a member's full signature.
   `usage_hints.returns_classes` names the class a call returns — use it to
   verify methods on returned objects instead of inventing them.

For orientation, `get_overview(library?)` returns the module tree with
symbol counts.

## Multiple libraries

With one library loaded, `library=` may be omitted. With two or more, every
call requires `library=<name>` — otherwise you get an
`{"error": {"code": "ambiguous_library", "loaded_libraries": [...]}}`
response naming the choices.

## Errors

All failures are structured:
`{"error": {"code", "message", "hint", ...}}` — follow the `hint` (e.g.
"call resolve_library first", "pass library=").

## Key rules

- **Never assume** a parameter name, type, or default — `get_symbol` first.
- **Never invent** methods on returned objects — follow
  `usage_hints.returns_classes`.
- Batch related lookups into ONE `get_symbol(ids=[...])` call.
- Truncated responses say so (`"truncated": true`) and hint at the follow-up.
- Private packages work too — any pip-installed package can be scanned.
