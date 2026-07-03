---
description: Load a Python library into LCP via resolve_library and prepare it for exploration with search / get_symbol.
argument-hint: <package-name>
---

# Resolve a Python library

Load a Python library into LCP for exploration. Call
`resolve_library("$ARGUMENTS")` to scan, cache, and make it available.

Then explore with `search("<what you need>", library="$ARGUMENTS")` and
verify exact signatures with `get_symbol(ids=[...])` before writing code.
