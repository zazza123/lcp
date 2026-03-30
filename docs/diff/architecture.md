# Version Diff - Architecture

## Overview

This document covers the internals of the diff module: how two LCP documents are compared, how deprecation entries are generated, and how they are merged back into a document.

---

## Comparison Algorithm

**Function:** `diff_documents()` in `src/lcp/diff.py`

The comparison operates purely on symbol IDs — the string keys of the `symbols` dict in each `LCPDocument`. No structural or semantic diffing is performed on individual symbol contents.

### Steps

1. Extract the set of symbol IDs from each document.
2. Compute the set difference in both directions:
   - `removed = old_ids - new_ids` — symbols that existed in the old version but are absent in the new one.
   - `added = new_ids - old_ids` — symbols that exist in the new version but were absent in the old one.
3. Sort both lists alphabetically for deterministic output.
4. For each removed symbol, create a `SymbolDiff` with the symbol's ID, kind, module, and summary (extracted from the old document).
5. For each added symbol, create a `SymbolDiff` from the new document.
6. For each removed symbol, create a `Deprecation` entry with `deprecated_in` set to the new document's version string.
7. Return a `DiffResult` containing all of the above.

Symbols that appear in both documents (the intersection) are not examined — the diff module does not detect signature changes, docstring updates, or other modifications to existing symbols.

---

## Data Structures

### SymbolDiff

A lightweight dataclass describing one symbol that was added or removed:

| Field | Type | Description |
|-------|------|-------------|
| `symbol_id` | `str` | The full symbol ID (e.g. `json:loads`) |
| `kind` | `str` | Symbol kind string (`function`, `class`, `method`, etc.) |
| `module` | `str \| None` | Module path the symbol belongs to |
| `summary` | `str \| None` | One-line summary from the symbol's semantics |

### DiffResult

The top-level result dataclass returned by `diff_documents()`:

| Field | Type | Description |
|-------|------|-------------|
| `old_version` | `str` | Version string from the old document |
| `new_version` | `str` | Version string from the new document |
| `library_name` | `str` | Library name from the new document's manifest |
| `removed` | `list[SymbolDiff]` | Symbols present in old but absent in new |
| `added` | `list[SymbolDiff]` | Symbols present in new but absent in old |
| `deprecated` | `dict[str, Deprecation]` | Map of symbol ID → generated `Deprecation` entry |

`DiffResult` provides two serialization methods:
- `to_dict()` — returns a JSON-serializable dict with `summary`, `removed`, `added`, and `deprecations` fields.
- `to_json(indent=2)` — returns a formatted JSON string.

### Deprecation Model

`Deprecation` in `src/lcp/models.py` is a Pydantic model with:

| Field | Type | Description |
|-------|------|-------------|
| `deprecated_in` | `str` | Version in which the symbol was deprecated |
| `replaced_by` | `str \| None` | Symbol ID of the replacement, if any |
| `notes` | `str \| None` | Free-text notes about the deprecation |

The diff module only populates `deprecated_in`. The `replaced_by` and `notes` fields can be filled in manually after generation.

---

## Document Update Strategy

**Function:** `update_document()` in `src/lcp/diff.py`

`update_document()` merges the `deprecated` dict from a `DiffResult` into an existing `LCPDocument`. The merge follows these rules:

1. If the document already has a `deprecations` dict, its entries are preserved as-is.
2. For each entry in the diff result's `deprecated` dict, the entry is added only if the symbol ID is **not** already present in the document's existing deprecations.
3. If the merged dict is empty (no existing entries and no new entries), `deprecations` is set to `None` to avoid writing an empty object.
4. The function returns a **new** `LCPDocument` via Pydantic's `model_copy(update=...)` — the original document is not mutated.

This design ensures that:
- Running `lcp diff --update` multiple times is idempotent — existing entries are never overwritten.
- Manually curated deprecation notes (e.g. `replaced_by` or `notes` fields) are preserved across repeated diff runs.

---

## File Loading

**Function:** `load_lcp_document()` in `src/lcp/diff.py`

A convenience function that reads a JSON file from disk and returns a validated `LCPDocument`. It opens the file with UTF-8 encoding, parses it with `json.load()`, and passes the result to `LCPDocument.model_validate()`. Pydantic validation ensures the file conforms to the LCP document structure.

Possible exceptions:
- `FileNotFoundError` — file does not exist
- `json.JSONDecodeError` — file is not valid JSON
- `pydantic.ValidationError` — JSON does not match the `LCPDocument` schema

---

## CLI Integration

The `lcp diff` command in `src/lcp/cli.py` is a thin wrapper around the diff module functions. It:

1. Loads both files via `load_lcp_document()`.
2. Calls `diff_documents()` to produce a `DiffResult`.
3. Serializes the result with `to_json()` and writes it to stdout or a file.
4. Prints a summary to stderr (library name, version range, removed/added counts).
5. If `--update` is set and there are deprecations, calls `update_document()` and writes the updated document back to the NEW file path via `to_file()`.

---

## Related Documentation

- [Version Diff Overview](index.md) - CLI usage, Python API, diff report format

---
**Last Updated:** March 2026
**Status:** Implemented
