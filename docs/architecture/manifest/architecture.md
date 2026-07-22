# Manifest Generation - Architecture

## Overview

This document covers the internals of the three-stage scan → generate → validate pipeline that produces an LCP manifest.

---

## Stage 1: Scanner

**Module:** `src/lcp/scanner.py`

The scanner uses Python's `inspect` module to introspect a live, imported package. It never parses source files directly for symbol discovery — it relies on the runtime object graph. Source files are accessed only to retrieve file paths and line number ranges via `inspect.getfile()` / `inspect.getsourcelines()`.

### Internal Data Structures

| Dataclass | Purpose |
|-----------|---------|
| `ScannedParam` | One parameter: name, type hint string, default value, kind (`positional`, `keyword_only`, `rest`, …) |
| `ScannedSignature` | Callable signature: list of `ScannedParam`, return type string, `is_async` flag |
| `ScannedSymbol` | One symbol: name, qualified name, module path, kind, summary/description, signature, members list, source location |
| `ScannedModule` | Top-level result: package name, version, flat list of all `ScannedSymbol` objects |

Class members (methods, properties) are stored inline inside the parent `ScannedSymbol.members` list. The generator later flattens this into the top-level `symbols` dict.

### Entry Points

- `scan_package(package_name, include_private, recursive, include_tests)` — top-level function; imports the package, calls `scan_module()` on the root module, then iterates over submodules if `recursive=True`
- `scan_module(module, include_private, _visited)` — scans one `ModuleType`; uses a `_visited` set of object IDs to avoid processing the same module twice (handles circular imports)

### Submodule Discovery

`_iter_submodules()` uses `pkgutil.iter_modules()` for standard packages. It also handles namespace packages (directories without `__init__.py`) by iterating the package's `__path__` entries directly and trying to import any subdirectory that is a valid Python identifier.

Submodule discovery is fail-open: a submodule that raises at import time is skipped and the walk continues, so one hostile module can never abort the whole scan. The guard catches any `BaseException` (not only `Exception`) — `KeyboardInterrupt` and `SystemExit` remain handled explicitly, but `BaseException` subclasses raised by import-time probes are caught too. This matters because test modules commonly call `pytest.importorskip()`, which raises `Skipped` (a `BaseException`, not an `Exception`); without this, any package whose test suite probes an absent optional dependency (`pandas`, `scipy`, `pyarrow`) would fail to scan at all.

Test subpackages are excluded by default. Any subpackage whose leaf name is exactly `tests` is skipped *before* it is imported — controlled by the `include_tests` flag (default off). The rationale is twofold: test packages are not public API and would otherwise dominate a manifest (roughly a third of the raw symbols for large scientific packages), and skipping them before import also sidesteps the `importorskip` failure mode above at the source. The rule matches the leaf name exactly, so public utilities such as `numpy.testing` (leaf `testing`) are always included. Pass `include_tests=True` to scan test packages anyway.

### Public Symbol Rules

`_is_public(name, include_private)` controls what names are emitted:

1. If `include_private=True`, all names pass.
2. Names in the **public dunders allowlist** always pass (e.g. `__init__`, `__call__`, operators). See [index.md](index.md#what-gets-scanned) for the full list.
3. All other names starting with `_` are excluded.

When a module defines `__all__`, that set takes precedence: only names listed there are scanned (after applying the public-name check).

### Re-export Aliases

Re-exported symbols — where `obj.__module__` differs from the current module's name — are never scanned twice. What happens instead depends on where the object comes from:

- **Intra-package re-export** (the origin module is inside the scanned package, e.g. `requests/__init__.py` re-exporting `requests.api.get`): `scan_module()` records an `_AliasRecord` with the origin, the re-exporting module, and the local name (which may differ for `from x import y as z` renames). After all modules are scanned, `_attach_aliases()` resolves each record onto its canonical `ScannedSymbol`, filling its `aliases` list with `(module_path, name)` pairs. Records whose target was never scanned are dropped.
- **External re-export from a declared dependency** (the origin is a different, non-stdlib distribution that the scanned package's own metadata declares as a requirement, e.g. `flask` re-exporting `request`, `g`, `current_app` and `session` from `werkzeug`, or `pydantic` re-exporting `ValidationError` from `pydantic_core`): the foreign package is never scanned, but the object itself is captured in place as a symbol whose canonical identity is the facade module — `flask:request`, `pydantic:ValidationError`. The discriminator resolves the scanned package's distribution(s) to their declared dependencies and checks the re-export's top-level origin module against that set (excluding anything in `sys.stdlib_module_names`), so a name re-exported from the standard library or from an undeclared/foreign distribution is still skipped. A re-exported callable whose signature can be recovered (i.e. it looks like a C-implemented function rather than a Python one) is deliberately left uncaptured here too — that recovery is issue #63, not this mechanism. This is issue #67; the discriminator is inert (behaves exactly as before) whenever dependency metadata cannot be resolved. This capture is scoped to the entry module the user scans: `scan_package()` computes the declared-dependency top-levels once and passes them only to the root module's `scan_module()` call, so a package's internal submodules are inert for this mechanism and never capture their own dependency re-imports. That scoping was a deliberate, measurement-driven decision, not an oversight — threading the followable set into every submodule was tried first and, measured against the corpus in `tools/corpus/`, added thousands of noise symbols.
- **External re-export from a same-distribution sibling package** (the origin sits outside the scanned package's own subtree but under the same top-level import segment, e.g. `google` for both `google.cloud.firestore` and `google.cloud.firestore_v1`, and the *scanned package's own installed distribution* — resolved from that distribution's file list via `_own_distribution_modules()`, not from the ambiguous `packages_distributions()` lookup — also provides the origin module): the shared top-level segment means an `_AliasRecord` for this crossing is created during the walk exactly like an intra-package one, but its target is never itself scanned, so left alone it would dangle (see Unresolved Re-export Reporting below). Once the walk finishes, `scan_package()` re-resolves every still-dangling record whose target belongs to that same distribution at its definition site: a re-exported class or function is captured canonically in the sibling module, with the facade path recorded as its alias, so the idiomatic facade path still surfaces first through the preferred-alias ordering the MCP layer already applies (fewest module segments wins; see [MCP Server](../mcp_server/architecture.md)). A re-exported value with no name of its own — a sentinel such as firestore's `SERVER_TIMESTAMP` or `DELETE_FIELD` — has no definition-site identity to alias to, so it is captured directly at the facade instead, as a constant. Only the names the facade actually re-exports are followed this way: the sibling module itself is never walked, and a sibling package the facade does not import from (`google.cloud.firestore_admin_v1`, alongside `firestore_v1` in the same distribution) is untouched. This is issue #68, completing problem 2 of #58 alongside #67. What it does not cover: a name that lives in the sibling implementation package but that the facade itself never re-exports is not captured through the facade at all — a consumer wanting that surface has to scan the sibling package (`google.cloud.firestore_v1`) directly.
- **External re-export with no resolvable declared-dependency or same-distribution-sibling relationship** (the origin is another package that is either stdlib, not declared as a dependency, or not part of the scanned package's own distribution, e.g. `from json import loads` inside a scanned package): skipped entirely, exactly as before.

The definition site remains the canonical identity; the generator turns the recorded pairs into the additive `Symbol.aliases` field (a sorted list of full Symbol IDs, e.g. `requests:get`), so a symbol is findable under the import path users actually write while the `symbols` map key stays stable. Why this design: agents and users think in documented import paths (`requests.get`), but rewriting IDs to the re-export site would break ID stability across internal refactors — aliases give both.

### Unresolved Re-export Reporting

An `_AliasRecord` can end up dangling — its target was never scanned, so `_attach_aliases()` has nothing to attach the alias to. There are two distinct reasons a record dangles, and the scanner deliberately treats them differently:

- **Benign drop.** The defining module *was* scanned, but the target is not a scannable kind (a plain module-level variable, for instance). This is silent, exactly as before this diagnostic existed — there was never any public surface being lost.
- **Real lost surface.** The defining module was *never* scanned at all. This is the issue #58 case: a facade package that re-exports from a sibling package. `scan_package()` sets the package root to the first dotted segment of the import path (`google` for `google.cloud.firestore`) — not the installed distribution, which for that package is `google-cloud-firestore` — so a sibling re-export does pass the in-package test and an alias record *is* created — it only dies later, dangling, because the sibling module was never visited by the walk. Without this distinction, the scan of the facade would silently produce a near-empty manifest that still validates and still exits successfully. When the sibling module belongs to the same distribution as the scanned package, this dangling record is now exactly the input the same-distribution-sibling capture (described above, #68) resolves instead of leaving lost; what remains genuinely lost through this path is a target outside both the scanned subtree and the scanned distribution — an unrelated package sharing only the top-level namespace.

`_attach_aliases()` collapses each dangling origin module to the sibling package it belongs to before reporting, but only when the origin actually sits outside the scanned subtree: a facade re-exports from a sibling package that sits at the same depth in the module tree as the package that was scanned, so every such origin is truncated to that many dotted segments (an origin with fewer segments than the scanned package's depth keeps its own full name — it is never padded out). Scanning `google.cloud.firestore` (three dotted segments), for example, collapses an origin such as `google.cloud.firestore_v1.types.write` down to `google.cloud.firestore_v1` — the actually useful follow-up scan target — and folds in every other defining submodule under that same sibling, including private ones such as `google.cloud.firestore_v1._helpers`, which would otherwise surface as a private-module suggestion.

An origin that is itself a descendant of the scanned target — a submodule of the very package being scanned, equal to the target or starting with the target plus a dot — is never collapsed this way. Truncating it to the target's depth would just return the target unchanged, which is nonsensical: it would produce a warning that a package is undefined "in" the package that was just successfully scanned, with a follow-up suggestion to scan the same package again. This shape is ordinary and expected — `_iter_submodules` skips any submodule that raises on import (an optional dependency, a `TYPE_CHECKING`-only branch, a platform-specific module), and the alias mechanism exists precisely to catch an already-scanned module re-exporting a name from one that failed. Such an origin keeps its own full module path instead, which is the genuinely actionable target for the import failure.

This produces `(ancestor_module, distinct_name_count, contributing_module_count)` triples, sorted by descending name count then ascending ancestor path, which `scan_package()` carries on `ScannedModule.unresolved_reexports`. `lcp scan` prints a warning to stderr naming the ancestor and suggesting a follow-up scan of it, wording it as a single defining module ("in") or several collapsed into one ancestor ("under ... (N modules)") depending on `contributing_module_count`; the MCP `resolve_library` tool attaches a `note` to its response with the same distinction, pointing the calling agent at the module it should resolve instead.

The diagnostic is structurally blind when the re-export crosses a top-level package boundary, because `scan_module()` only records an `_AliasRecord` when the target is inside the same package root. That blind spot is now closed for both shapes it was written to flag: a name re-exported from a distribution the scanned package declares as a dependency (the `flask`-importing-from-`werkzeug` shape) is captured directly at the facade (#67), and a name re-exported from a sibling implementation package in the scanned package's own distribution (the `google.cloud.firestore` → `firestore_v1` shape described above) is now captured at its definition site once the dangling record resolves to that sibling (#68, described above) — neither shape leaves the diagnostic anything to report, because neither leaves the surface actually lost. What is not covered — and is not a gap in this diagnostic, since no `_AliasRecord` is ever created for it — is a name that lives in the sibling package but that the facade itself never re-exports: there is no re-export for `scan_module()` to observe, so a consumer wanting that surface has to scan the sibling package directly. This completes problem 2 of #58.

This diagnostic is scan-time only: it is derived from data that never enters the `LCPDocument` or the manifest schema, so it appears on the scan that produces it and not on subsequent cache or registry hits for the same package. That is a deliberate trade-off — the manifest itself stays a pure implementation of the LCP v1 spec, with no scanner-internal bookkeeping leaking into it.

### Docstring Parsing

`_parse_docstring()` splits a raw docstring into:
- **summary** — the first paragraph (consecutive non-empty lines joined with a space)
- **description** — everything after the first blank line, stripped

Both fields may be `None` if no docstring exists. The scanner additionally captures the raw docstring verbatim on `ScannedSymbol.docstring` (guarded by the same non-string check — some classes expose `__doc__` as a descriptor). This is capture only: no structured parsing happens during member iteration, so a hostile package cannot crash the scan through its docstrings. Structured parsing is deferred to the generator stage.

### Type Hint Resolution

`_type_to_string()` converts a runtime type hint to a readable string:
- Uses `typing.get_origin()` / `typing.get_args()` for generics (`List[str]`, `Optional[int]`, `Union[…]`)
- Collapses `Union[X, None]` to `Optional[X]`
- Falls back to `__name__` or `str()` for plain types

`get_type_hints()` is preferred over `inspect.Parameter.annotation` because it resolves string annotations (`from __future__ import annotations`).

---

## Stage 2: Generator

**Module:** `src/lcp/generator.py`

The generator converts the `ScannedModule` tree into an `LCPDocument`. All logic is pure transformation — no I/O, no imports.

### Symbol ID Construction

`_build_symbol_id(scanned)` produces `"{module_path}:{entity_path}"`:
- Module symbols have an empty `qualified_name`, producing `"json:"`.
- Functions and classes use their plain name: `"json:loads"`, `"pathlib:Path"`.
- Methods use `Class#method` notation in `qualified_name`: `"pathlib:Path#resolve"`.

### Symbol Conversion

`_convert_symbol(scanned)` maps each `ScannedSymbol` to a `(symbol_id, Symbol)` pair:

1. **Semantics**: `summary` from the parsed docstring, or a fallback `"{kind} {name}"` string; `description` if present; `examples` extracted from the docstring's `Examples` sections (see below).
2. **Signatures**: constructed only for `function`, `method`, and `class` kinds. The class signature is the `__init__` signature captured by the scanner. Parameter descriptions, `raises` entries and the `returns_description` come from the docstring (see below).
3. **Kind mapping**: scanner strings (`"function"`, `"class"`, …) → `SymbolKind` enum values.

### Structured Docstring Extraction

`extract_structured()` in `src/lcp/docstrings.py` parses the raw docstring captured by the scanner (Google and NumPy styles, auto-detected via the `docstring_parser` dependency) and returns a `DocstringExtras` value holding per-parameter descriptions, `(exception, condition)` pairs, the return-value prose, and `(code, description)` example pairs. `_convert_symbol()` calls it once per symbol and threads the result through `_convert_signature()` and `_convert_param()`.

Design rules, in order of importance:

- **Fail-open.** Any parser exception makes `extract_structured()` return `None` and the generator emits exactly the pre-Phase-4 output (summary + raw description). A docstring can degrade the enrichment, never the manifest.
- **Introspection wins.** Docstring parameter entries are merged with introspected parameters *by name*: a matching entry contributes only its description text; an unmatched entry (a renamed or removed parameter that the docstring still mentions) never invents a `Param`, and types always come from introspection.
- **No information loss.** `semantics.description` keeps the scanner's full post-summary remainder even when parsing succeeds. This is deliberate duplication: the Google-style parser silently drops unknown sections (such as a `Note:` appearing after `Args:`), so rebuilding the description from parser output would lose prose. The measured gzip cost is ~10–30 % on real libraries.
- **Examples via doctest.** `Examples` sections containing `>>>` blocks are re-rendered through the stdlib `doctest` parser (canonical prompts plus expected output, surrounding prose becoming the example description); sections without `>>>` are taken verbatim. A malformed doctest is dropped without discarding the docstring's other structured fields.

### Class Member Flattening

`generate_lcp()` iterates `scanned_module.symbols` (the flat list including class symbols). For each class symbol it also iterates `scanned.members` and converts each member independently, adding them as top-level entries in the `symbols` dict under their `Class#method` IDs. Members do not appear nested inside the class entry in the output.

### Detailed Index

For symbols that have source location data (`source_file` and `source_lines`), `_build_detailed_index_entry()` creates a `DetailedIndexEntry` with an `Artifact` pointing to the file path and `[start_line, end_line]`. These entries are collected in `detailed_index` and included in the final document.

### Manifest Header

The manifest is populated with:
- `schema_version`: `"1.0"`
- `library.name` / `library.version` from `ScannedModule`
- `library.language`: `"python"` (hardcoded)
- `distribution`: `"pypi"`
- `generation.tool`: `"lcp"`, `generation.date`: current UTC timestamp

---

## Stage 3: Validator

**Module:** `src/lcp/validator.py`

The validator checks a completed `LCPDocument` against the bundled `schema.json` using `jsonschema` (Draft 2020-12).

### Validation Functions

| Function | Input | Output |
|----------|-------|--------|
| `validate_document(doc)` | `LCPDocument` | `list[str]` of error messages |
| `validate_dict(data)` | `dict` | `list[str]` of error messages |
| `validate_file(path)` | file path | `list[str]` of error messages |
| `is_valid(doc)` | `LCPDocument` or `dict` | `bool` |
| `validate_or_raise(doc)` | `LCPDocument` or `dict` | raises `LCPValidationError` |

`LCPValidationError` collects all errors and formats the first ten in its message. It is raised by `scan()` when `validate=True` (the default).

Each error message includes a dot-separated JSON path prefix (e.g. `symbols.json:loads.semantics`) pointing to the offending field.

---

## LCP Document Model

**Module:** `src/lcp/models.py`

All models use `ConfigDict(extra="allow")`, which means the SDK round-trips unknown fields transparently and remains forward-compatible with future LCP spec extensions.

### Document Structure

`LCPDocument` in `src/lcp/models.py` is the root model. It contains a `manifest` field of type `Manifest`, a `symbols` dict keyed by symbol ID, an optional `deprecations` dict, and an optional `detailed_index` dict.

`Manifest` holds the library name, version, and language via a nested `Library` model, plus `schema_version`, `distribution`, `symbol_resolution`, optional `compatibility` (Python version range and supported platforms), and `generation` metadata (tool name, version, UTC date).

Each `Symbol` in the `symbols` dict has a `kind` (`SymbolKind` enum), a `module` path, an optional list of `Signature` objects, and a required `semantics` field of type `Semantics`. `Semantics` holds the `summary` (required), an optional `description`, and optional `examples`. A `Signature` carries an `async` flag, an optional list of `Param` objects, an optional return type (`TypeRef` or string), and an optional list of `RaisesEntry` objects. Each `Param` records its name, type, `required` flag, default value, `variadic` flag, and `kind` (`ParamKind` enum).

The `detailed_index` dict maps symbol IDs to `DetailedIndexEntry` objects, each containing an `Artifact` with the source file path and a `[start_line, end_line]` pair.

### Serialization

`LCPDocument.to_dict()` calls `model_dump(mode="json", by_alias=True, exclude_none=True)`. The `by_alias=True` is needed because `Signature.async_` is stored internally as `async_` (to avoid the Python keyword) but serialized as `"async"` via a Pydantic `Field(alias="async")`.

---

## Related Documentation

- [Manifest Overview](index.md) - CLI usage, Python API, symbol IDs
- [Coverage](../coverage/index.md) - Uses the same `ScannedModule` to analyze doc completeness
- [MCP Server](../mcp_server/index.md) - Loads the `.lcp.json` output and exposes it over MCP

---
**Last Updated:** July 2026
**Status:** Implemented
