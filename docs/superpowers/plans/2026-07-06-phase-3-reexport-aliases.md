# Phase 3 — Re-export Aliases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A symbol re-exported inside its own package is findable and presented under the name users actually import (`requests:get` resolves even though it is defined in `requests.api`), and the eval harness stops under-counting exactly this fix.

**Architecture:** The scanner records intra-package re-exports as `(module, name)` alias pairs on the canonical `ScannedSymbol` (definition site stays the ID). The generator emits an additive `Symbol.aliases: list[str]` field (spec D10, schema `"1.0"`, backward compatible). `LCPIndex` indexes alias IDs and expands class-member alias IDs at build time without duplicating manifest entries; `search`/`get_symbol` present the preferred importable ID first, marking alias hits with `resolved_via_alias: "<canonical id>"` (alias-first decision, settled 2026-07-06). The eval harness verifier (`symbol_used`) learns aliases via live object-identity resolution in the same phase.

**Tech Stack:** Python ≥3.10, pydantic v2, jsonschema (Draft 2020-12), fastmcp ≥3.0,<4 (main venv) / 2.14.4 (evals venv), pytest.

**Design authority:** `docs/superpowers/specs/2026-07-03-v2-surface-design.md` D10/D4/D12; roadmap Phase 3 section (`docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md:444-522`).

**Decisions settled at phase start (2026-07-06, with the user):**
1. **Alias-first presentation:** search hits and `get_symbol` entries carry the preferred importable ID as `id` (echoing the requested ID in `get_symbol`), with `resolved_via_alias: "<canonical id>"` when `id` is not the canonical. Members of a class served via an alias are alias-prefixed (`pkg:Widget#render`).
2. **Recording rule — intra-package always:** the scanner records an alias whenever `obj.__module__ != module_path` AND `obj.__module__` is inside the package root. The `__all__` filter stays upstream (if `__all__` exists, only listed names reach the check). External re-exports stay skipped, exactly as today. Evidence: `requests` root has NO `__all__` (`requests.get.__module__ == "requests.api"`); `cyhole.jupiter` HAS `__all__` with `Jupiter.__module__ == "cyhole.jupiter.interaction"` — a narrower rule misses one of the two flagship cases.

## Global Constraints

- Schema version stays `"1.0"`; `aliases` is additive-only. Both `src/lcp/schema.json` and `docs/assets/schema.json` must stay **semantically identical** (they differ in formatting; verify with `python3 -c "import json; print(json.load(open('src/lcp/schema.json'))==json.load(open('docs/assets/schema.json')))"` → `True`).
- Main test suite (461+ tests) runs from the project `.venv` (fastmcp 3.x): `pytest`. Harness tests run from `evals/.venv`: `evals/.venv/bin/python -m pytest evals/tests -v`. **NEVER run `pip install -e ".[dev]"` in `evals/.venv`** (it would bump the pinned fastmcp 2.14.4 — see `evals/README.md`).
- Commits follow the `git-commit-convention` skill (3-letter action code; NO co-author lines, NO session links — public repo).
- `docs/superpowers/` is gitignored: commit roadmap/plan updates with `git add -f`.
- Docs follow the `lcp-writing-documentation` skill (architecture vs guides vs spec conventions); `mkdocs build --strict` must pass at the end.
- Scanner resilience must not regress: alias recording happens inside the existing per-member `try/except` in `scan_module`; no second scanning pass (roadmap code note: don't defeat `_visited` dedup).

---

### Task 1: Re-exporting fixture package + scanner alias recording

**Files:**
- Create: `tests/sample_package/__init__.py`, `tests/sample_package/core.py`, `tests/sample_package/extras.py`, `tests/sample_package/convenience.py`, `tests/sample_package/allexport.py`, `tests/sample_package/mod_a.py`, `tests/sample_package/mod_b.py`, `tests/sample_package/re_a.py`, `tests/sample_package/re_b.py`
- Modify: `src/lcp/scanner.py` (`ScannedSymbol` at :45-58, `scan_module` at :393-482, `scan_package` at :573-596)
- Test: `tests/test_scanner.py` (new class `TestReexportAliases`)

**Interfaces:**
- Produces: `ScannedSymbol.aliases: list[tuple[str, str]]` — list of `(alias_module_path, alias_name)` pairs, empty by default. `scan_module(..., _alias_records=None)` keyword param (private, backward compatible). Helper `_attach_aliases(symbols, records)` and dataclass `_AliasRecord`.
- Consumed by: Task 2's generator (`scanned.aliases` → `Symbol.aliases` ID strings).

- [ ] **Step 1: Create the fixture package**

`tests/conftest.py` already puts `tests/` on `sys.path`, so `sample_package` is importable by name. Create these files:

`tests/sample_package/__init__.py` (package root, **no** `__all__` — the requests-shaped case, plus an `as`-rename and external re-exports that must NOT alias):
```python
"""Sample package fixture for re-export alias scanning."""

from json import loads  # external re-export: must NOT produce an alias
import json  # external module: must stay skipped

from .core import CoreClass, core_function, CONSTANT
from .extras import helper as aliased_helper
```

`tests/sample_package/core.py`:
```python
"""Core module defining the canonical symbols."""

CONSTANT = 42


class CoreClass:
    """A class re-exported at the package root."""

    def do_something(self) -> str:
        """Do something."""
        return "done"


def core_function(x: int) -> int:
    """A function re-exported at the package root."""
    return x + 1


def _private_function() -> None:
    """Never public."""
```

`tests/sample_package/extras.py`:
```python
"""Extras module whose helper is re-exported under a different name."""


def helper() -> str:
    """A helper re-exported at the root as aliased_helper."""
    return "help"
```

`tests/sample_package/convenience.py` (star re-export, **no** `__all__` anywhere in the chain):
```python
"""Convenience module star-re-exporting core."""

from .core import *  # noqa: F401,F403
```

`tests/sample_package/allexport.py` (`__all__` filters which re-exports alias):
```python
"""Module whose __all__ selects one of two re-exports."""

from .core import CoreClass, core_function  # noqa: F401

__all__ = ["CoreClass"]
```

`tests/sample_package/mod_a.py`:
```python
"""First origin of the colliding name."""


def common() -> str:
    """common from mod_a."""
    return "a"
```

`tests/sample_package/mod_b.py`:
```python
"""Second origin of the colliding name."""


def common() -> str:
    """common from mod_b."""
    return "b"
```

`tests/sample_package/re_a.py`:
```python
"""Re-exports mod_a.common."""

from .mod_a import common  # noqa: F401
```

`tests/sample_package/re_b.py`:
```python
"""Re-exports mod_b.common."""

from .mod_b import common  # noqa: F401
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_scanner.py`:

```python
class TestReexportAliases:
    """Intra-package re-exports become aliases on the canonical symbol."""

    @pytest.fixture(scope="class")
    def scanned(self):
        return scan_package("sample_package")

    def _by_id(self, scanned):
        return {
            (s.module_path, s.qualified_name): s for s in scanned.symbols
        }

    def test_root_reexport_recorded_as_alias(self, scanned):
        symbols = self._by_id(scanned)
        core_class = symbols[("sample_package.core", "CoreClass")]
        assert ("sample_package", "CoreClass") in core_class.aliases

    def test_definition_site_remains_canonical(self, scanned):
        symbols = self._by_id(scanned)
        # No symbol is scanned AT the re-export site
        assert ("sample_package", "CoreClass") not in symbols
        assert ("sample_package", "core_function") not in symbols

    def test_renamed_reexport_uses_alias_name(self, scanned):
        symbols = self._by_id(scanned)
        helper = symbols[("sample_package.extras", "helper")]
        assert ("sample_package", "aliased_helper") in helper.aliases

    def test_star_reexport_without_all_recorded(self, scanned):
        symbols = self._by_id(scanned)
        core_class = symbols[("sample_package.core", "CoreClass")]
        core_function = symbols[("sample_package.core", "core_function")]
        assert ("sample_package.convenience", "CoreClass") in core_class.aliases
        assert (
            "sample_package.convenience",
            "core_function",
        ) in core_function.aliases

    def test_all_filter_limits_aliases(self, scanned):
        symbols = self._by_id(scanned)
        core_class = symbols[("sample_package.core", "CoreClass")]
        core_function = symbols[("sample_package.core", "core_function")]
        assert ("sample_package.allexport", "CoreClass") in core_class.aliases
        # core_function is imported by allexport but excluded from __all__
        assert (
            "sample_package.allexport",
            "core_function",
        ) not in core_function.aliases

    def test_external_reexports_still_skipped(self, scanned):
        symbols = self._by_id(scanned)
        # json.loads is re-exported at the root but is NOT part of the package
        assert ("sample_package", "loads") not in symbols
        for symbol in scanned.symbols:
            for alias_module, alias_name in symbol.aliases:
                assert alias_name != "loads"

    def test_name_collision_keeps_aliases_separate(self, scanned):
        symbols = self._by_id(scanned)
        common_a = symbols[("sample_package.mod_a", "common")]
        common_b = symbols[("sample_package.mod_b", "common")]
        assert ("sample_package.re_a", "common") in common_a.aliases
        assert ("sample_package.re_b", "common") not in common_a.aliases
        assert ("sample_package.re_b", "common") in common_b.aliases
        assert ("sample_package.re_a", "common") not in common_b.aliases

    def test_symbols_without_reexports_have_no_aliases(self, sample_module):
        symbols = scan_module(sample_module)
        assert all(s.aliases == [] for s in symbols)
```

Also add `scan_package` and `scan_module` to the existing import from `lcp.scanner` at the top of the file if not already imported (check `tests/test_scanner.py:7`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_scanner.py::TestReexportAliases -v`
Expected: FAIL — `AttributeError: 'ScannedSymbol' object has no attribute 'aliases'` (or `TypeError` on the fixture) on every test.

- [ ] **Step 4: Implement scanner alias recording**

In `src/lcp/scanner.py`:

(a) Add the field to `ScannedSymbol` (after `source_lines` at :58):
```python
    aliases: list[tuple[str, str]] = field(default_factory=list)
```
And document it in the class docstring: aliases are `(module_path, name)` pairs where the symbol is re-exported inside its own package.

(b) Add after the `ScannedModule` dataclass:
```python
@dataclass
class _AliasRecord:
    """A re-export observed while scanning, before its target is known.

    ``scan_module`` records these when a member's ``__module__`` points at
    another module inside the same package; ``_attach_aliases`` resolves
    them onto the canonical scanned symbols once every module is scanned.
    """

    target_module: str
    target_name: str
    alias_module: str
    alias_name: str


def _attach_aliases(
    symbols: list[ScannedSymbol], records: list[_AliasRecord]
) -> None:
    """Attach re-export aliases to their canonical scanned symbols.

    Records whose target was never scanned (e.g. the defining module failed
    to import, or the object is not a scannable kind) are dropped.
    """
    by_key = {(s.module_path, s.qualified_name): s for s in symbols}
    for rec in records:
        target = by_key.get((rec.target_module, rec.target_name))
        if target is None:
            continue
        alias = (rec.alias_module, rec.alias_name)
        if alias not in target.aliases:
            target.aliases.append(alias)
```

(c) Change `scan_module`'s signature (`:393`) to accept the accumulator:
```python
def scan_module(
    module: ModuleType,
    include_private: bool = False,
    _visited: set | None = None,
    _package_root: str | None = None,
    _alias_records: list[_AliasRecord] | None = None,
) -> list[ScannedSymbol]:
```
At the top of the body (next to the `_visited` init):
```python
    records = _alias_records if _alias_records is not None else []
```

(d) Replace the skip at `:453-457`:
```python
            # Check if this symbol is defined in this module
            obj_module = getattr(obj, "__module__", None)
            if obj_module and obj_module != module_path:
                # Re-exported symbol: documented at its definition site.
                # If the origin is inside the scanned package, record the
                # re-export as an alias on the canonical symbol; external
                # origins stay skipped entirely.
                if isinstance(obj_module, str) and (
                    obj_module == _package_root
                    or obj_module.startswith(_package_root + ".")
                ):
                    target_name = getattr(obj, "__name__", None)
                    if isinstance(target_name, str):
                        records.append(
                            _AliasRecord(
                                target_module=obj_module,
                                target_name=target_name,
                                alias_module=module_path,
                                alias_name=name,
                            )
                        )
                continue
```
(The `inspect.ismodule(obj)` skip above it stays FIRST and unchanged — module re-exports do not alias; module IDs use the empty entity path and an alias would break the grammar.)

(e) At the end of `scan_module`, before `return symbols`:
```python
    if _alias_records is None:
        _attach_aliases(symbols, records)
```

(f) In `scan_package` (`:573-596`): create a shared accumulator, thread it through both `scan_module` calls, and resolve once at the end:
```python
    version = _get_package_version(package_name)
    visited: set = set()
    package_root = package_name.split(".")[0]
    alias_records: list[_AliasRecord] = []

    # Scan main module
    symbols = scan_module(
        module,
        include_private,
        visited,
        _package_root=package_root,
        _alias_records=alias_records,
    )

    # Scan submodules if it's a package
    if recursive and hasattr(module, "__path__"):
        for submod in _iter_submodules(module):
            symbols.extend(
                scan_module(
                    submod,
                    include_private,
                    visited,
                    _package_root=package_root,
                    _alias_records=alias_records,
                )
            )

    _attach_aliases(symbols, alias_records)
    return ScannedModule(name=package_name, version=version, symbols=symbols)
```

- [ ] **Step 5: Run the tests and the full scanner suite**

Run: `pytest tests/test_scanner.py tests/test_scanner_resilient.py -v`
Expected: all PASS (new class green, zero regressions).

- [ ] **Step 6: Commit** (use the `git-commit-convention` skill)

```bash
git add tests/sample_package tests/test_scanner.py src/lcp/scanner.py
git commit  # ADD: Record intra-package re-export aliases in the scanner
```

---

### Task 2: `Symbol.aliases` model field, generator emission, schema files

**Files:**
- Modify: `src/lcp/models.py:162-173` (Symbol), `src/lcp/generator.py:102-128` (`_convert_symbol`), `src/lcp/schema.json` (`$defs/symbol/properties`), `docs/assets/schema.json` (same)
- Test: `tests/test_generator.py`, `tests/test_models.py`, `tests/test_validator.py`

**Interfaces:**
- Consumes: `ScannedSymbol.aliases: list[tuple[str, str]]` from Task 1.
- Produces: `Symbol.aliases: list[str] | None` (full alias IDs, `f"{module}:{name}"`, sorted; `None` when empty). Schema accepts `aliases` as `array<string> | null`. Task 3's index reads `symbol.aliases`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generator.py`:
```python
class TestAliasEmission:
    def test_convert_symbol_emits_sorted_alias_ids(self):
        scanned = ScannedSymbol(
            name="CoreClass",
            qualified_name="CoreClass",
            module_path="sample_package.core",
            kind="class",
            summary="A class.",
            aliases=[
                ("sample_package", "CoreClass"),
                ("sample_package.allexport", "CoreClass"),
            ],
        )
        symbol_id, symbol = _convert_symbol(scanned)
        assert symbol_id == "sample_package.core:CoreClass"
        assert symbol.aliases == [
            "sample_package.allexport:CoreClass",
            "sample_package:CoreClass",
        ]

    def test_convert_symbol_without_aliases_emits_none(self):
        scanned = ScannedSymbol(
            name="f",
            qualified_name="f",
            module_path="m",
            kind="function",
            summary="F.",
        )
        _, symbol = _convert_symbol(scanned)
        assert symbol.aliases is None

    def test_generate_lcp_end_to_end_aliases(self):
        scanned = scan_package("sample_package")
        doc = generate_lcp(scanned)
        core = doc.symbols["sample_package.core:CoreClass"]
        assert "sample_package:CoreClass" in core.aliases
        helper = doc.symbols["sample_package.extras:helper"]
        assert "sample_package:aliased_helper" in helper.aliases
```
(Match existing import style at the top of `tests/test_generator.py`; add `scan_package` from `lcp.scanner` and `ScannedSymbol` if missing.)

Append to `tests/test_validator.py`:
```python
class TestAliasesValidation:
    def test_manifest_with_aliases_validates(self, sample_lcp_dict):
        sample_lcp_dict["symbols"]["test:func"]["aliases"] = ["pkg:func"]
        errors = validate_dict(sample_lcp_dict)
        assert errors == []

    def test_manifest_without_aliases_still_validates(self, sample_lcp_dict):
        errors = validate_dict(sample_lcp_dict)
        assert errors == []

    def test_generated_aliased_manifest_validates(self):
        from lcp.generator import generate_lcp
        from lcp.scanner import scan_package

        doc = generate_lcp(scan_package("sample_package"))
        errors = validate_document(doc)
        assert errors == []
```
(`validate_dict` and `validate_document` are the real names — `src/lcp/validator.py:24` and `:44`; extend the existing `from lcp.validator import (...)` at the top of the test file if they're not already imported.)

Append to `tests/test_models.py` (follow the file's existing style):
```python
def test_symbol_aliases_field_roundtrip():
    symbol = Symbol(
        kind=SymbolKind.FUNCTION,
        semantics=Semantics(summary="S."),
        aliases=["pkg:f"],
    )
    assert symbol.model_dump(exclude_none=True)["aliases"] == ["pkg:f"]


def test_symbol_aliases_default_none():
    symbol = Symbol(kind=SymbolKind.FUNCTION, semantics=Semantics(summary="S."))
    assert symbol.aliases is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_generator.py::TestAliasEmission tests/test_validator.py::TestAliasesValidation tests/test_models.py -v`
Expected: FAIL — `TypeError`/`ValidationError` (`aliases` unknown to the dataclass call is fine from Task 1; `Symbol` has no field; schema rejects the extra property because `$defs/symbol` has `additionalProperties: false`).

- [ ] **Step 3: Implement**

(a) `src/lcp/models.py` — add to `Symbol` after `module`:
```python
    aliases: list[str] | None = None
```
With a docstring line: alternative full symbol IDs where the symbol is re-exported (e.g. `["requests:get"]`); the map key stays the definition site.

(b) `src/lcp/generator.py` — in `_convert_symbol` (:102), before building `symbol`:
```python
    alias_ids = (
        sorted(f"{mod}:{name}" for mod, name in scanned.aliases)
        if scanned.aliases
        else None
    )
```
and pass `aliases=alias_ids` in the `Symbol(...)` constructor call.

(c) `src/lcp/schema.json` — in `$defs.symbol.properties`, after the `"module"` entry, add (2-space indent style of the file):
```json
"aliases": {
  "type": ["array", "null"],
  "items": { "type": "string" }
},
```

(d) `docs/assets/schema.json` — same addition, same position, preserving that file's formatting.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_generator.py tests/test_validator.py tests/test_models.py -v`
Expected: PASS.

Then verify schema copies stay semantically identical:
```bash
python3 -c "import json; print(json.load(open('src/lcp/schema.json'))==json.load(open('docs/assets/schema.json')))"
```
Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add src/lcp/models.py src/lcp/generator.py src/lcp/schema.json docs/assets/schema.json tests/test_generator.py tests/test_validator.py tests/test_models.py
git commit  # ADD: Emit additive Symbol.aliases for re-exported symbols
```

---

### Task 3: Alias-aware `LCPIndex` (lookup layer)

**Files:**
- Modify: `src/lcp/mcp_server.py` — `LCPIndex.__init__`/`_build_indexes` (:75-110), new module-level `_alias_rank`
- Test: `tests/test_mcp_server.py` (extend `TestLCPIndex` or add `TestAliasIndex`)

**Interfaces:**
- Consumes: `Symbol.aliases` from Task 2.
- Produces (used by Task 4):
  - `LCPIndex.alias_to_canonical: dict[str, str]` — alias ID (including expanded member IDs like `pkg:Widget#render`) → canonical ID.
  - `LCPIndex.preferred_alias: dict[str, str]` — canonical ID → best display ID (fewest module dots, then shortest, then lexicographic); absent when the symbol has no aliases. Class members inherit their class's preferred alias (`pkg:Widget#render`).
  - `LCPIndex.resolve_id(symbol_id) -> tuple[str | None, Symbol | None]` — `(canonical_id, symbol)` for direct or alias hits, `(None, None)` otherwise.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mcp_server.py` (reuse the file's fixture style — look at `TestLCPIndex` at :427 for how docs are built):
```python
ALIASED_DOC = {
    "manifest": {
        "schema_version": "1.0",
        "library": {"name": "pkg", "version": "1.0.0", "language": "python"},
    },
    "symbols": {
        "pkg.core:Widget": {
            "kind": "class",
            "module": "pkg.core",
            "semantics": {"summary": "A widget."},
            "aliases": ["pkg:Widget", "pkg.convenience:Widget"],
        },
        "pkg.core:Widget#render": {
            "kind": "method",
            "module": "pkg.core",
            "semantics": {"summary": "Render it."},
        },
        "pkg.core:make": {
            "kind": "function",
            "module": "pkg.core",
            "semantics": {"summary": "Make a widget."},
            "signatures": [{"params": [], "returns": "Widget"}],
            "aliases": ["pkg:make"],
        },
        "pkg.other:plain": {
            "kind": "function",
            "module": "pkg.other",
            "semantics": {"summary": "No aliases."},
        },
    },
}


def _aliased_index():
    return LCPIndex(LCPDocument.model_validate(ALIASED_DOC))


class TestAliasIndex:
    def test_alias_maps_to_canonical(self):
        index = _aliased_index()
        assert index.alias_to_canonical["pkg:Widget"] == "pkg.core:Widget"
        assert index.alias_to_canonical["pkg:make"] == "pkg.core:make"

    def test_member_ids_expanded_for_every_alias(self):
        index = _aliased_index()
        assert (
            index.alias_to_canonical["pkg:Widget#render"]
            == "pkg.core:Widget#render"
        )
        assert (
            index.alias_to_canonical["pkg.convenience:Widget#render"]
            == "pkg.core:Widget#render"
        )

    def test_member_entries_not_materialized(self):
        index = _aliased_index()
        assert "pkg:Widget#render" not in index.symbols_by_id
        assert len(index.symbols_by_id) == 4

    def test_preferred_alias_is_shortest_module_path(self):
        index = _aliased_index()
        assert index.preferred_alias["pkg.core:Widget"] == "pkg:Widget"
        assert (
            index.preferred_alias["pkg.core:Widget#render"]
            == "pkg:Widget#render"
        )
        assert "pkg.other:plain" not in index.preferred_alias

    def test_resolve_id_direct_alias_and_miss(self):
        index = _aliased_index()
        canonical, symbol = index.resolve_id("pkg.core:Widget")
        assert canonical == "pkg.core:Widget" and symbol is not None
        canonical, symbol = index.resolve_id("pkg:Widget")
        assert canonical == "pkg.core:Widget" and symbol is not None
        canonical, symbol = index.resolve_id("pkg:Widget#render")
        assert canonical == "pkg.core:Widget#render"
        assert index.resolve_id("pkg:nope") == (None, None)

    def test_alias_colliding_with_canonical_id_is_ignored(self):
        doc = {
            "manifest": ALIASED_DOC["manifest"],
            "symbols": {
                "pkg:real": {
                    "kind": "function",
                    "module": "pkg",
                    "semantics": {"summary": "The real pkg:real."},
                },
                "pkg.impl:real": {
                    "kind": "function",
                    "module": "pkg.impl",
                    "semantics": {"summary": "Impl."},
                    "aliases": ["pkg:real"],
                },
            },
        }
        index = LCPIndex(LCPDocument.model_validate(doc))
        assert "pkg:real" not in index.alias_to_canonical
        canonical, _ = index.resolve_id("pkg:real")
        assert canonical == "pkg:real"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_server.py::TestAliasIndex -v`
Expected: FAIL with `AttributeError: 'LCPIndex' object has no attribute 'alias_to_canonical'`.

- [ ] **Step 3: Implement**

(a) Module-level helper near `_symbol_name` (:29):
```python
def _alias_rank(alias_id: str) -> tuple[int, int, str]:
    """Order alias ids: fewest module dots, then shortest, then lexicographic.

    The package-root re-export (``requests:get``) is the path users see in
    documentation, so it wins the "preferred alias" slot.
    """
    return (alias_id.split(":")[0].count("."), len(alias_id), alias_id)
```

(b) In `LCPIndex.__init__` (:78-87), add before `self._build_indexes()`:
```python
        self.alias_to_canonical: dict[str, str] = {}
        self.preferred_alias: dict[str, str] = {}
```

(c) At the end of `_build_indexes` (:89-110), after the `classes_by_name` sort loop:
```python
        # Alias indexes (spec D10): alias ids resolve to the canonical
        # entry, and class aliases expand to member ids at build time —
        # without materializing duplicate entries in the manifest.
        for symbol_id, symbol in self.symbols_by_id.items():
            aliases = [
                a
                for a in (symbol.aliases or [])
                if a not in self.symbols_by_id
            ]
            if not aliases:
                continue
            for alias in aliases:
                self.alias_to_canonical.setdefault(alias, symbol_id)
            preferred = min(aliases, key=_alias_rank)
            self.preferred_alias[symbol_id] = preferred
            if symbol.kind == SymbolKind.CLASS:
                for member_id in self.class_members.get(symbol_id, []):
                    entity = member_id.split("#", 1)[1]
                    for alias in aliases:
                        self.alias_to_canonical.setdefault(
                            f"{alias}#{entity}", member_id
                        )
                    self.preferred_alias[member_id] = f"{preferred}#{entity}"
```

(d) New method on `LCPIndex`:
```python
    def resolve_id(self, symbol_id: str) -> tuple[str | None, Symbol | None]:
        """Resolve a possibly-aliased id to ``(canonical_id, symbol)``.

        Returns ``(None, None)`` when the id matches neither a canonical
        entry nor a known alias.
        """
        symbol = self.symbols_by_id.get(symbol_id)
        if symbol is not None:
            return symbol_id, symbol
        canonical = self.alias_to_canonical.get(symbol_id)
        if canonical is not None:
            return canonical, self.symbols_by_id[canonical]
        return None, None
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS (new class green, existing index tests untouched).

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit  # ADD: Index re-export aliases with build-time member expansion
```

---

### Task 4: Alias-first responses in `search` / `get_symbol`

**Files:**
- Modify: `src/lcp/mcp_server.py` — `_symbol_summary` (:561-568), `_search_index` (:571-657), `_symbol_detail` (:704-778), `_get_symbols` (:781-827), `_resolve_type_to_classes` call site inside `_symbol_detail`
- Test: `tests/test_mcp_server.py` (new `TestAliasResponses`, plus one end-to-end test via `scan_package("sample_package")`)

**Interfaces:**
- Consumes: `alias_to_canonical`, `preferred_alias`, `resolve_id` from Task 3.
- Produces (documented behavior the plugin skills and docs describe in Task 6):
  - search hit: `{id: <preferred alias or canonical>, kind, summary, import, resolved_via_alias?: <canonical>}`; query matches alias names too; browse mode sorts by display name.
  - `get_symbol` entry: `id` echoes the *requested* ID; `resolved_via_alias: <canonical>` when requested via alias; `import` always uses the preferred importable path; class members listed with the display ID's prefix; `usage_hints.returns_classes` lists display IDs.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mcp_server.py` (reuses `ALIASED_DOC`/`_aliased_index` from Task 3):
```python
class TestAliasResponses:
    def test_search_hit_presents_preferred_alias(self):
        index = _aliased_index()
        result = _search_index(index, "widget")
        widget = next(
            r for r in result["results"] if r["kind"] == "class"
        )
        assert widget["id"] == "pkg:Widget"
        assert widget["resolved_via_alias"] == "pkg.core:Widget"
        assert widget["import"] == "from pkg import Widget"

    def test_search_hit_without_alias_is_unmarked(self):
        index = _aliased_index()
        result = _search_index(index, "plain")
        (hit,) = result["results"]
        assert hit["id"] == "pkg.other:plain"
        assert "resolved_via_alias" not in hit

    def test_search_matches_renamed_alias_name(self):
        doc = {
            "manifest": ALIASED_DOC["manifest"],
            "symbols": {
                "pkg.extras:helper": {
                    "kind": "function",
                    "module": "pkg.extras",
                    "semantics": {"summary": "Helps."},
                    "aliases": ["pkg:aliased_helper"],
                },
            },
        }
        index = LCPIndex(LCPDocument.model_validate(doc))
        result = _search_index(index, "aliased_helper")
        (hit,) = result["results"]
        assert hit["id"] == "pkg:aliased_helper"
        assert hit["resolved_via_alias"] == "pkg.extras:helper"

    def test_get_symbol_via_alias_echoes_requested_id(self):
        index = _aliased_index()
        result = _get_symbols(index, ["pkg:Widget"])
        (entry,) = result["symbols"]
        assert entry["id"] == "pkg:Widget"
        assert entry["resolved_via_alias"] == "pkg.core:Widget"
        assert entry["import"] == "from pkg import Widget"
        assert result["not_found"] == []

    def test_get_symbol_canonical_keeps_canonical_id(self):
        index = _aliased_index()
        result = _get_symbols(index, ["pkg.core:Widget"])
        (entry,) = result["symbols"]
        assert entry["id"] == "pkg.core:Widget"
        assert "resolved_via_alias" not in entry
        # import still prefers the documented path (F2)
        assert entry["import"] == "from pkg import Widget"
        assert entry["aliases"] == ["pkg:Widget", "pkg.convenience:Widget"]

    def test_get_symbol_alias_member_id_resolves(self):
        index = _aliased_index()
        result = _get_symbols(index, ["pkg:Widget#render"])
        (entry,) = result["symbols"]
        assert entry["id"] == "pkg:Widget#render"
        assert entry["resolved_via_alias"] == "pkg.core:Widget#render"
        assert result["not_found"] == []

    def test_class_members_prefixed_with_display_id(self):
        index = _aliased_index()
        via_alias = _get_symbols(index, ["pkg:Widget"])["symbols"][0]
        assert [m["id"] for m in via_alias["members"]] == [
            "pkg:Widget#render"
        ]
        canonical = _get_symbols(index, ["pkg.core:Widget"])["symbols"][0]
        assert [m["id"] for m in canonical["members"]] == [
            "pkg.core:Widget#render"
        ]

    def test_returns_classes_use_display_ids(self):
        index = _aliased_index()
        (entry,) = _get_symbols(index, ["pkg.core:make"])["symbols"]
        assert entry["usage_hints"]["returns_classes"] == ["pkg:Widget"]

    def test_unknown_id_still_not_found(self):
        index = _aliased_index()
        result = _get_symbols(index, ["pkg:nothing"])
        assert result["not_found"] == ["pkg:nothing"]


class TestAliasEndToEnd:
    def test_scanned_package_resolves_root_alias(self):
        from lcp.generator import generate_lcp
        from lcp.scanner import scan_package

        doc = generate_lcp(scan_package("sample_package"))
        index = LCPIndex(doc)
        result = _get_symbols(index, ["sample_package:CoreClass"])
        (entry,) = result["symbols"]
        assert entry["resolved_via_alias"] == "sample_package.core:CoreClass"
        assert entry["import"] == "from sample_package import CoreClass"
        member = _get_symbols(index, ["sample_package:CoreClass#do_something"])
        assert member["not_found"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_server.py::TestAliasResponses tests/test_mcp_server.py::TestAliasEndToEnd -v`
Expected: FAIL — hits carry canonical ids, alias lookups land in `not_found`.

- [ ] **Step 3: Implement**

(a) `_symbol_summary` (:561) becomes index-aware:
```python
def _symbol_summary(
    index: LCPIndex, symbol_id: str, symbol: Symbol
) -> dict[str, Any]:
    """Create a compact search/browse hit for a symbol (spec D4/D10).

    Presents the preferred importable id; alias hits carry
    ``resolved_via_alias`` pointing at the canonical definition site.
    """
    display_id = index.preferred_alias.get(symbol_id, symbol_id)
    hit = {
        "id": display_id,
        "kind": symbol.kind.value,
        "summary": symbol.semantics.summary,
        "import": _import_statement(display_id, symbol.kind),
    }
    if display_id != symbol_id:
        hit["resolved_via_alias"] = symbol_id
    return hit
```
Update its call site in `_search_index` (:649-651) to `_symbol_summary(index, sid, index.symbols_by_id[sid])`.

(b) In `_search_index` scoring loop (:625-644), match alias names too:
```python
        scored: list[tuple[int, str]] = []
        for sid in candidates:
            symbol = index.symbols_by_id[sid]
            names = {_symbol_name(sid).lower()}
            names.update(
                _symbol_name(a).lower() for a in (symbol.aliases or [])
            )
            if q in names:
                score = 0
            elif any(n.startswith(q) for n in names):
                score = 1
            elif any(q in n for n in names):
                score = 2
            elif q in symbol.semantics.summary.lower():
                score = 3
            elif (
                symbol.semantics.description
                and q in symbol.semantics.description.lower()
            ):
                score = 4
            else:
                continue
            scored.append((score, sid))
```
And the browse-mode sort key (:616-623) uses the display name:
```python
        ranked = sorted(
            candidates,
            key=lambda sid: (
                index.symbols_by_id[sid].kind.value,
                _symbol_name(index.preferred_alias.get(sid, sid)).lower(),
                sid,
            ),
        )
```

(c) `_symbol_detail` (:704) gains `requested_id`:
```python
def _symbol_detail(
    index: LCPIndex,
    symbol_id: str,
    symbol: Symbol,
    max_bytes: int,
    requested_id: str | None = None,
) -> dict[str, Any]:
```
`symbol_id` is always canonical. Replace the two lines at :715-716:
```python
    display_id = requested_id if requested_id is not None else symbol_id
    result["id"] = display_id
    if display_id != symbol_id:
        result["resolved_via_alias"] = symbol_id
    import_id = index.preferred_alias.get(symbol_id, display_id)
    result["import"] = _import_statement(import_id, symbol.kind)
```
In the `usage_hints` block, map `returns_classes` to display ids (replace the `returns_classes` assignment at :735-739):
```python
            returns_classes = sorted(
                index.preferred_alias.get(c, c)
                for c in _resolve_type_to_classes(index, hints["return_type"])
            )
```
(the `hints["next"]` line below it keeps using `returns_classes[0]` — unchanged).
In the class-members block (:758-777), prefix members with the display id and use it in the hint:
```python
    if symbol.kind == SymbolKind.CLASS:
        member_ids = sorted(index.class_members.get(symbol_id, []))
        members = [
            {
                "id": f"{display_id}#{mid.split('#', 1)[1]}",
                "kind": index.symbols_by_id[mid].kind.value,
                "summary": index.symbols_by_id[mid].semantics.summary,
            }
            for mid in member_ids
        ]
        member_budget = max(0, max_bytes - body_size - slack)
        members, truncated = _fit_list(members, member_budget)
        result["members"] = members
        if truncated:
            result["members_truncated"] = True
            result["members_hint"] = (
                "Member list truncated. Use search('<member name>', "
                f"module='{symbol.module}') or get_symbol on "
                f"'{display_id}#<member>' for the rest."
            )
```

(d) `_get_symbols` loop (:797-804) resolves through aliases:
```python
    details: list[dict[str, Any]] = []
    not_found: list[str] = []
    for requested in ids:
        canonical, symbol = index.resolve_id(requested)
        if symbol is None:
            not_found.append(requested)
        else:
            details.append(
                _symbol_detail(
                    index, canonical, symbol, max_bytes, requested_id=requested
                )
            )
```
Note: `result["not_returned"]` at :820 uses `d["id"]` — still correct (echoed ids are resolvable ids).

(e) `get_symbol`'s tool docstring (:1085-1108) — append one line to the first paragraph: `Re-exported symbols resolve under both their canonical id and their documented import path (aliases); alias answers carry resolved_via_alias.`

- [ ] **Step 4: Run the full main suite**

Run: `pytest`
Expected: all PASS (fix any `_symbol_summary` signature fallout — it has exactly one call site; `grep -n "_symbol_summary" src tests` to confirm).

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit  # UPD: Serve alias-first ids in search and get_symbol responses
```

---

### Task 5: Harness co-fix — alias-aware `symbol_used` + `rescore` subcommand

**Files:**
- Modify: `evals/harness/verify.py` (whole `resolve_dotted`/`symbol_used` area, :9-56), `evals/run.py` (new `rescore` subcommand), `evals/README.md` (document `rescore`)
- Test: `evals/tests/test_verify.py`, new `evals/tests/test_rescore.py`

**Interfaces:**
- Consumes: nothing from `src/lcp/` (the harness verifies via live introspection, deliberately independent of the manifest).
- Produces: `symbol_used` accepts any used dotted path that resolves to the *same live object* as the canonical path (re-export aliases). `run.py rescore --src OLD --out NEW [--cases DIR]` re-verifies stored runs with the current verifier and re-aggregates.

**Run all steps in this task with `evals/.venv/bin/python -m pytest` — NOT the main venv.**

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_verify.py` (match its existing imports/style):
```python
class TestSymbolUsedAliases:
    def test_reexport_alias_path_accepted(self):
        # The Phase 2b jupiter-swap repro: canonical id is
        # cyhole.jupiter.interaction:Jupiter, agents write the valid
        # package-level re-export import.
        usage = extract.extract_usage(
            "from cyhole.jupiter import Jupiter\nj = Jupiter()",
            "cyhole",
        )
        assert verify.symbol_used("cyhole.jupiter.interaction:Jupiter", usage)

    def test_canonical_path_still_accepted(self):
        usage = extract.extract_usage(
            "from cyhole.jupiter.interaction import Jupiter\nj = Jupiter()",
            "cyhole",
        )
        assert verify.symbol_used("cyhole.jupiter.interaction:Jupiter", usage)

    def test_different_object_same_root_not_matched(self):
        usage = extract.extract_usage(
            "from cyhole.solscan import Solscan\ns = Solscan()",
            "cyhole",
        )
        assert not verify.symbol_used(
            "cyhole.jupiter.interaction:Jupiter", usage
        )

    def test_stdlib_alias_identity(self):
        # os.path.join IS posixpath.join on this platform — identity match.
        usage = extract.extract_usage(
            "import os.path\nos.path.join('a', 'b')", "os"
        )
        assert verify.symbol_used("posixpath:join", usage)

    def test_unresolvable_symbol_never_matches(self):
        usage = extract.extract_usage("import cyhole\ncyhole.x()", "cyhole")
        assert not verify.symbol_used("cyhole:does_not_exist_at_all", usage)
```

Create `evals/tests/test_rescore.py`:
```python
"""rescore re-verifies stored runs with the current verifier."""

import json
import subprocess
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]

CASE_YAML = """\
- id: json-loads
  library: json
  version: "X"
  prompt: parse JSON
  checks:
    required_symbols: ["json:loads"]
"""


def test_rescore_recomputes_verification(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "json.yaml").write_text(CASE_YAML)

    src = tmp_path / "old"
    (src / "runs").mkdir(parents=True)
    stale = {
        "case_id": "json-loads",
        "arm": "lcp",
        "rep": 1,
        "code": "import json\njson.loads('1')",
        "verification": {
            "passed": False,
            "misuse_count": 9,
            "required_missing": ["json:loads"],
            "forbidden_used": [],
            "unresolved_usages": [],
            "error": None,
        },
    }
    (src / "runs" / "json-loads_lcp_r1.json").write_text(json.dumps(stale))

    out = tmp_path / "new"
    proc = subprocess.run(
        [
            sys.executable,
            str(EVALS_DIR / "run.py"),
            "rescore",
            "--src", str(src),
            "--out", str(out),
            "--cases", str(cases_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    rescored = json.loads((out / "runs" / "json-loads_lcp_r1.json").read_text())
    assert rescored["verification"]["passed"] is True
    assert rescored["verification"]["required_missing"] == []
    assert (out / "summary.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `evals/.venv/bin/python -m pytest evals/tests/test_verify.py::TestSymbolUsedAliases evals/tests/test_rescore.py -v`
Expected: alias tests FAIL (assert False on the re-export path); rescore test FAILS (`argparse` error: invalid choice 'rescore').

- [ ] **Step 3: Implement the verifier**

Rewrite the top of `evals/harness/verify.py` (:9-56) as:
```python
_UNRESOLVED = object()


def _resolve_object(path: str):
    """Resolve a dotted path to the live object, or ``_UNRESOLVED``.

    Tries the longest importable module prefix, then getattr-walks the rest.
    Any exception during import or attribute access counts as unresolved.
    """
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except Exception:
            continue
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except Exception:
            return _UNRESOLVED
        return obj
    return _UNRESOLVED


def resolve_dotted(path: str) -> bool:
    """Return True if a dotted path like 'polars.DataFrame.group_by' resolves."""
    return _resolve_object(path) is not _UNRESOLVED


def resolve_symbol(symbol_id: str) -> bool:
    """Return True if an LCP symbol id resolves.

    Formats: 'module:entity' (e.g. 'json:loads') and 'module:Class#method'
    (e.g. 'pathlib:Path#resolve'). A bare 'module' (no colon) is also accepted.
    """
    module, _, entity = symbol_id.partition(":")
    if not entity:
        return resolve_dotted(module)
    return resolve_dotted(f"{module}.{entity.replace('#', '.')}")


def symbol_used(symbol_id: str, usage: "extract.CodeUsage") -> bool:
    """Return True if the generated code uses this symbol.

    'module:Class#method' matches by method name on any receiver (static
    analysis cannot type the receiver) or by full dotted path.
    'module:entity' matches the canonical dotted path, or ANY used dotted
    path that resolves to the same live object — so valid re-export
    aliases (e.g. `from cyhole.jupiter import Jupiter` for
    cyhole.jupiter.interaction:Jupiter) count as usage.
    """
    module, _, entity = symbol_id.partition(":")
    if "#" in entity:
        cls, _, method = entity.partition("#")
        if method in usage.method_names:
            return True
        canonical = f"{module}.{cls}.{method}"
    else:
        canonical = f"{module}.{entity}" if entity else module
    if canonical in usage.dotted_paths:
        return True
    target = _resolve_object(canonical)
    if target is _UNRESOLVED:
        return False
    return any(_resolve_object(p) is target for p in usage.dotted_paths)
```

- [ ] **Step 4: Implement `rescore` in `evals/run.py`**

Add after `cmd_report` (:153-154):
```python
def cmd_rescore(args) -> int:
    """Re-verify stored runs with the CURRENT verifier into a new dir.

    Copies each <src>/runs/*.json record, recomputes its "verification"
    against the (unchanged) generated code, and re-aggregates. Use when the
    verifier changes (e.g. Phase 3 alias awareness) to separate "the
    verifier got fairer" from "the server got better".
    """
    loaded = {c.id: c for c in cases.load_cases(args.cases)}
    src = Path(args.src)
    out = Path(args.out)
    runs_dir = out / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for run_file in sorted((src / "runs").glob("*.json")):
        record = json.loads(run_file.read_text())
        case = loaded.get(record["case_id"])
        if case is None:
            print(f"SKIP     {run_file.name} (unknown case id)")
            continue
        record["verification"] = asdict(
            verify.verify_code(record.get("code"), case)
        )
        record["rescored_from"] = str(src)
        (runs_dir / run_file.name).write_text(json.dumps(record, indent=2))
        status = "PASS" if record["verification"]["passed"] else "FAIL"
        print(f"{status:8}{run_file.name}")
    return _report(out)
```
And register it in `main()` next to the other subparsers:
```python
    p_rescore = sub.add_parser(
        "rescore", help="re-verify an existing results dir with the current verifier"
    )
    p_rescore.add_argument("--src", required=True)
    p_rescore.add_argument("--out", required=True)
    p_rescore.add_argument("--cases", type=Path, default=EVALS_DIR / "cases")
    p_rescore.set_defaults(func=cmd_rescore)
```

- [ ] **Step 5: Run the harness test suite**

Run: `evals/.venv/bin/python -m pytest evals/tests -v`
Expected: all PASS (including the pre-existing verify/extract/report tests).

Also re-validate the case files (required symbols must still resolve, forbidden must not — the verifier change must not break the traps):
Run: `evals/.venv/bin/python evals/run.py validate`
Expected: `28 cases, 0 problems`

- [ ] **Step 6: Update `evals/README.md`**

In the Commands section, add after the `report` example:
```bash
# Re-verify an existing results dir with the current verifier (no agent runs).
evals/.venv/bin/python evals/run.py rescore --src evals/results/<old> \
    --out evals/results/<old>-rescored [--cases evals/cases]
```
And in "Methodology and caveats", append one sentence to the verification paragraph: `symbol_used` accepts any used dotted path that resolves (live introspection) to the same object as the required symbol's canonical path, so valid re-export imports count as usage; `rescore` exists to re-score older results dirs when the verifier changes.

- [ ] **Step 7: Commit**

```bash
git add evals/harness/verify.py evals/run.py evals/tests/test_verify.py evals/tests/test_rescore.py evals/README.md
git commit  # UPD: Teach the eval verifier re-export aliases and add rescore
```

---

### Task 6: Docs alignment (same-phase, per the docs-alignment rule)

**Files:**
- Modify: `docs/spec/index.md` (symbol identity section ~:128, symbols object section ~:91), `docs/spec/schema.md` (symbol table :42-53), `docs/guides/mcp-server.md`, `plugin/lcp/skills/lcp-universal/SKILL.md`, `plugin/lcp/skills/lcp-usage/SKILL.md`, `docs/architecture/manifest/architecture.md`, `docs/architecture/mcp_server/architecture.md`
- Verify: `mkdocs build --strict`

**REQUIRED SUB-SKILL: invoke `lcp-writing-documentation` before editing** — it is the authority on which conventions apply per area (spec/guides = user-facing kebab-case with examples; architecture = conceptual, no code snippets). The bullets below say WHAT must land where; the skill says HOW.

- [ ] **Step 1: Invoke the `lcp-writing-documentation` skill and read the target files**

- [ ] **Step 2: Spec pages**

- `docs/spec/schema.md` — add one row to the symbol-object table (after `module`):
  `| aliases | array<string> \| null | no | Alternative full Symbol IDs where the symbol is re-exported inside its own package (e.g. requests:get for a symbol defined in requests.api). The map key remains the definition site. |`
- `docs/spec/index.md` — in the Symbol ID section (~:128), add a short "Re-export aliases" subsection: canonical ID stays the definition site (stability rule unchanged); `aliases` lists the documented import paths; consumers should treat an alias as resolving to the same symbol; alias IDs follow the same `module_path:entity_path` grammar; class-member alias IDs (`pkg:Widget#render`) are derivable and need not be materialized. Include one short JSON example (spec pages carry examples).

- [ ] **Step 3: MCP guide + plugin skills**

- `docs/guides/mcp-server.md` — where `search`/`get_symbol` responses are described, document: hits/entries present the preferred importable ID; `resolved_via_alias` names the canonical definition site; both IDs work in `get_symbol`, including `#member` forms.
- `plugin/lcp/skills/lcp-universal/SKILL.md` — in "The 3-call workflow" `get_symbol` bullet, add one sentence: symbols re-exported at package level resolve under both the documented import path and the canonical id (`resolved_via_alias` names the definition site); the `import` line is always the documented path — copy it as-is.
- `plugin/lcp/skills/lcp-usage/SKILL.md` — mirror the same fact wherever it explains ids/responses (read it first; keep the edit minimal).

- [ ] **Step 4: Architecture docs (conceptual, no code snippets)**

- `docs/architecture/manifest/architecture.md` — document the aliases data flow: scanner records intra-package re-exports → generator emits additive `aliases` → definition site remains canonical.
- `docs/architecture/mcp_server/architecture.md` — document the alias index: alias→canonical map, build-time member expansion, alias-first presentation with `resolved_via_alias` provenance.

- [ ] **Step 5: Build strict and fix anything it flags**

Run: `pip show mkdocs >/dev/null 2>&1 || pip install -e ".[docs]"; mkdocs build --strict`
Expected: `Documentation built` with zero warnings.

- [ ] **Step 6: Commit**

```bash
git add docs/spec docs/guides plugin/lcp/skills docs/architecture
git commit  # DOC: Document re-export aliases across spec, guides and skills
```

---

### Task 7: Verification sweep

- [ ] **Step 1: Full main suite from the project venv**

Run: `pytest`
Expected: 461+ tests, all PASS.

- [ ] **Step 2: Harness suite from the evals venv**

Run: `evals/.venv/bin/python -m pytest evals/tests -v && evals/.venv/bin/python evals/run.py validate`
Expected: all PASS; `28 cases, 0 problems`.

- [ ] **Step 3: Live smoke of the exit criterion (the `requests:get` equivalent)**

```bash
python3 - <<'EOF'
import sys
sys.path.insert(0, "tests")
from lcp.generator import generate_lcp
from lcp.scanner import scan_package
from lcp.mcp_server import LCPIndex, _get_symbols, _search_index

index = LCPIndex(generate_lcp(scan_package("sample_package")))
entry = _get_symbols(index, ["sample_package:CoreClass"])["symbols"][0]
assert entry["resolved_via_alias"] == "sample_package.core:CoreClass", entry
assert entry["import"] == "from sample_package import CoreClass", entry
hit = _search_index(index, "CoreClass")["results"][0]
assert hit["id"] == "sample_package:CoreClass", hit
print("alias smoke OK:", entry["id"], "->", entry["resolved_via_alias"])
EOF
```
Expected: `alias smoke OK: sample_package:CoreClass -> sample_package.core:CoreClass`

If the evals venv is reachable, also smoke the real repro against the editable install:
```bash
evals/.venv/bin/python -c "
from lcp.generator import generate_lcp
from lcp.scanner import scan_package
from lcp.mcp_server import LCPIndex, _get_symbols
index = LCPIndex(generate_lcp(scan_package('cyhole')))
r = _get_symbols(index, ['cyhole.jupiter:Jupiter'])
assert r['not_found'] == [], r
print('cyhole alias OK:', r['symbols'][0]['resolved_via_alias'])
"
```
Expected: `cyhole alias OK: cyhole.jupiter.interaction:Jupiter`

- [ ] **Step 4: Fix anything that surfaced, then commit if changes were needed** (use `git-commit-convention`; no commit if clean).

---

### Task 8: Eval re-run + rescore + roadmap bookkeeping

**Context:** the phase's expected "clearest accuracy delta" (roadmap exit criteria). Two measurements, kept apart so the log doesn't conflate them:
- **(a) Rescore** of `evals/results/2026-07-03-phase2b-skill/` with the alias-aware verifier → quantifies how much of the old failure count was verifier blindness (prediction from its analysis.md: jupiter-swap +3/12 cyhole passes, code unchanged).
- **(b) Fresh `lcp-skill` run** on the same 8 F1 cases (4 fastmcp + 4 cyhole), 3 reps, pinned haiku — measures the shipped alias-aware server end-to-end. lcp is installed editable in `evals/.venv`, so the checked-out branch (`roadmap/phase-3-reexport-aliases`) IS the measured server — verify with `git branch --show-current` before launching (the Phase 2b mis-based-branch incident is in the results meta note).

- [ ] **Step 1: Rescore Phase 2b Exp1**

```bash
evals/.venv/bin/python evals/run.py rescore \
  --src evals/results/2026-07-03-phase2b-skill \
  --out evals/results/2026-07-06-phase2b-skill-rescored
```
Expected: 24 runs rescored; cyhole passes rise from 7/12 (check `report.md`; the 3 jupiter-swap failures should flip to PASS; fastmcp numbers should not move, its failures were non-engagement, not alias mismatches).

- [ ] **Step 2: Clear the scan cache and run the Phase 3 measurement**

The LCP arm caches manifests under `evals/.lcp-cache/` — stale pre-alias manifests would silently serve; remove the cache first:
```bash
rm -rf evals/.lcp-cache
git branch --show-current   # MUST print roadmap/phase-3-reexport-aliases
claude --version            # record for meta.json
evals/.venv/bin/python evals/run.py run \
  --out evals/results/2026-07-06-phase3-aliases-skill \
  --arms lcp-skill --reps 3 \
  --case-id fastmcp-server-tool --case-id fastmcp-resource \
  --case-id fastmcp-client --case-id fastmcp-context \
  --case-id cyhole-birdeye-price --case-id cyhole-jupiter-swap \
  --case-id cyhole-rugcheck-report --case-id cyhole-missing-api-key
```
(24 runs, ~2 workers; resumable with the same `--out` if interrupted.)

- [ ] **Step 3: Write `meta.json` + `analysis.md` in the new results dir**

`meta.json` mirrors the Phase 2b format (`evals/results/2026-07-03-phase2b-skill/meta.json`): experiment name, date 2026-07-06, `claude_version` from Step 2, model `claude-haiku-4-5-20251001`, `lcp_commit` (current HEAD short SHA + "Phase 3 aliases"), arm, the 8 case ids, reps 3, and references: the 2026-07-03 phase2b-skill dir AND the rescored dir as the fair baseline.

`analysis.md` answers, with per-case numbers from `runs/`/`summary.json`:
1. cyhole pass rate vs the RESCORED baseline (does the server-side fix add anything beyond the verifier fix — e.g. do agents now copy the alias id/import directly from responses?).
2. jupiter-swap specifically: do engaged runs still fetch the canonical and write the root import, and does it now count? What id form do `get_symbol` calls use (`tool_call_details`)?
3. fastmcp engagement (calls/run) vs 1.42 — should be flat (aliases don't touch adoption); flag if it moved >±0.5 as noise/regression signal.
4. Any new `required_missing`/`unresolved_usages` patterns.

- [ ] **Step 4: Commit the results**

```bash
git add evals/results/2026-07-06-phase2b-skill-rescored evals/results/2026-07-06-phase3-aliases-skill
git commit  # UPD: Record Phase 3 alias eval (rescore + lcp-skill re-run)
```

- [ ] **Step 5: Update the roadmap and commit (force-add)**

In `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md`:
- Phase 3 **Status** line → `done (2026-07-06) — plan: docs/superpowers/plans/2026-07-06-phase-3-reexport-aliases.md. Shipped: ...` (one-paragraph summary: scanner aliases, additive Symbol.aliases under schema 1.0, alias-first index/responses with resolved_via_alias, harness co-fix + rescore, docs; headline eval numbers).
- **Eval results log**: two new rows (rescored phase2b baseline; phase3 lcp-skill run) following the existing column format.
- If the eval contradicts expectations (e.g. no delta beyond the rescore), record that honestly per the roadmap's gate rule — the phase still ships (correctness fix), but the log must say what moved and what didn't.

```bash
git add -f docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md docs/superpowers/plans/2026-07-06-phase-3-reexport-aliases.md
git commit  # UPD: Record Phase 3 eval results and close the phase in the roadmap
```

---

### Task 9: Finish the branch

- [ ] **Step 1: REQUIRED SUB-SKILL — `superpowers:verification-before-completion`**: re-run `pytest`, `evals/.venv/bin/python -m pytest evals/tests`, `mkdocs build --strict`; confirm `git status` clean.

- [ ] **Step 2: Push and open the PR** (REQUIRED SUB-SKILL: `superpowers:finishing-a-development-branch`)

```bash
git push -u origin roadmap/phase-3-reexport-aliases
gh pr create --base roadmap/agentic-improvements \
  --title "CODE: Re-export aliases (Phase 3)" \
  --body "..."
```
PR body: summary of the alias pipeline (scanner → aliases field → alias-aware index/responses), the harness co-fix rationale (Phase 2b evidence), eval headline numbers, and the exit-criteria checklist. **NO session links, NO co-author lines** (public repo).

---

## Self-Review Notes

- Spec coverage: scanner hook (roadmap :465-468 → Task 1); additive field + schema both files + validate old/new (:469, :515, :522 → Task 2); index + alias hits marked (:469-472 → Tasks 3-4); all six edge cases (`__all__`, star-no-`__all__`, `as`-rename, class members via both ids, collisions, external skip → Tasks 1, 3, 4 tests); fixture package (:477-478 → Task 1); harness co-fix (:508-511 → Task 5); docs-alignment rule (→ Task 6); eval re-run recorded, lcp-skill arm on cyhole vs phase2b-skill, claude --version in meta (→ Task 8); exit criteria `get_symbol("requests:get")`-equivalent resolves (→ Task 7 smoke + Task 4 e2e).
- Out of scope (per roadmap): ID rewriting to re-export sites; registry `latest.json`; module aliases (empty-entity-path grammar conflict — documented in Task 1 Step 4d); search `module=` filter matching alias modules (browse of a re-exporting module lists only its own definitions — noted as future work, not required by any listed edge case).
- Type consistency check: `ScannedSymbol.aliases: list[tuple[str, str]]` (Task 1) → consumed by `_convert_symbol` (Task 2); `Symbol.aliases: list[str] | None` (Task 2) → consumed by `_build_indexes` (Task 3); `resolve_id` tuple return (Task 3) → consumed by `_get_symbols` (Task 4); `_symbol_summary(index, sid, symbol)` new arity has exactly one call site (`_search_index`).
