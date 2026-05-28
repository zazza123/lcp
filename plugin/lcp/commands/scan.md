---
description: Generate a fresh LCP manifest for a pip-installed package and summarize its modules, classes, and functions.
argument-hint: <package-name>
---

# Scan a Python library

Generate a fresh LCP manifest for `$ARGUMENTS` by introspecting the pip-installed package.

1. Call `resolve_library("$ARGUMENTS")` to scan and cache the library.
2. Call `get_manifest()` to confirm the package name and version.
3. Call `list_modules()` to display the module structure.
4. Summarize the library: number of modules, classes, functions, and total symbols.
