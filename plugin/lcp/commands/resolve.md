---
description: Load a Python library into LCP via resolve_library and prepare it for exploration with list_modules / list_symbols / get_symbol.
argument-hint: <package-name>
---

# Resolve a Python library

Load a Python library into LCP for exploration. Call `resolve_library("$ARGUMENTS")` to scan, cache, and make it available for browsing.

After resolving, confirm with `get_manifest()` and explore with `list_modules()` → `list_symbols()` → `get_symbol()`.
