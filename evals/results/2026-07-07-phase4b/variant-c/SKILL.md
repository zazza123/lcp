---
name: lcp-universal
description: This skill should be used when the user writes code that imports or uses a Python library, asks to "look up the X API", "check how to use X", "what's the signature of X.Y", "resolve library X", or encounters import errors or API misuse. Activates the lcp MCP server's resolve → search → get_symbol workflow for on-demand introspection of any pip-installed package.
---

# LCP — Verified Python Library APIs

The `lcp` MCP server serves ground-truth API documentation for any
pip-installed Python library, introspected from the installed version —
never stale, unlike memory.

**Verify before you write.** If you are not certain a symbol exists with
the exact signature you are about to write, check it first — the whole
workflow is 3 calls:

```
resolve_library("polars")                  # 1. load the library (always first)
search("read csv", library="polars")       # 2. find symbols, ranked
get_symbol(ids=["polars:read_csv"])        # 3. exact signature + import line
```

Rules:

- **Never assume** a parameter name, type, or default — `get_symbol` first.
- **Never invent** methods on returned objects — follow
  `usage_hints.returns_classes`.
- Copy the `import` line from responses as-is; batch related ids into ONE
  `get_symbol(ids=[...])` call.
- With two or more libraries loaded, pass `library=<name>` on every call.
- Error responses are structured and carry a `hint` — follow it (e.g.
  "call resolve_library first").
