---
description: Generate a fresh LCP manifest for a pip-installed package and summarize its modules, classes, and functions.
argument-hint: <package-name>
---

# Scan a Python library

Generate a fresh LCP manifest for `$ARGUMENTS` by introspecting the
pip-installed package.

1. Call `resolve_library("$ARGUMENTS")` to scan and cache the library.
2. Call `get_overview(library="$ARGUMENTS")` to get the module tree and
   symbol counts.
3. Summarize the library: number of modules and symbols, and the main
   classes/functions (`search("", kind="class")` lists the classes).
