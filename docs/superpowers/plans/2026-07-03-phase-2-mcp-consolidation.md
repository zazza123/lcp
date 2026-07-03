# Phase 2 — MCP Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current 11-tool MCP surface with the 4-tool V2 surface (resolve_library → search → get_symbol, plus get_overview) designed in `docs/superpowers/specs/2026-07-03-v2-surface-design.md`, deduplicating the two servers into one registration path, migrating the FastMCP pin to `>=3.0,<4`, and updating plugin skills + user docs — then re-run the eval harness gating on tool *adoption* (F1).

**Architecture:** One `_register_tools()` function registers the four tools on a `FastMCP` instance against a `MultiLibraryIndex`; both `lcp serve-all` and the deprecated `lcp serve` build the same server (serve = universal server with the manifest pre-loaded and `expose` locked to it). Tool logic lives in pure module-level functions (`_search_index`, `_get_symbols`, `_overview`) operating on `LCPIndex`, so ranking/caps/batching are unit-testable without MCP. Servers are returned as an `LCPServer` dataclass (`mcp`, `index`, `tools`) — the `tools` dict of raw callables replaces the `mcp.tool_funcs` attribute-stuffing and is what tests and the preload loop use.

**Tech Stack:** Python ≥3.10, FastMCP `>=3.0,<4` (installed: 3.4.2 in `.venv`), Pydantic v2, pytest, Click, MkDocs.

## Global Constraints

- Python `>=3.10`; core deps stay `pydantic>=2`, `click>=8`, `jsonschema>=4`; FastMCP pin becomes `fastmcp>=3.0,<4` (spec D0). No other new runtime deps.
- LCP schema version stays `"1.0"`; this phase changes **no** manifest fields (D12).
- Every tool returns a **structured error dict** on failure: `{"error": {"code": ..., "message": ..., "hint": ..., <extras>}}` — never FastMCP `ToolError` for recoverable conditions (D5).
- `library` is **required** when ≥2 libraries are loaded → `code: "ambiguous_library"` listing `loaded_libraries`; with exactly 1 loaded it may be omitted; the "last-resolved implicit default" is removed (D7).
- Byte cap: `DEFAULT_MAX_RESPONSE_BYTES = 25_000` on every list-returning payload, configurable via `create_universal_server(max_response_bytes=...)` and `lcp serve-all --max-response-bytes`. Calibrated 2026-07-03 against polars 1.42.1: `DataFrame` has 159 members ≈ 30 KB of member summaries alone — the cap is real, and 25 KB ≈ 6 k tokens ≈ 3 % of a 200 k context (D6).
- `search` default `limit=20`, clamped to `1..100`, `"truncated": true` when capped (by limit or by bytes) (D4/D6).
- Member summaries inline in class `get_symbol` responses carry `{id, kind, summary}` **without** a per-member `import` field — deviation from D4's letter, rationale: a member's import line is identical to the class's `import` field one level up, and repeating it 159× on DataFrame costs ~7 KB of the 25 KB budget for zero information.
- Commits follow the `git-commit-convention` skill (`ACTION(scope): Title`); **no Co-Authored-By / session links** (public repo).
- Docs changes in Tasks 10 use the `lcp-writing-documentation` skill (architecture vs guides conventions).
- Run the main suite from the project venv: `.venv/bin/python -m pytest tests/ -q`. Known pre-existing env-dependent failure: `tests/test_cli.py::TestPublishCommand::test_publish_no_token` fails when `LCP_GITHUB_TOKEN` is set in the shell — run that file with `env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN` when you need it green.
- `docs/superpowers/` is gitignored — plan/roadmap commits need `git add -f`.

## Design deltas settled by this plan (within the spec's freedom)

- **`list_libraries` is removed too** (D1 says *four* tools). Discovery of loaded libraries moves to: the `ambiguous_library`/`library_not_loaded` error payloads (`loaded_libraries` key) and the `resolve_library` response.
- **`lcp serve MANIFEST`** keeps its argument (a manifest *path*, not a package name): it becomes "universal server with this manifest pre-loaded into the index and `expose` locked to its library name" + `DeprecationWarning`. That is the D8 "thin alias" adapted to the existing argument shape.
- **`resolve_library` gains `version: str | None`** (D1 signature). Semantics: `version` overrides the installed version for cache lookup and registry fetch; live scan still returns whatever is installed; if the resolved document's version differs from the requested one, the response carries `"warning": {"code": "version_mismatch", ...}` (feeds D4's "version-mismatch flags" in `get_overview` via the stored source).
- **`usage_hints.returns_classes`** is a *list* of class ids resolved by **exact class-name match** (token-split on `[](),| ` and whitespace, strip dotted prefixes) — never `endswith` (kills the `PurePath`-matches-`Path` false positive).
- **`build_universal_server` is removed** (redundant wrapper; only `tests/test_serve_all_expose.py` uses it — rewritten in Task 8).

---

### Task 1: Error helper + `MultiLibraryIndex` rework (D5, D7)

**Files:**
- Modify: `src/lcp/mcp_server.py` (replace `MultiLibraryIndex`, add `_error`)
- Test: `tests/test_mcp_server.py` (add classes; update `TestMultiLibraryIndex`)

**Interfaces:**
- Produces: `_error(code: str, message: str, hint: str | None = None, **extra) -> dict[str, Any]` returning `{"error": {"code", "message", "hint"?, **extra}}`.
- Produces: `MultiLibraryIndex` with `add(name, index, source="scan")`, `get(name) -> LCPIndex | None`, `names() -> list[str]`, `source(name) -> str | None`, `resolve(library: str | None) -> tuple[str | None, LCPIndex | None, dict | None]`, `list_libraries() -> list[dict]`, `__contains__`. **Removed:** `default_library`, default-tracking in `add`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_mcp_server.py`, add near the top (after the existing fixtures):

```python
from lcp.mcp_server import _error


class TestErrorHelper:
    """D5: structured error dicts with a stable shape."""

    def test_minimal_shape(self):
        err = _error("symbol_not_found", "Symbol not found: x:y")
        assert err == {"error": {"code": "symbol_not_found",
                                 "message": "Symbol not found: x:y"}}

    def test_hint_and_extras(self):
        err = _error(
            "ambiguous_library", "Pass library=", hint="Pick one.",
            loaded_libraries=["requests", "httpx"],
        )
        assert err["error"]["hint"] == "Pick one."
        assert err["error"]["loaded_libraries"] == ["requests", "httpx"]
        # stable outer shape: exactly one top-level key
        assert set(err) == {"error"}
```

Replace the whole `TestMultiLibraryIndex` class with:

```python
class TestMultiLibraryIndex:
    """Tests for MultiLibraryIndex (D7 resolution rules)."""

    def test_add_and_get(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        assert multi.get("mylib") is None
        multi.add("mylib", lcp_index)
        assert multi.get("mylib") is lcp_index
        assert "mylib" in multi

    def test_source_tracking(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        multi.add("mylib", lcp_index, source="registry")
        assert multi.source("mylib") == "registry"
        assert multi.source("other") is None

    def test_resolve_no_library_loaded(self):
        multi = MultiLibraryIndex()
        name, idx, err = multi.resolve(None)
        assert (name, idx) == (None, None)
        assert err["error"]["code"] == "library_not_loaded"
        assert "resolve_library" in err["error"]["hint"]

    def test_resolve_single_library_omitted(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        multi.add("only", lcp_index)
        name, idx, err = multi.resolve(None)
        assert name == "only" and idx is lcp_index and err is None

    def test_resolve_ambiguous(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index)
        multi.add("lib_b", lcp_index)
        name, idx, err = multi.resolve(None)
        assert idx is None
        assert err["error"]["code"] == "ambiguous_library"
        assert err["error"]["loaded_libraries"] == ["lib_a", "lib_b"]

    def test_resolve_explicit_hit(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index)
        multi.add("lib_b", lcp_index)
        name, idx, err = multi.resolve("lib_a")
        assert name == "lib_a" and idx is lcp_index and err is None

    def test_resolve_explicit_miss(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index)
        name, idx, err = multi.resolve("nope")
        assert idx is None
        assert err["error"]["code"] == "library_not_loaded"
        assert err["error"]["loaded_libraries"] == ["lib_a"]

    def test_list_libraries(self, lcp_index: LCPIndex):
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index, source="cache")
        libs = multi.list_libraries()
        assert len(libs) == 1
        assert libs[0]["name"] == "lib_a"
        assert libs[0]["source"] == "cache"
        assert libs[0]["symbol_count"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py::TestErrorHelper tests/test_mcp_server.py::TestMultiLibraryIndex -q`
Expected: FAIL (ImportError: cannot import `_error`; then attribute errors on `resolve`/`source`).

- [ ] **Step 3: Implement**

In `src/lcp/mcp_server.py`, add above `MultiLibraryIndex`:

```python
def _error(
    code: str, message: str, hint: str | None = None, **extra: Any
) -> dict[str, Any]:
    """Build the stable structured-error shape every tool returns on failure.

    Args:
        code: Machine-readable error code (e.g. ``"ambiguous_library"``).
        message: Human/agent-readable description of what went wrong.
        hint: Optional recovery suggestion for the calling agent.
        **extra: Additional context keys merged into the error object
            (e.g. ``loaded_libraries=[...]``).

    Returns:
        ``{"error": {"code": ..., "message": ..., "hint"?: ..., **extra}}``.
    """
    err: dict[str, Any] = {"code": code, "message": message}
    if hint is not None:
        err["hint"] = hint
    err.update(extra)
    return {"error": err}
```

Replace the `MultiLibraryIndex` class entirely with:

```python
class MultiLibraryIndex:
    """Registry of loaded LCPIndex instances for the MCP server.

    Holds one :class:`LCPIndex` per loaded library plus the source it was
    resolved from. There is deliberately **no** implicit default library:
    with one library loaded ``resolve(None)`` returns it, with several it
    returns an ``ambiguous_library`` error (spec D7).
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[LCPIndex, str]] = {}

    def add(self, name: str, index: LCPIndex, source: str = "scan") -> None:
        """Register (or replace) a library index.

        Args:
            name: Library name used as the lookup key.
            index: Built index for the library's manifest.
            source: Where the manifest came from (``"cache"``, ``"scan"``,
                ``"registry"``, or ``"manifest"`` for a pre-loaded file).
        """
        self._entries[name] = (index, source)

    def get(self, name: str) -> LCPIndex | None:
        """Return the index registered under *name*, or None."""
        entry = self._entries.get(name)
        return entry[0] if entry else None

    def source(self, name: str) -> str | None:
        """Return the resolution source recorded for *name*, or None."""
        entry = self._entries.get(name)
        return entry[1] if entry else None

    def names(self) -> list[str]:
        """Return the sorted names of all loaded libraries."""
        return sorted(self._entries)

    def resolve(
        self, library: str | None
    ) -> tuple[str | None, LCPIndex | None, dict[str, Any] | None]:
        """Resolve a tool's ``library`` argument to an index (spec D7).

        Args:
            library: Explicit library name, or None.

        Returns:
            ``(name, index, None)`` on success, ``(None, None, error_dict)``
            on failure — the error dict follows the D5 shape.
        """
        if library is not None:
            entry = self._entries.get(library)
            if entry is not None:
                return library, entry[0], None
            return None, None, _error(
                "library_not_loaded",
                f"Library '{library}' is not loaded.",
                hint=f"Call resolve_library('{library}') first.",
                loaded_libraries=self.names(),
            )
        if not self._entries:
            return None, None, _error(
                "library_not_loaded",
                "No library is loaded.",
                hint="Call resolve_library(<package name>) first.",
            )
        if len(self._entries) == 1:
            name = next(iter(self._entries))
            return name, self._entries[name][0], None
        return None, None, _error(
            "ambiguous_library",
            "Multiple libraries are loaded; pass library=<name>.",
            hint="Pick one of loaded_libraries and retry with library=<name>.",
            loaded_libraries=self.names(),
        )

    def list_libraries(self) -> list[dict[str, Any]]:
        """Return summary info for all loaded libraries."""
        result = []
        for name in self.names():
            idx, source = self._entries[name]
            lib = idx.doc.manifest.library
            result.append(
                {
                    "name": name,
                    "version": lib.version,
                    "language": lib.language,
                    "symbol_count": len(idx.symbols_by_id),
                    "source": source,
                }
            )
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._entries
```

Note: `create_universal_server` still references `multi_index.add(name, index)` and old tests reference `default_library`/`is_default` — the old universal-server code keeps compiling because `add()`'s signature is compatible; the two old tests that assert `default_library`/`is_default` were replaced in Step 1. If any other old test now fails on `is_default` (grep `is_default tests/`), update it to `source`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS (the two new classes green; `TestResolveLibraryTool::test_sets_default_library` and `TestUniversalToolsWithLibrary` still pass because they don't touch `default_library` directly — if `test_sets_default_library` fails on `is_default`, replace its assertion with `libs[0]["source"] == "scan"`).

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit  # use git-commit-convention skill, e.g.:
# UPD(mcp): Add structured error helper and rework MultiLibraryIndex
#
# _error() builds the stable D5 error shape; MultiLibraryIndex drops the
# implicit last-resolved default in favour of D7 resolution (explicit
# library required with >=2 loaded) and tracks the resolution source.
```

---

### Task 2: `LCPIndex.classes_by_name`, import-statement helper, byte-cap helper (D4, D6)

**Files:**
- Modify: `src/lcp/mcp_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `LCPIndex.classes_by_name: dict[str, list[str]]` (bare class name → sorted class ids).
- Produces: `_symbol_name(symbol_id: str) -> str` (last segment after `:` then `#`).
- Produces: `_import_statement(symbol_id: str, kind: SymbolKind) -> str`.
- Produces: `_fit_list(items: list[Any], max_bytes: int) -> tuple[list[Any], bool]`.
- Produces: `DEFAULT_MAX_RESPONSE_BYTES = 25_000` module constant.
- Produces: synthetic-document test helpers `make_symbol(...)` and `make_index(symbols)` in `tests/test_mcp_server.py` (used by Tasks 3–5).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mcp_server.py`:

```python
from lcp.mcp_server import (
    DEFAULT_MAX_RESPONSE_BYTES,
    _fit_list,
    _import_statement,
    _symbol_name,
)
from lcp.models import (
    LCPDocument,
    Library,
    Manifest,
    Semantics,
    Signature,
    Symbol,
    SymbolKind,
)


def make_symbol(
    kind: str = "function",
    module: str = "fake",
    summary: str = "A symbol.",
    description: str | None = None,
    returns=None,
    params=None,
) -> Symbol:
    """Build a minimal Symbol for synthetic-index tests."""
    signatures = None
    if returns is not None or params is not None:
        signatures = [Signature(params=params, returns=returns)]
    return Symbol(
        kind=SymbolKind(kind),
        module=module,
        signatures=signatures,
        semantics=Semantics(summary=summary, description=description),
    )


def make_index(symbols: dict[str, Symbol], name: str = "fake") -> LCPIndex:
    """Build an LCPIndex from an in-code symbol table."""
    doc = LCPDocument(
        manifest=Manifest(library=Library(name=name, version="1.0.0")),
        symbols=symbols,
    )
    return LCPIndex(doc)


class TestSymbolNameAndImport:
    def test_symbol_name_plain(self):
        assert _symbol_name("requests.api:get") == "get"

    def test_symbol_name_member(self):
        assert _symbol_name("pathlib:Path#resolve") == "resolve"

    def test_import_function(self):
        stmt = _import_statement("requests.api:get", SymbolKind.FUNCTION)
        assert stmt == "from requests.api import get"

    def test_import_class_member(self):
        stmt = _import_statement("pathlib:Path#resolve", SymbolKind.METHOD)
        assert stmt == "from pathlib import Path"

    def test_import_module_kind(self):
        stmt = _import_statement("json:decoder", SymbolKind.MODULE)
        assert stmt == "import json.decoder"


class TestClassesByName:
    def test_exact_name_lookup(self):
        idx = make_index(
            {
                "fake.io:Path": make_symbol("class"),
                "fake.io:PurePath": make_symbol("class"),
                "fake:get": make_symbol("function"),
            }
        )
        assert idx.classes_by_name["Path"] == ["fake.io:Path"]
        assert idx.classes_by_name["PurePath"] == ["fake.io:PurePath"]
        assert "get" not in idx.classes_by_name


class TestFitList:
    def test_all_fit(self):
        items = [{"id": "a"}, {"id": "b"}]
        kept, truncated = _fit_list(items, 10_000)
        assert kept == items and truncated is False

    def test_truncates_prefix(self):
        items = [{"pad": "x" * 100} for _ in range(100)]
        kept, truncated = _fit_list(items, 500)
        assert truncated is True
        assert 0 < len(kept) < 100
        # kept must be a prefix
        assert kept == items[: len(kept)]

    def test_default_budget_constant(self):
        assert DEFAULT_MAX_RESPONSE_BYTES == 25_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py::TestSymbolNameAndImport tests/test_mcp_server.py::TestClassesByName tests/test_mcp_server.py::TestFitList -q`
Expected: FAIL (ImportError on the new names).

- [ ] **Step 3: Implement**

In `src/lcp/mcp_server.py`:

Add to `LCPIndex.__init__`: `self.classes_by_name: dict[str, list[str]] = defaultdict(list)` and in `_build_indexes`, inside the loop:

```python
            # Index classes by bare name for exact return-type resolution
            if symbol.kind == SymbolKind.CLASS:
                self.classes_by_name[_symbol_name(symbol_id)].append(symbol_id)
```

and at the end of `_build_indexes`:

```python
        for ids in self.classes_by_name.values():
            ids.sort()
```

Add module-level (near `_symbol_summary`):

```python
DEFAULT_MAX_RESPONSE_BYTES = 25_000
"""Default byte budget for any list-returning tool payload (spec D6).

Calibrated against polars 1.42.1: DataFrame's 159 member summaries alone are
~30 KB, so heavy classes are expected to truncate; 25 KB is ~6k tokens.
"""


def _symbol_name(symbol_id: str) -> str:
    """Return the bare symbol name (last segment after ':' and '#')."""
    return symbol_id.split(":")[-1].split("#")[-1]


def _import_statement(symbol_id: str, kind: SymbolKind) -> str:
    """Return the import line an agent should write for *symbol_id*.

    Args:
        symbol_id: LCP symbol id (``module:entity`` or ``module:Class#member``).
        kind: The symbol's kind; modules render as ``import a.b``.

    Returns:
        e.g. ``"from requests.api import get"``; class members import the
        class (``pathlib:Path#resolve`` → ``"from pathlib import Path"``).
    """
    module, _, entity = symbol_id.partition(":")
    if not entity:
        return f"import {module}"
    if kind == SymbolKind.MODULE:
        return f"import {module}.{entity}"
    top_level = entity.split("#")[0]
    return f"from {module} import {top_level}"


def _fit_list(items: list[Any], max_bytes: int) -> tuple[list[Any], bool]:
    """Keep the longest prefix of *items* whose JSON size fits *max_bytes*.

    Args:
        items: JSON-serializable payload entries, already ordered.
        max_bytes: Byte budget for the serialized list.

    Returns:
        Tuple of (kept prefix, truncated flag).
    """
    total = 2  # enclosing brackets
    kept: list[Any] = []
    for item in items:
        size = len(json.dumps(item, default=str)) + 2
        if total + size > max_bytes:
            return kept, True
        kept.append(item)
        total += size
    return kept, False
```

(`_symbol_name` must be defined before `LCPIndex` uses it — place these helpers *above* the `LCPIndex` class, or define `_symbol_name` above the class and the rest near `_symbol_summary`. Simplest: put all four definitions directly after the imports, before `LCPIndex`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit
# ADD(mcp): Add class-name index, import-line and byte-cap helpers
```

---

### Task 3: `_search_index` — ranked, capped search with browse mode (D3, D4, D6)

**Files:**
- Modify: `src/lcp/mcp_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `_symbol_name`, `_fit_list`, `_error`, `_import_statement`, `make_index`/`make_symbol` (tests).
- Produces: `_search_index(index: LCPIndex, query: str, module: str | None = None, kind: str | None = None, limit: int = 20, max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> dict[str, Any]` returning `{"results": [{id, kind, summary, import}], "total": int, "truncated": bool}` or a D5 error dict (`invalid_kind`).
- Produces: updated `_symbol_summary(symbol_id, symbol) -> dict` now including `"import"`.

- [ ] **Step 1: Write the failing tests**

```python
from lcp.mcp_server import _search_index


@pytest.fixture
def ranking_index() -> LCPIndex:
    """Synthetic index with one hit per ranking tier for query 'get'."""
    return make_index(
        {
            "fake:get": make_symbol("function", summary="Send a request."),
            "fake:getattr_helper": make_symbol("function", summary="Helper."),
            "fake:widget_getter": make_symbol("function", summary="A widget."),
            "fake:fetch": make_symbol(
                "function", summary="Alias to get a resource."
            ),
            "fake:pull": make_symbol(
                "function", summary="Pull.", description="Wraps get internally."
            ),
            "fake:unrelated": make_symbol("function", summary="Nothing here."),
            "fake:Client": make_symbol("class", summary="A client."),
            "fake:Client#get": make_symbol("method", summary="Client get."),
        }
    )


class TestSearchRanking:
    def test_tier_order(self, ranking_index):
        result = _search_index(ranking_index, "get")
        ids = [r["id"] for r in result["results"]]
        # exact name (tie-break by id) > prefix > substring > summary > description
        assert ids == [
            "fake:Client#get",      # name 'get' == query (id tie-break: C < g)
            "fake:get",             # name 'get' == query
            "fake:getattr_helper",  # prefix
            "fake:widget_getter",   # substring
            "fake:fetch",           # summary
            "fake:pull",            # description
        ]
        assert result["total"] == 6
        assert result["truncated"] is False

    def test_hit_shape(self, ranking_index):
        hit = _search_index(ranking_index, "get")["results"][1]
        assert hit == {
            "id": "fake:get",
            "kind": "function",
            "summary": "Send a request.",
            "import": "from fake import get",
        }

    def test_case_insensitive(self, ranking_index):
        result = _search_index(ranking_index, "GET")
        assert result["results"][1]["id"] == "fake:get"

    def test_no_matches(self, ranking_index):
        result = _search_index(ranking_index, "zzz_nope")
        assert result == {"results": [], "total": 0, "truncated": False}


class TestSearchLimitAndCaps:
    def test_limit_truncates(self, ranking_index):
        result = _search_index(ranking_index, "get", limit=2)
        assert len(result["results"]) == 2
        assert result["total"] == 6
        assert result["truncated"] is True

    def test_limit_clamped_to_100(self):
        idx = make_index(
            {f"fake:sym{i:03d}": make_symbol("function") for i in range(150)}
        )
        result = _search_index(idx, "sym", limit=999)
        assert len(result["results"]) == 100
        assert result["truncated"] is True

    def test_byte_cap_truncates(self, ranking_index):
        result = _search_index(ranking_index, "get", max_bytes=250)
        assert result["truncated"] is True
        assert 0 < len(result["results"]) < 6


class TestSearchBrowseMode:
    """D3: empty query = browse, deterministic (kind, name) order."""

    def test_empty_query_orders_by_kind_then_name(self, ranking_index):
        result = _search_index(ranking_index, "")
        ids = [r["id"] for r in result["results"]]
        assert ids == [
            "fake:Client",           # class
            "fake:fetch",            # functions, by name
            "fake:get",
            "fake:getattr_helper",
            "fake:pull",
            "fake:unrelated",
            "fake:widget_getter",
            "fake:Client#get",       # method
        ]

    def test_browse_with_kind_filter(self, ranking_index):
        result = _search_index(ranking_index, "", kind="class")
        assert [r["id"] for r in result["results"]] == ["fake:Client"]

    def test_browse_with_module_filter(self):
        idx = make_index(
            {
                "fake.a:one": make_symbol("function", module="fake.a"),
                "fake.b:two": make_symbol("function", module="fake.b"),
            }
        )
        result = _search_index(idx, "", module="fake.a")
        assert [r["id"] for r in result["results"]] == ["fake.a:one"]

    def test_invalid_kind_error(self, ranking_index):
        result = _search_index(ranking_index, "get", kind="wibble")
        assert result["error"]["code"] == "invalid_kind"
        assert "function" in result["error"]["hint"]

    def test_query_with_kind_filter(self, ranking_index):
        result = _search_index(ranking_index, "get", kind="method")
        assert [r["id"] for r in result["results"]] == ["fake:Client#get"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q -k "SearchRanking or SearchLimit or SearchBrowse"`
Expected: FAIL (ImportError: `_search_index`).

- [ ] **Step 3: Implement**

Replace `_symbol_summary` and add `_search_index` in `src/lcp/mcp_server.py`:

```python
_VALID_KINDS = [k.value for k in SymbolKind]


def _symbol_summary(symbol_id: str, symbol: Symbol) -> dict[str, Any]:
    """Create a compact search/browse hit for a symbol (spec D4)."""
    return {
        "id": symbol_id,
        "kind": symbol.kind.value,
        "summary": symbol.semantics.summary,
        "import": _import_statement(symbol_id, symbol.kind),
    }


def _search_index(
    index: LCPIndex,
    query: str,
    module: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Ranked, capped symbol search over one library index (spec D3/D4/D6).

    Ranking tiers: exact name > name prefix > name substring > summary
    substring > description substring; ties break by id. An empty *query*
    browses instead: results are ordered by ``(kind, name, id)``.

    Args:
        index: The library index to search.
        query: Case-insensitive text; empty string means "browse".
        module: Optional module-path filter.
        kind: Optional symbol-kind filter (validated).
        limit: Maximum hits to return, clamped to 1..100 (default 20).
        max_bytes: Byte budget for the results list.

    Returns:
        ``{"results": [...], "total": N, "truncated": bool}`` or a D5 error
        dict when *kind* is invalid.
    """
    if kind is not None and kind not in _VALID_KINDS:
        return _error(
            "invalid_kind",
            f"Invalid kind '{kind}'.",
            hint=f"Valid kinds: {', '.join(_VALID_KINDS)}.",
        )
    limit = max(1, min(int(limit), 100))

    if module is not None:
        candidates = list(index.symbols_by_module.get(module, []))
    else:
        candidates = list(index.symbols_by_id)
    if kind is not None:
        kind_ids = set(index.symbols_by_kind.get(kind, []))
        candidates = [sid for sid in candidates if sid in kind_ids]

    q = query.strip().lower()
    if not q:
        # Browse mode: no relevance to rank by — deterministic (kind, name, id)
        ranked = sorted(
            candidates,
            key=lambda sid: (
                index.symbols_by_id[sid].kind.value,
                _symbol_name(sid).lower(),
                sid,
            ),
        )
    else:
        scored: list[tuple[int, str]] = []
        for sid in candidates:
            symbol = index.symbols_by_id[sid]
            name = _symbol_name(sid).lower()
            if name == q:
                score = 0
            elif name.startswith(q):
                score = 1
            elif q in name:
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
        scored.sort()
        ranked = [sid for _, sid in scored]

    total = len(ranked)
    hits = [
        _symbol_summary(sid, index.symbols_by_id[sid]) for sid in ranked[:limit]
    ]
    hits, byte_truncated = _fit_list(hits, max_bytes)
    return {
        "results": hits,
        "total": total,
        "truncated": byte_truncated or total > len(hits),
    }
```

Note: the old single-library `create_server` still calls the *old* two-key `_symbol_summary` contract in `list_symbols`/`search_symbols`/`get_class_members` — those tools now emit the extra `import` key, which breaks no old test (they assert subset keys). Leave them; they are deleted in Task 6.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit
# ADD(mcp): Implement ranked, capped search with empty-query browse mode
```

---

### Task 4: `_get_symbols` — batch detail with inline members and `returns_classes` (D4)

**Files:**
- Modify: `src/lcp/mcp_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `_import_statement`, `_fit_list`, `_normalize_return_type`, `LCPIndex.classes_by_name`, `LCPIndex.class_members`.
- Produces: `_resolve_type_to_classes(index: LCPIndex, return_type: str) -> list[str]`.
- Produces: `_get_symbols(index: LCPIndex, ids: list[str], max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> dict[str, Any]` returning `{"symbols": [...], "not_found": [...]}` plus `truncated`/`not_returned`/`hint` when size-capped. Each symbol entry: full `model_dump(exclude_none=True, mode="json")` + `id` + `import` + `usage_hints` (functions/methods) + `members`/`members_truncated` (classes).

- [ ] **Step 1: Write the failing tests**

```python
from lcp.mcp_server import _get_symbols, _resolve_type_to_classes
from lcp.models import Param


@pytest.fixture
def detail_index() -> LCPIndex:
    symbols = {
        "fake.io:Path": make_symbol("class", module="fake.io", summary="A path."),
        "fake.io:PurePath": make_symbol(
            "class", module="fake.io", summary="A pure path."
        ),
        "fake.io:Path#resolve": make_symbol(
            "method", module="fake.io", summary="Resolve.", returns="Path"
        ),
        "fake.io:Path#name": make_symbol(
            "attribute", module="fake.io", summary="Name."
        ),
        "fake:open_path": make_symbol(
            "function",
            summary="Open a path.",
            returns="Path",
            params=[
                Param(name="target", type="str", required=True),
                Param(name="strict", type="bool", required=False, default=False),
            ],
        ),
        "fake:none_fn": make_symbol("function", summary="No sig."),
    }
    return make_index(symbols)


class TestResolveTypeToClasses:
    def test_exact_match(self, detail_index):
        assert _resolve_type_to_classes(detail_index, "Path") == ["fake.io:Path"]

    def test_no_endswith_false_positive(self, detail_index):
        # 'PurePath' must NOT match a 'Path' lookup and vice versa (spec D2)
        assert _resolve_type_to_classes(detail_index, "PurePath") == [
            "fake.io:PurePath"
        ]

    def test_generic_types_are_split(self, detail_index):
        assert _resolve_type_to_classes(detail_index, "list[Path]") == [
            "fake.io:Path"
        ]
        assert _resolve_type_to_classes(detail_index, "Path | None") == [
            "fake.io:Path"
        ]

    def test_dotted_prefix_stripped(self, detail_index):
        assert _resolve_type_to_classes(detail_index, "fake.io.Path") == [
            "fake.io:Path"
        ]

    def test_builtins_skipped(self, detail_index):
        assert _resolve_type_to_classes(detail_index, "dict[str, int]") == []


class TestGetSymbolsBatch:
    def test_function_detail(self, detail_index):
        result = _get_symbols(detail_index, ["fake:open_path"])
        assert result["not_found"] == []
        sym = result["symbols"][0]
        assert sym["id"] == "fake:open_path"
        assert sym["import"] == "from fake import open_path"
        hints = sym["usage_hints"]
        assert hints["required_parameters"] == [{"name": "target", "type": "str"}]
        assert hints["optional_parameters"] == [
            {"name": "strict", "type": "bool", "default": False}
        ]
        assert hints["is_async"] is False
        assert hints["return_type"] == "Path"
        assert hints["returns_classes"] == ["fake.io:Path"]
        assert "fake.io:Path" in hints["next"]

    def test_class_inlines_member_summaries(self, detail_index):
        result = _get_symbols(detail_index, ["fake.io:Path"])
        sym = result["symbols"][0]
        assert sym["import"] == "from fake.io import Path"
        members = {m["id"]: m for m in sym["members"]}
        assert set(members) == {"fake.io:Path#resolve", "fake.io:Path#name"}
        # summaries only — no full bodies, no per-member import
        assert members["fake.io:Path#resolve"] == {
            "id": "fake.io:Path#resolve",
            "kind": "method",
            "summary": "Resolve.",
        }

    def test_batch_order_and_not_found(self, detail_index):
        result = _get_symbols(
            detail_index, ["fake:none_fn", "fake:missing", "fake:open_path"]
        )
        assert [s["id"] for s in result["symbols"]] == [
            "fake:none_fn",
            "fake:open_path",
        ]
        assert result["not_found"] == ["fake:missing"]
        assert "hint" in result

    def test_no_signature_no_usage_hints(self, detail_index):
        result = _get_symbols(detail_index, ["fake:none_fn"])
        assert "usage_hints" not in result["symbols"][0]

    def test_byte_cap_returns_not_returned(self, detail_index):
        big = {
            f"fake:f{i:02d}": make_symbol("function", summary="y" * 400)
            for i in range(40)
        }
        idx = make_index(big)
        result = _get_symbols(idx, sorted(big), max_bytes=2_000)
        assert result["truncated"] is True
        assert len(result["symbols"]) + len(result["not_returned"]) == 40
        assert "hint" in result

    def test_member_list_byte_capped(self):
        symbols = {"fake:Big": make_symbol("class", summary="Big.")}
        for i in range(400):
            symbols[f"fake:Big#m{i:03d}"] = make_symbol(
                "method", summary="z" * 200
            )
        idx = make_index(symbols)
        result = _get_symbols(idx, ["fake:Big"], max_bytes=10_000)
        sym = result["symbols"][0]
        assert sym["members_truncated"] is True
        assert 0 < len(sym["members"]) < 400
        assert "search" in sym["members_hint"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q -k "ResolveTypeToClasses or GetSymbolsBatch"`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

Add to `src/lcp/mcp_server.py` (after `_search_index`); also add `import re` to the imports:

```python
_BUILTIN_TYPE_NAMES = {
    "str", "int", "float", "bool", "bytes", "none", "nonetype", "list",
    "dict", "tuple", "set", "frozenset", "optional", "any", "union",
    "callable", "iterator", "iterable", "sequence", "mapping", "self",
}


def _resolve_type_to_classes(index: LCPIndex, return_type: str) -> list[str]:
    """Resolve a return-type string to class ids by exact name match (D4).

    Splits generics/unions (``list[Path]``, ``Path | None``), strips dotted
    prefixes, skips builtins, and looks each token up in
    ``index.classes_by_name`` — exact matches only, never ``endswith``.

    Args:
        index: The library index to resolve against.
        return_type: Normalized return-type string.

    Returns:
        Sorted, de-duplicated list of matching class ids.
    """
    matches: set[str] = set()
    for token in re.split(r"[\[\](),|\s]+", return_type):
        bare = token.strip().split(".")[-1]
        if not bare or bare.lower() in _BUILTIN_TYPE_NAMES:
            continue
        matches.update(index.classes_by_name.get(bare, []))
    return sorted(matches)


def _symbol_detail(
    index: LCPIndex, symbol_id: str, symbol: Symbol, max_bytes: int
) -> dict[str, Any]:
    """Build the full get_symbol payload for one symbol (spec D4)."""
    result = symbol.model_dump(exclude_none=True, mode="json")
    result["id"] = symbol_id
    result["import"] = _import_statement(symbol_id, symbol.kind)

    if symbol.signatures:
        sig = symbol.signatures[0]
        hints: dict[str, Any] = {
            "required_parameters": [
                {"name": p.name, "type": p.type}
                for p in (sig.params or [])
                if p.required
            ],
            "optional_parameters": [
                {"name": p.name, "type": p.type, "default": p.default}
                for p in (sig.params or [])
                if not p.required
            ],
            "is_async": sig.async_ if sig.async_ is not None else False,
            "return_type": _normalize_return_type(sig.returns),
        }
        if hints["return_type"]:
            returns_classes = _resolve_type_to_classes(
                index, hints["return_type"]
            )
            if returns_classes:
                hints["returns_classes"] = returns_classes
                hints["next"] = (
                    f"returns {hints['return_type']} → "
                    f"get_symbol(ids=['{returns_classes[0]}']) to see its members"
                )
        result["usage_hints"] = hints

    if symbol.kind == SymbolKind.CLASS:
        member_ids = sorted(index.class_members.get(symbol_id, []))
        members = [
            {
                "id": mid,
                "kind": index.symbols_by_id[mid].kind.value,
                "summary": index.symbols_by_id[mid].semantics.summary,
            }
            for mid in member_ids
        ]
        # Members share the class's byte budget; leave headroom for the body.
        members, truncated = _fit_list(members, int(max_bytes * 0.8))
        result["members"] = members
        if truncated:
            result["members_truncated"] = True
            result["members_hint"] = (
                "Member list truncated. Use search('<member name>', "
                f"module='{symbol.module}') or get_symbol on "
                f"'{symbol_id}#<member>' for the rest."
            )
    return result


def _get_symbols(
    index: LCPIndex,
    ids: list[str],
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Batch symbol lookup with per-response byte cap (spec D4/D6).

    Args:
        index: The library index to read from.
        ids: Symbol ids, returned in request order.
        max_bytes: Byte budget for the symbols list.

    Returns:
        ``{"symbols": [...], "not_found": [...]}``; adds ``truncated``,
        ``not_returned`` and ``hint`` when the byte cap cut the batch short.
    """
    details: list[dict[str, Any]] = []
    not_found: list[str] = []
    for symbol_id in ids:
        symbol = index.symbols_by_id.get(symbol_id)
        if symbol is None:
            not_found.append(symbol_id)
        else:
            details.append(_symbol_detail(index, symbol_id, symbol, max_bytes))

    kept, truncated = _fit_list(details, max_bytes)
    result: dict[str, Any] = {"symbols": kept, "not_found": not_found}
    if not_found:
        result["hint"] = (
            "Some ids were not found — take ids from search() results; the "
            "format is 'module:name' or 'module:Class#member'."
        )
    if truncated:
        result["truncated"] = True
        result["not_returned"] = [d["id"] for d in details[len(kept):]]
        result["hint"] = (
            "Response byte cap reached; call get_symbol again with the "
            "ids in not_returned."
        )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit
# ADD(mcp): Implement batch get_symbol detail with inline members and exact return-type resolution
```

---

### Task 5: `_overview` + `version` parameter on the resolution path (D1, D4)

**Files:**
- Modify: `src/lcp/mcp_server.py` (`_overview`, `resolve_library_document`)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `_overview(index: LCPIndex, source: str | None = None, max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> dict[str, Any]` → `{"library": {name, version, language, schema_version, source?, compatibility?}, "modules": [{"module", "symbols"}], "total_symbols": int}` (+ `truncated` when capped).
- Produces: `resolve_library_document(name, cache_dir=..., no_cache=False, registry_url=None, version=None)` — `version` overrides the installed version for cache lookup and registry fetch; live scan unchanged.

- [ ] **Step 1: Write the failing tests**

```python
from lcp.mcp_server import _overview


class TestOverview:
    def test_shape(self, detail_index):
        result = _overview(detail_index, source="scan")
        assert result["library"]["name"] == "fake"
        assert result["library"]["version"] == "1.0.0"
        assert result["library"]["source"] == "scan"
        modules = {m["module"]: m["symbols"] for m in result["modules"]}
        assert modules["fake.io"] == 4
        assert modules["fake"] == 2
        assert result["total_symbols"] == 6

    def test_modules_sorted(self, detail_index):
        mods = [m["module"] for m in _overview(detail_index)["modules"]]
        assert mods == sorted(mods)

    def test_byte_cap(self):
        idx = make_index(
            {
                f"fake.m{i:03d}:f": make_symbol("function", module=f"fake.m{i:03d}")
                for i in range(600)
            }
        )
        result = _overview(idx, max_bytes=1_000)
        assert result["truncated"] is True
        assert len(result["modules"]) < 600
        assert result["total_symbols"] == 600


class TestResolveDocumentVersion:
    def test_version_pins_cache_lookup(self, tmp_path, sample_lcp_file):
        """A cached doc for the requested version is used even when the
        installed version differs (installed metadata is absent here)."""
        cache_dir = tmp_path / "cache"
        doc = load_lcp_document(sample_lcp_file)
        _save = __import__("lcp.mcp_server", fromlist=["_save_to_cache"])
        _save._save_to_cache(cache_dir, doc)
        cached_version = doc.manifest.library.version

        got, source = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            version=cached_version,
        )
        assert source == "cache"
        assert got.manifest.library.version == cached_version

    def test_version_passed_to_registry(self, tmp_path, sample_lcp_file):
        doc = load_lcp_document(sample_lcp_file)
        manifest_json = doc.model_dump_json().encode()
        mock_response = MagicMock()
        mock_response.read.return_value = manifest_json
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as m:
            resolve_library_document(
                "nonexistent_package_xyz_123",
                cache_dir=tmp_path / "cache",
                no_cache=True,
                registry_url="https://registry.example.com",
                version="9.9.9",
            )
        called_url = m.call_args[0][0]
        assert "9.9.9.lcp.json.gz" in called_url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q -k "TestOverview or TestResolveDocumentVersion"`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `_overview` after `_get_symbols`:

```python
def _overview(
    index: LCPIndex,
    source: str | None = None,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Build the get_overview payload: identity + module tree (spec D4).

    Args:
        index: The library index to summarize.
        source: Resolution source recorded for the library, if known.
        max_bytes: Byte budget for the modules list.

    Returns:
        ``{"library": {...}, "modules": [...], "total_symbols": N}``.
    """
    manifest = index.doc.manifest
    library: dict[str, Any] = {
        "name": manifest.library.name,
        "version": manifest.library.version,
        "language": manifest.library.language,
        "schema_version": manifest.schema_version,
    }
    if source:
        library["source"] = source
    if manifest.compatibility:
        library["compatibility"] = manifest.compatibility.model_dump(
            exclude_none=True
        )

    modules = [
        {"module": module, "symbols": len(index.symbols_by_module[module])}
        for module in sorted(index.modules)
    ]
    modules, truncated = _fit_list(modules, max_bytes)
    result: dict[str, Any] = {
        "library": library,
        "modules": modules,
        "total_symbols": len(index.symbols_by_id),
    }
    if truncated:
        result["truncated"] = True
    return result
```

In `resolve_library_document`, add the parameter and thread it through — the new signature and the two touched hunks:

```python
def resolve_library_document(
    name: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    no_cache: bool = False,
    registry_url: str | None = None,
    version: str | None = None,
) -> tuple[LCPDocument, str]:
```

(extend the docstring's Args with `version: Optional exact version to prefer; overrides the installed version for cache lookup and registry fetch. Live scan always returns the installed version.`)

```python
    installed_ver = _installed_version(name)
    lookup_ver = version or installed_ver

    # 1. Cache lookup
    if not no_cache:
        if lookup_ver:
            cached = _load_from_cache(cache_dir, name, lookup_ver)
            if cached is not None:
                return cached, "cache"
        else:
            cached = _find_any_cached(cache_dir, name)
            if cached is not None:
                return cached, "cache"
```

and in the registry fallback: `doc = _fetch_from_registry(name, registry_url, version=lookup_ver)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py tests/test_mcp_server.py
git commit
# ADD(mcp): Add get_overview payload builder and version-pinned resolution
```

---

### Task 6: The V2 server — `LCPServer`, `_register_tools`, instructions; delete the old surface (D1, D2, D5, D9, D0)

This is the big consolidation task: the four tools become the *only* tools, the ~450 duplicated lines and the removed tools (`get_usage_guide`, `get_suggestions`, `explore_return_type`, `search_symbols`, `list_symbols`, `list_modules`, `get_manifest`, `get_class_members`, `list_libraries`) are deleted, and `mcp.tool_funcs` is replaced by `LCPServer.tools`.

**Files:**
- Modify: `src/lcp/mcp_server.py` (rewrite `create_universal_server`; delete the old tool bodies in it AND the whole tool block of `create_server`; delete `build_universal_server`)
- Modify: `src/lcp/__init__.py` (export `LCPServer`)
- Test: `tests/test_mcp_server.py` (delete old tool-test classes; add new surface tests)

**Interfaces:**
- Consumes: everything produced in Tasks 1–5.
- Produces:

```python
@dataclass
class LCPServer:
    mcp: FastMCP
    index: MultiLibraryIndex
    tools: dict[str, Callable[..., Any]]
    def run(self) -> None: ...   # delegates to self.mcp.run()

SERVER_INSTRUCTIONS: str  # module constant, D9 copy

def _register_tools(
    mcp: FastMCP,
    libraries: MultiLibraryIndex,
    *,
    cache_dir: Path,
    no_cache: bool = False,
    registry_url: str | None = None,
    allow: set[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Callable[..., Any]]: ...

def create_universal_server(
    name: str = "lcp-universal",
    cache_dir: Path | str | None = None,
    no_cache: bool = False,
    registry_url: str | None = None,
    expose: list[str] | None = None,
    preload: list[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> LCPServer: ...
```

- Tool signatures (registered names): `resolve_library(name, version=None)`, `search(query, library=None, module=None, kind=None, limit=20)`, `get_symbol(ids, library=None)`, `get_overview(library=None)`.

- [ ] **Step 1: Delete the obsolete tests**

In `tests/test_mcp_server.py` delete these classes entirely (they test removed tools / the old single-library server): `TestCreateServer` (recreated in Task 8 for the deprecated wrapper), `TestGetManifestTool`, `TestListModulesTool`, `TestListSymbolsTool`, `TestGetSymbolTool`, `TestSearchSymbolsTool`, `TestGetClassMembersTool`, `TestGetUsageGuideTool`, `TestExploreReturnTypeTool`, `TestGetSuggestionsTool`, `TestCreateUniversalServer`, `TestResolveLibraryTool`, `TestListLibrariesTool`, `TestUniversalToolsWithoutLibrary`, `TestUniversalToolsWithLibrary`. Also delete the `mcp_server` fixture and the `_get_tool_fn` helper.

- [ ] **Step 2: Write the failing tests for the new surface**

```python
@pytest.fixture
def universal_server(tmp_path: Path):
    """V2 universal server with a temporary cache dir."""
    return create_universal_server(
        name="lcp-test-universal",
        cache_dir=tmp_path / "cache",
        no_cache=True,
    )


@pytest.fixture
def loaded_server(universal_server):
    """Universal server with tests.sample_module resolved."""
    result = universal_server.tools["resolve_library"](name="tests.sample_module")
    assert result.get("status") == "loaded", result
    return universal_server


class TestCreateUniversalServer:
    def test_returns_lcp_server(self, universal_server):
        from lcp.mcp_server import LCPServer

        assert isinstance(universal_server, LCPServer)
        assert universal_server.mcp.name == "lcp-test-universal"

    def test_exactly_four_tools(self, universal_server):
        assert set(universal_server.tools) == {
            "resolve_library",
            "search",
            "get_symbol",
            "get_overview",
        }

    def test_tools_registered_over_protocol(self, universal_server):
        """FastMCP 3.x verification (spec D0): registration + in-process call."""
        from fastmcp import Client

        async def _probe():
            async with Client(universal_server.mcp) as client:
                tools = {t.name for t in await client.list_tools()}
                assert tools == {
                    "resolve_library", "search", "get_symbol", "get_overview",
                }
                result = await client.call_tool(
                    "resolve_library", {"name": "tests.sample_module"}
                )
                assert result.data["status"] == "loaded"
                result = await client.call_tool("search", {"query": "simple"})
                assert result.data["results"]

        asyncio.run(_probe())

    def test_instructions_present(self, universal_server):
        """D9: the instructions field is the always-on adoption lever."""
        text = universal_server.mcp.instructions
        assert text
        for phrase in ("resolve_library", "search", "get_symbol"):
            assert phrase in text

    def test_no_tool_funcs_attribute(self, universal_server):
        assert not hasattr(universal_server.mcp, "tool_funcs")


class TestResolveLibraryTool:
    def test_resolve_installed_package(self, universal_server):
        result = universal_server.tools["resolve_library"](
            name="tests.sample_module"
        )
        assert result["status"] == "loaded"
        assert result["symbol_count"] > 0
        assert result["source"] == "scan"
        assert "search" in result["next_step"]

    def test_resolve_missing_package(self, universal_server):
        result = universal_server.tools["resolve_library"](
            name="nonexistent_package_xyz_123"
        )
        assert result["error"]["code"] == "resolve_failed"
        assert "message" in result["error"]

    def test_expose_blocks_unlisted(self, tmp_path):
        server = create_universal_server(
            cache_dir=tmp_path / "cache", no_cache=True, expose=["json"]
        )
        result = server.tools["resolve_library"](name="os")
        assert result["error"]["code"] == "library_not_exposed"
        assert result["error"]["exposed"] == ["json"]

    def test_version_mismatch_warning(self, universal_server):
        result = universal_server.tools["resolve_library"](
            name="tests.sample_module", version="0.0.0-nonexistent"
        )
        # scan wins (installed version) and flags the mismatch
        assert result["status"] == "loaded"
        assert result["warning"]["code"] == "version_mismatch"
        assert result["warning"]["requested"] == "0.0.0-nonexistent"

    def test_registry_fallback(self, tmp_path, sample_lcp_file):
        doc = load_lcp_document(sample_lcp_file)
        mock_response = MagicMock()
        mock_response.read.return_value = doc.model_dump_json().encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        server = create_universal_server(
            cache_dir=tmp_path / "cache",
            no_cache=True,
            registry_url="https://registry.example.com",
        )
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = server.tools["resolve_library"](
                name="nonexistent_package_xyz_123"
            )
        assert result["status"] == "loaded"
        assert result["source"] == "registry"


class TestLibraryDisambiguation:
    """D7 behaviour through the real tools."""

    def test_no_library_loaded(self, universal_server):
        for call in (
            lambda: universal_server.tools["search"](query="x"),
            lambda: universal_server.tools["get_symbol"](ids=["a:b"]),
            lambda: universal_server.tools["get_overview"](),
        ):
            result = call()
            assert result["error"]["code"] == "library_not_loaded"

    def test_single_library_omitted_ok(self, loaded_server):
        result = loaded_server.tools["search"](query="simple")
        assert result["results"]

    def test_two_libraries_require_param(self, loaded_server, sample_lcp_file):
        doc = load_lcp_document(sample_lcp_file)
        loaded_server.index.add("second_lib", LCPIndex(doc))
        result = loaded_server.tools["search"](query="simple")
        assert result["error"]["code"] == "ambiguous_library"
        assert set(result["error"]["loaded_libraries"]) == {
            "tests.sample_module",
            "second_lib",
        }
        # explicit library recovers
        ok = loaded_server.tools["search"](
            query="simple", library="tests.sample_module"
        )
        assert ok["results"]


class TestSearchTool:
    def test_end_to_end(self, loaded_server):
        result = loaded_server.tools["search"](query="simple")
        assert any("simple" in r["id"].lower() for r in result["results"])
        assert all("import" in r for r in result["results"])

    def test_browse_empty_query(self, loaded_server):
        result = loaded_server.tools["search"](
            query="", module="tests.sample_module", kind="class"
        )
        assert result["results"]
        assert all(r["kind"] == "class" for r in result["results"])


class TestGetSymbolTool:
    def test_batch_end_to_end(self, loaded_server):
        found = loaded_server.tools["search"](query="simple")["results"]
        ids = [r["id"] for r in found[:2]]
        result = loaded_server.tools["get_symbol"](ids=ids)
        assert [s["id"] for s in result["symbols"]] == ids

    def test_class_has_members(self, loaded_server):
        result = loaded_server.tools["get_symbol"](
            ids=["tests.sample_module:SimpleClass"]
        )
        sym = result["symbols"][0]
        assert sym["kind"] == "class"
        assert any(m["id"].endswith("#get_value") or "#" in m["id"]
                   for m in sym["members"])


class TestGetOverviewTool:
    def test_end_to_end(self, loaded_server):
        result = loaded_server.tools["get_overview"]()
        assert result["library"]["name"] == "tests.sample_module"
        assert result["library"]["source"] == "scan"
        assert result["total_symbols"] > 0


class TestPreload:
    def test_preload_resolves_at_startup(self, tmp_path):
        server = create_universal_server(
            cache_dir=tmp_path / "cache",
            no_cache=True,
            preload=["tests.sample_module"],
        )
        assert "tests.sample_module" in server.index

    def test_preload_failure_does_not_raise(self, tmp_path, capsys):
        server = create_universal_server(
            cache_dir=tmp_path / "cache",
            no_cache=True,
            preload=["nonexistent_package_xyz_123"],
        )
        assert server.index.names() == []
        assert "preload" in capsys.readouterr().err.lower()
```

(Check the actual member name of `SimpleClass` in `tests/sample_module.py` before finalizing `test_class_has_members` — use whatever method exists there.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: new classes FAIL (`LCPServer` import error / `.tools` attribute missing); retained infra classes PASS.

- [ ] **Step 4: Implement the V2 server**

In `src/lcp/mcp_server.py`:

1. Add imports: `import warnings`, `from dataclasses import dataclass`, `from typing import Callable` (extend existing `typing` import).
2. **Delete**: the entire tool block inside `create_server` (from `@mcp.tool()` `get_usage_guide` down to `return mcp`) — Task 8 rewrites `create_server` as a deprecated wrapper; for now replace its body with `raise NotImplementedError` **or** go straight to the Task 8 wrapper if you prefer one pass (then also do Task 8's CLI test updates in that same commit — otherwise `test_cli.py` serve tests break). Recommended: implement the Task 8 wrapper body now (it is 8 lines, shown in Task 8 Step 3) but leave CLI text/flags to Task 8.
3. **Delete**: everything in `create_universal_server` from the first `@mcp.tool()` to `return mcp`, and delete `build_universal_server`.
4. Add the instructions constant and the new machinery:

```python
SERVER_INSTRUCTIONS = """\
LCP serves ground-truth API documentation for Python libraries, generated by
introspecting the installed package — unlike training data, it is never stale.

WHEN TO USE: before writing an import or a call against any library you have
not verified in this session — especially niche, new, or fast-moving ones.
If you are not certain a symbol exists with the exact signature you are about
to write, check first: a plausible-looking guess is the top source of broken
code, and checking costs 3 quick calls.

WORKFLOW (3 calls):
1. resolve_library(name)          — load the library (cache / scan / registry)
2. search(query, library=...)     — find symbols; empty query browses a module
3. get_symbol(ids=[...])          — exact signatures, parameters, and the
                                    correct import line; classes include all
                                    members inline

get_overview(library=...) shows the module tree if you need orientation first.
Errors come back as {"error": {"code", "message", "hint", ...}} — follow the
hint to recover (e.g. pass library=<name> when several libraries are loaded).
"""


@dataclass
class LCPServer:
    """A configured LCP MCP server plus direct access to its internals.

    Attributes:
        mcp: The underlying FastMCP server (use :meth:`run` to serve stdio).
        index: The registry of loaded library indexes.
        tools: Raw tool callables by name, for in-process invocation
            (tests, preload) without the MCP protocol.
    """

    mcp: FastMCP
    index: MultiLibraryIndex
    tools: dict[str, Callable[..., Any]]

    def run(self) -> None:
        """Run the MCP server on stdio transport (blocks)."""
        self.mcp.run()


def _register_tools(
    mcp: FastMCP,
    libraries: MultiLibraryIndex,
    *,
    cache_dir: Path,
    no_cache: bool = False,
    registry_url: str | None = None,
    allow: set[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Callable[..., Any]]:
    """Register the four V2 tools on *mcp* against *libraries* (spec D1).

    This is the single registration path shared by ``lcp serve-all`` and the
    deprecated ``lcp serve`` — the index provider (*libraries*) is the only
    thing that varies between them.

    Args:
        mcp: FastMCP server to register tools on.
        libraries: Index registry the tools read from and resolve into.
        cache_dir: Manifest cache root for resolve_library.
        no_cache: Disable cache read/write in resolve_library.
        registry_url: Optional registry fallback URL for resolve_library.
        allow: Optional allow-list of resolvable package names (None = all).
        max_response_bytes: Byte budget applied to list-returning payloads.

    Returns:
        Dict of tool name → raw callable for in-process invocation.
    """

    def resolve_library(name: str, version: str | None = None) -> dict[str, Any]:
        """Load a Python library's API docs. Call this FIRST, before any other
        lcp tool and before writing code that imports the library.

        Resolution order: local cache → live scan of the installed package →
        registry fetch. Then use search() to find symbols and get_symbol()
        to verify exact signatures before writing code.

        Args:
            name: pip package name (e.g. "requests", "fastmcp").
            version: Optional exact version to prefer from cache/registry; a
                mismatch with what gets resolved is flagged, not fatal.

        Returns:
            {"status": "loaded", name, version, symbol_count, module_count,
            source, next_step} or {"error": {code, message, hint, ...}}.
        """
        if allow is not None and name not in allow:
            return _error(
                "library_not_exposed",
                f"Library '{name}' is not exposed by this server.",
                hint="Ask for one of the exposed libraries instead.",
                exposed=sorted(allow),
            )
        try:
            doc, source = resolve_library_document(
                name,
                cache_dir=cache_dir,
                no_cache=no_cache,
                registry_url=registry_url,
                version=version,
            )
        except ImportError as exc:
            return _error(
                "resolve_failed",
                str(exc),
                hint=(
                    "Check the package name (pip distribution vs import "
                    "path) and that it is installed in this environment."
                ),
            )

        index = LCPIndex(doc)
        libraries.add(name, index, source=source)
        lib = doc.manifest.library
        result: dict[str, Any] = {
            "status": "loaded",
            "name": lib.name,
            "version": lib.version,
            "language": lib.language,
            "symbol_count": len(index.symbols_by_id),
            "module_count": len(index.modules),
            "source": source,
            "next_step": (
                f"search(<what you need>, library='{name}') to find symbols, "
                "then get_symbol(ids=[...]) to verify signatures."
            ),
        }
        if version and lib.version != version:
            result["warning"] = {
                "code": "version_mismatch",
                "requested": version,
                "resolved": lib.version,
                "message": (
                    f"Requested {name}=={version} but resolved "
                    f"{lib.version}; the docs describe {lib.version}."
                ),
            }
        return result

    def search(
        query: str,
        library: str | None = None,
        module: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find symbols in a loaded library, ranked by relevance. The primary
        discovery tool — one call replaces browsing module by module.

        Ranking: exact name > name prefix > name substring > summary >
        description. An EMPTY query browses: combine with module= and/or
        kind= to list contents in deterministic (kind, name) order.

        Args:
            query: Case-insensitive text to match; "" to browse.
            library: Library name — required when several libraries are loaded.
            module: Restrict to one module path (e.g. "requests.sessions").
            kind: Restrict to one kind: function, class, method, attribute,
                module, constant.
            limit: Max results (default 20, max 100).

        Returns:
            {"results": [{id, kind, summary, import}], "total", "truncated"}.
            "import" is the exact import line. Follow up with
            get_symbol(ids=[...]) before writing code.
        """
        _, index, err = libraries.resolve(library)
        if err is not None:
            return err
        return _search_index(
            index, query, module=module, kind=kind, limit=limit,
            max_bytes=max_response_bytes,
        )

    def get_symbol(
        ids: list[str], library: str | None = None
    ) -> dict[str, Any]:
        """Get full, verified details for one or more symbols in one call:
        exact signature, parameters, return type, and the correct import
        line. ALWAYS call this before writing a call site — never guess
        parameter names or defaults.

        Classes inline all members as one-line summaries, so one call usually
        answers "what can this object do"; fetch a member id (Class#member)
        for its full signature. usage_hints.returns_classes links a return
        type to its class id — verify methods on returned objects instead of
        inventing them.

        Args:
            ids: Symbol ids from search results, e.g.
                ["requests.api:get", "pathlib:Path#resolve"]. Batch related
                ids in ONE call.
            library: Library name — required when several libraries are loaded.

        Returns:
            {"symbols": [...], "not_found": [...]} plus truncated/
            not_returned when the response hits the size cap.
        """
        _, index, err = libraries.resolve(library)
        if err is not None:
            return err
        return _get_symbols(index, ids, max_bytes=max_response_bytes)

    def get_overview(library: str | None = None) -> dict[str, Any]:
        """Get a library's identity and module tree with per-module symbol
        counts. Use for orientation when you don't yet know what to search
        for; use search("", module=...) to browse a specific module.

        Args:
            library: Library name — required when several libraries are loaded.

        Returns:
            {"library": {name, version, language, source}, "modules":
            [{module, symbols}], "total_symbols"}.
        """
        name, index, err = libraries.resolve(library)
        if err is not None:
            return err
        return _overview(
            index, source=libraries.source(name), max_bytes=max_response_bytes
        )

    tools: dict[str, Callable[..., Any]] = {
        "resolve_library": resolve_library,
        "search": search,
        "get_symbol": get_symbol,
        "get_overview": get_overview,
    }
    for fn in tools.values():
        mcp.tool()(fn)
    return tools


def create_universal_server(
    name: str = "lcp-universal",
    cache_dir: Path | str | None = None,
    no_cache: bool = False,
    registry_url: str | None = None,
    expose: list[str] | None = None,
    preload: list[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> LCPServer:
    """Create a universal MCP server that resolves any installed Python library.

    The server exposes exactly four tools — ``resolve_library``, ``search``,
    ``get_symbol``, ``get_overview`` — and carries adoption-focused
    ``instructions`` so agents verify APIs before writing code.

    Args:
        name: Server name shown to MCP clients.
        cache_dir: Root directory for cached manifests (default ~/.lcp/cache/).
        no_cache: Disable reading from and writing to the cache.
        registry_url: Optional LCP registry URL used when local scanning fails.
        expose: Optional allow-list of package names resolve_library may load.
        preload: Package names to resolve eagerly at startup.
        max_response_bytes: Byte budget for list-returning tool responses.

    Returns:
        An :class:`LCPServer` bundling the FastMCP instance, the library
        index, and the raw tool callables.
    """
    resolved_cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    libraries = MultiLibraryIndex()
    mcp = FastMCP(name, instructions=SERVER_INSTRUCTIONS)
    allow: set[str] | None = (
        {n.strip() for n in expose if n.strip()} or None
    ) if expose else None

    tools = _register_tools(
        mcp,
        libraries,
        cache_dir=resolved_cache_dir,
        no_cache=no_cache,
        registry_url=registry_url,
        allow=allow,
        max_response_bytes=max_response_bytes,
    )

    for pkg in preload or []:
        try:
            result = tools["resolve_library"](pkg)
            if "error" in result:
                raise RuntimeError(result["error"]["message"])
        except Exception as exc:
            print(
                f"Warning: failed to preload package '{pkg}': {exc}",
                file=sys.stderr,
            )

    return LCPServer(mcp=mcp, index=libraries, tools=tools)
```

5. Update `run_universal_server` to call `create_universal_server(...).run()` and add the `max_response_bytes` parameter (docstring too).
6. In `src/lcp/__init__.py`, add `LCPServer` to the `from .mcp_server import (...)` block and to `__all__`.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS. Then run the full suite: `.venv/bin/python -m pytest tests/ -q` — `tests/test_serve_all_expose.py` and CLI serve tests may now fail; fix `test_serve_all_expose.py` here (below), CLI fixes belong to Task 8.

Rewrite `tests/test_serve_all_expose.py` as:

```python
"""Tests for serve-all --expose/--preload package allow-list."""

from __future__ import annotations

from lcp.mcp_server import create_universal_server


def _build(expose=None, preload=None, tmp=None):
    return create_universal_server(expose=expose, preload=preload, no_cache=True)


def test_expose_blocks_unlisted_package():
    server = _build(expose=["json"])
    blocked = server.tools["resolve_library"]("os")
    assert blocked["error"]["code"] == "library_not_exposed"


def test_expose_allows_listed_package():
    server = _build(expose=["json"])
    ok = server.tools["resolve_library"]("json")
    assert not ok.get("error")


def test_no_expose_allows_any_package():
    server = _build(expose=None)
    ok = server.tools["resolve_library"]("json")
    assert not ok.get("error")
```

- [ ] **Step 6: Grep for leftovers**

Run: `grep -rn "tool_funcs\|get_usage_guide\|get_suggestions\|explore_return_type\|search_symbols\|list_symbols\|get_class_members\|list_libraries\|build_universal_server\|default_library" src/ tests/`
Expected: no hits in `src/` (docs/plugin hits are Tasks 9–10). Fix any stragglers.

- [ ] **Step 7: Commit**

```bash
git add src/lcp/mcp_server.py src/lcp/__init__.py tests/test_mcp_server.py tests/test_serve_all_expose.py
git commit
# UPD(mcp): Consolidate MCP surface to resolve_library/search/get_symbol/get_overview
#
# Single _register_tools() path replaces the two duplicated servers;
# LCPServer.tools replaces the mcp.tool_funcs attribute-stuffing; server
# instructions carry the usage guide (spec D1-D9). Removes get_usage_guide,
# get_suggestions, explore_return_type, search_symbols, list_symbols,
# list_modules, get_manifest, get_class_members, list_libraries.
```

---

### Task 7: FastMCP pin `>=3.0,<4` (D0)

**Files:**
- Modify: `pyproject.toml:29`

**Interfaces:** none (dependency metadata only). The 3.x behaviors the code relies on were verified on installed 3.4.2: `@mcp.tool()` returns the original function, `FastMCP(name, instructions=...)` works, in-process `fastmcp.Client` calls work (covered by `test_tools_registered_over_protocol`).

- [ ] **Step 1: Update the pin**

In `pyproject.toml` change `"fastmcp>=2.0",` to `"fastmcp>=3.0,<4",`.

- [ ] **Step 2: Reinstall and verify**

Run: `.venv/bin/pip install -e ".[dev]" -q && .venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"`
Expected: a 3.x version (3.4.2).

- [ ] **Step 3: Full suite**

Run: `env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN .venv/bin/python -m pytest tests/ -q`
Expected: PASS (CLI serve tests may still be red if Task 6 chose the NotImplementedError placeholder — then do Task 8 before committing, in one commit).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit
# UPD(deps): Pin fastmcp to >=3.0,<4
```

---

### Task 8: Deprecate `lcp serve` / `create_server`; CLI `--max-response-bytes` (D8)

**Files:**
- Modify: `src/lcp/mcp_server.py` (`create_server`, `run_server`)
- Modify: `src/lcp/cli.py` (`serve`, `serve_all`)
- Test: `tests/test_mcp_server.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `create_server(manifest_path, name=None) -> LCPServer` — emits `DeprecationWarning`; returns a universal server with the manifest pre-loaded (`source="manifest"`) and `expose` locked to the library name.
- Produces: `run_server(manifest_path, name=None)` — same, then `.run()`.
- Produces: CLI `lcp serve` prints a deprecation warning to stderr and serves; `lcp serve-all` gains `--max-response-bytes` (default 25000).

- [ ] **Step 1: Write the failing tests**

In `tests/test_mcp_server.py`:

```python
class TestCreateServerDeprecated:
    def test_emits_deprecation_and_preloads(self, sample_lcp_file):
        with pytest.warns(DeprecationWarning, match="serve-all"):
            server = create_server(sample_lcp_file)
        assert server.mcp.name == "lcp-tests.sample_module"
        assert set(server.tools) == {
            "resolve_library", "search", "get_symbol", "get_overview",
        }
        # manifest already loaded: tools work without resolve_library
        overview = server.tools["get_overview"]()
        assert overview["library"]["name"] == "tests.sample_module"
        assert overview["library"]["source"] == "manifest"

    def test_expose_locked_to_manifest_library(self, sample_lcp_file):
        with pytest.warns(DeprecationWarning):
            server = create_server(sample_lcp_file)
        blocked = server.tools["resolve_library"](name="os")
        assert blocked["error"]["code"] == "library_not_exposed"

    def test_custom_name(self, sample_lcp_file):
        with pytest.warns(DeprecationWarning):
            server = create_server(sample_lcp_file, name="custom-name")
        assert server.mcp.name == "custom-name"
```

In `tests/test_cli.py`, find the existing serve-command tests (grep `def test_serve`); update/extend with:

```python
    def test_serve_warns_deprecated(self, runner, sample_lcp_file):
        with patch("lcp.cli.run_mcp_server") as mock_run:
            result = runner.invoke(main, ["serve", str(sample_lcp_file)])
        assert result.exit_code == 0
        assert "deprecated" in result.output.lower()
        assert "serve-all" in result.output
        mock_run.assert_called_once()

    def test_serve_all_max_response_bytes_flag(self, runner):
        with patch("lcp.cli.run_universal_server") as mock_run:
            result = runner.invoke(
                main, ["serve-all", "--max-response-bytes", "10000"]
            )
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["max_response_bytes"] == 10000
```

(Match the existing test file's fixture names — it already has a `runner` fixture and a sample manifest fixture; reuse them.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN .venv/bin/python -m pytest tests/test_mcp_server.py::TestCreateServerDeprecated tests/test_cli.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`create_server` / `run_server` in `src/lcp/mcp_server.py`:

```python
def create_server(
    manifest_path: str | Path,
    name: str | None = None,
) -> LCPServer:
    """Create an MCP server pre-loaded with one LCP manifest.

    .. deprecated::
        ``lcp serve`` / ``create_server`` are deprecated; use
        ``lcp serve-all --expose <package>`` / :func:`create_universal_server`.
        This wrapper builds the same universal server with the manifest
        pre-loaded and resolution locked to its library.

    Args:
        manifest_path: Path to the ``.lcp.json`` file.
        name: Server name (default: ``lcp-{library-name}``).

    Returns:
        Configured :class:`LCPServer` instance.
    """
    warnings.warn(
        "create_server()/'lcp serve' are deprecated; use "
        "create_universal_server()/'lcp serve-all --expose <package>'.",
        DeprecationWarning,
        stacklevel=2,
    )
    doc = load_lcp_document(manifest_path)
    lib_name = doc.manifest.library.name
    server = create_universal_server(
        name=name or f"lcp-{lib_name}", expose=[lib_name]
    )
    server.index.add(lib_name, LCPIndex(doc), source="manifest")
    return server


def run_server(manifest_path: str | Path, name: str | None = None) -> None:
    """Create and run a (deprecated) single-manifest MCP server.

    Args:
        manifest_path: Path to the ``.lcp.json`` file.
        name: Server name (default: ``lcp-{library-name}``).
    """
    create_server(manifest_path, name=name).run()
```

`src/lcp/cli.py` — in `serve()`, before `run_mcp_server(...)`:

```python
    click.echo(
        "Warning: 'lcp serve' is deprecated; use "
        "'lcp serve-all --expose <package>' instead.",
        err=True,
    )
```

and update the command docstring's first line to `"""Start an MCP server for an LCP manifest (deprecated: use serve-all)."""` keeping the examples.

In `serve_all()`, add the option and parameter:

```python
@click.option(
    "--max-response-bytes",
    type=int,
    default=25_000,
    show_default=True,
    help="Byte budget for list-returning tool responses (context blowout guard).",
)
```

thread `max_response_bytes: int` through the function signature into `run_universal_server(..., max_response_bytes=max_response_bytes)`.

- [ ] **Step 4: Run the full suite**

Run: `env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN .venv/bin/python -m pytest tests/ -q`
Expected: PASS (all files).

- [ ] **Step 5: Commit**

```bash
git add src/lcp/mcp_server.py src/lcp/cli.py tests/test_mcp_server.py tests/test_cli.py
git commit
# UPD(cli): Deprecate lcp serve in favour of serve-all --expose
```

---

### Task 9: Plugin skills, commands, and agent — the ≤3-call workflow (D9)

**Files:**
- Modify: `plugin/lcp/skills/lcp-universal/SKILL.md` (full rewrite)
- Modify: `plugin/lcp/skills/lcp-usage/SKILL.md` (full rewrite)
- Modify: `plugin/lcp/commands/resolve.md`, `plugin/lcp/commands/scan.md`
- Modify: `plugin/lcp/agents/library-explorer.md`
- Unchanged: `plugin/lcp/commands/configure.md` (no tool references)

No unit tests — verification is `grep` (Step 2) plus the Task 11 eval run and plugin smoke test.

- [ ] **Step 1: Rewrite the files**

`plugin/lcp/skills/lcp-universal/SKILL.md` (keep the frontmatter `name`; description updated):

```markdown
---
name: lcp-universal
description: This skill should be used when the user writes code that imports or uses a Python library, asks to "look up the X API", "check how to use X", "what's the signature of X.Y", "resolve library X", or encounters import errors or API misuse. Activates the lcp MCP server's resolve → search → get_symbol workflow for on-demand introspection of any pip-installed package.
---

# LCP Universal — On-demand Python Library Documentation

The `lcp` MCP server (started automatically by this plugin) serves
ground-truth API documentation for any pip-installed Python library —
every public symbol, signature, and docstring, introspected from the
installed version. Unlike training data, it is never stale.

**Verify before you write.** If you are not certain a symbol exists with
the exact signature you are about to write — especially for niche, new, or
fast-moving libraries — check it first. The whole workflow is 3 calls.

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
   required/optional parameters, return types, and the correct import line.
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
```

`plugin/lcp/skills/lcp-usage/SKILL.md`:

```markdown
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
| `search(query, library?, module?, kind?, limit?)` | Ranked symbol search; empty query = browse. Hits include the import line. |
| `get_symbol(ids, library?)` | Batch: full signatures, params, return types, import lines; classes inline member summaries. |
| `get_overview(library?)` | Library identity + module tree with symbol counts. |

## Rules

- With ≥2 libraries loaded, pass `library=` on every call (an
  `ambiguous_library` error lists the loaded names if you forget).
- Errors are `{"error": {"code", "message", "hint", ...}}` — follow the hint.
- If no `lcp` server is connected, suggest:
  `claude mcp add lcp -- lcp serve-all`.
```

`plugin/lcp/commands/resolve.md`:

```markdown
---
description: Load a Python library into LCP via resolve_library and prepare it for exploration with search / get_symbol.
argument-hint: <package-name>
---

# Resolve a Python library

Load a Python library into LCP for exploration. Call
`resolve_library("$ARGUMENTS")` to scan, cache, and make it available.

Then explore with `search("<what you need>", library="$ARGUMENTS")` and
verify exact signatures with `get_symbol(ids=[...])` before writing code.
```

`plugin/lcp/commands/scan.md`:

```markdown
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
```

`plugin/lcp/agents/library-explorer.md`:

```markdown
---
name: library-explorer
description: Systematically explores a Python library's API using LCP MCP tools. Use when the user asks to understand a library's capabilities, find the right API for a task, or compare approaches across a library.
model: haiku
effort: low
maxTurns: 15
disallowedTools: Write, Edit
---

You are a Python library research agent. Your job is to explore a library's
API using LCP MCP tools and return a structured summary of what you found.

## Workflow

1. Call `resolve_library("LIBRARY_NAME")` to load the library.
2. Call `search("<task keywords>", library="LIBRARY_NAME")` to find candidate
   symbols — hits are ranked and carry the exact import line.
3. Call `get_symbol(ids=[...])` on the promising ids (batch them in one
   call) for full signatures; classes include all members inline.
4. Only if you need orientation first: `get_overview()` for the module tree,
   or `search("", module="...", kind="...")` to browse one module.

## Rules

- Always call `resolve_library` first.
- Always call `get_symbol` before reporting any signature — never guess
  parameter names, types, or defaults.
- Follow `usage_hints.returns_classes` to verify methods on returned objects.
- With several libraries loaded, pass `library=` on every call.
- Report findings in a structured format: symbol id, kind, import line,
  signature summary.
```

- [ ] **Step 2: Verify no stale tool names remain**

Run: `grep -rn "list_symbols\|search_symbols\|get_class_members\|get_usage_guide\|explore_return_type\|get_suggestions\|list_modules\|get_manifest\|list_libraries" plugin/`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add plugin/
git commit
# UPD(plugin): Teach skills, commands and agent the 3-call V2 workflow
```

---

### Task 10: User-facing and architecture docs (docs-alignment rule)

**REQUIRED SUB-SKILL:** invoke `lcp-writing-documentation` before editing — it defines the per-area conventions (guides: kebab-case, examples expected; architecture: no code snippets, snake_case, index.md + architecture.md; API reference: fix docstrings, never hand-write).

**Files:**
- Modify: `docs/guides/mcp-server.md` — sequence diagram → resolve→search→get_symbol; tool table → the 4 tools (signatures + one-line purpose from Task 6 docstrings); add an "Errors and caps" subsection (D5 shape, `ambiguous_library` when ≥2 libs, 25 000-byte default cap + `--max-response-bytes`); "Single-library mode" section → deprecation note pointing at `serve-all --expose`; "Programmatic usage" → `create_universal_server(...)` returns `LCPServer`, call `.run()`, `tools` dict for in-process use; "Recommended workflow" → the 3 calls.
- Modify: `docs/guides/claude-code-plugin.md` — grep for old tool names / old workflow references and update to the 3-call workflow.
- Modify: `docs/cli.md` — `serve`: mark deprecated (alias guidance to `serve-all --expose`); `serve-all`: document `--max-response-bytes`.
- Modify: `docs/architecture/mcp_server/index.md` + `architecture.md` — describe the consolidated surface conceptually: one registration path parameterized by the index registry, four tools, structured-error model, byte caps, no implicit default library (no code snippets, per conventions).
- Modify: `docs/architecture/plugin/index.md` + `architecture.md` and `docs/architecture/publish/index.md` — grep hits for old tool names; update mentions.
- Check: `README.md` (repo root) — `grep -n "list_symbols\|search_symbols\|get_usage_guide\|list_modules\|get_manifest" README.md`; update any hits.

- [ ] **Step 1: Invoke the lcp-writing-documentation skill and make the edits above**
- [ ] **Step 2: Verify no stale tool names in docs**

Run: `grep -rn "list_symbols\|search_symbols\|get_class_members\|get_usage_guide\|explore_return_type\|get_suggestions\|list_libraries" docs/ README.md --include="*.md" | grep -v superpowers`
Expected: no output (a historical mention inside `docs/architecture` prose is acceptable only if explicitly past-tense about the old design; prefer removal).

- [ ] **Step 3: Build the docs strictly**

Run: `.venv/bin/python -m mkdocs build --strict` (install `pip install -e ".[docs]"` into `.venv` first if `mkdocs` is missing)
Expected: `INFO - Documentation built` with zero warnings.

- [ ] **Step 4: Commit**

```bash
git add docs/ README.md
git commit
# DOC: Align guides, CLI and architecture docs with the V2 MCP surface
```

---

### Task 11: Eval harness re-run — the F1 adoption gate

**Files:**
- Modify: `evals/README.md` (fastmcp venv note)
- Create: `evals/results/2026-07-03-phase2-mcp/` (run output, committed like the baseline)
- Modify: `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` (Phase 2 Status + Eval results log)

**Context — the fastmcp double role:** `evals/.venv` pins `fastmcp==2.14.4` because fastmcp is one of the seven *target* libraries (cases were validated against 2.14.4 and must stay pinned for comparability). The harness launches `evals/.venv/bin/lcp serve-all`, and lcp is installed there **editable**, so it runs the new server code — under fastmcp 2.14.4 at runtime. The new code only uses surface that exists in both majors (`FastMCP(name, instructions=...)`, `@mcp.tool()` registration, `mcp.run()`); the *pin* is `>=3.0,<4`, the 2.x tolerance is an incidental compatibility the eval env relies on. Do **not** `pip install -e ".[dev]"` into `evals/.venv` again (the new pin would drag fastmcp to 3.x and invalidate the case pins) — the editable install needs no reinstall.

- [ ] **Step 1: Preflight — new server runs under fastmcp 2.14.4**

Run:
```bash
evals/.venv/bin/python -c "
from lcp.mcp_server import create_universal_server
s = create_universal_server(no_cache=True)
print(sorted(s.tools))
r = s.tools['resolve_library']('json')
print(r['status'], r['symbol_count'])
print('instructions ok:', bool(s.mcp.instructions))
"
```
Expected: the four tool names, `loaded <N>`, `instructions ok: True`. If `@mcp.tool()` behaves differently on 2.14.4 in a way that breaks registration, fix forward in `_register_tools` (register via `mcp.tool()(fn)` exactly as written — it works on both) — do NOT change the evals fastmcp pin.

Also validate the cases still resolve: `evals/.venv/bin/python evals/run.py validate`
Expected: `28 cases, 0 problems`.

- [ ] **Step 2: Update `evals/README.md`**

Replace the fastmcp note paragraph (the `> **Note:**` block) with:

```markdown
> **Note:** the evals venv pins `fastmcp==2.14.4` because fastmcp is one of
> the seven *target* libraries and the cases were validated against that
> version. The `lcp` package itself now pins `fastmcp>=3.0,<4`, so do NOT
> re-run `pip install -e ".[dev]"` in this venv (it would bump fastmcp and
> invalidate the case pins) — lcp is installed editable and picks up code
> changes automatically. The server code happens to run on both majors; the
> supported pin is 3.x. Run the MAIN test suite (`tests/`) from the project
> `.venv` (fastmcp 3.x), never from `evals/.venv`.
> When recording a new results directory, note the `claude --version` in
> `meta.json` — CLI drift between runs must stay detectable.
```

- [ ] **Step 3: Run the benchmark (both arms, 3 reps — hours; run in background)**

```bash
claude --version   # record it
evals/.venv/bin/python evals/run.py run --out evals/results/2026-07-03-phase2-mcp --arms both
evals/.venv/bin/python evals/run.py report --out evals/results/2026-07-03-phase2-mcp
```
The run is resumable (re-invoke with the same `--out` after interruptions).

- [ ] **Step 4: Analyze against the F1 gate**

From `evals/results/2026-07-03-phase2-mcp/summary.json` compare with `evals/results/2026-07-03-baseline/`:
- **Gate metric (primary):** mean voluntary lcp tool calls per run on the **fastmcp** cases (baseline: 0) and **cyhole** cases (baseline: 4.3) — the fastmcp number must move off zero; overall LCP-arm adoption should rise from 1.7 calls/run.
- Secondary: pass rate and misuse counts on fastmcp/cyhole/hamana (no regression elsewhere; only >20% relative effects are signal).
- Cost: tokens/task in the LCP arm (fewer tools + instructions should not inflate it).

**If fastmcp-case adoption stays ~0:** iterate on `SERVER_INSTRUCTIONS` and the `search`/`resolve_library` docstrings (the D9 levers) — one focused rewrite, then re-run only the LCP arm on the fastmcp/cyhole cases: `evals/run.py run --out evals/results/2026-07-03-phase2-mcp-iter2 --arms lcp --case-id <fastmcp/cyhole ids>`. Do not close the phase with adoption at zero without recording why.

- [ ] **Step 5: Record results**

- Commit the results directory (like the baseline).
- Update the roadmap: Phase 2 **Status** line (done + date + plan path + one-line eval delta) and append an entry to the **Eval results log** (adoption metric front and center).

```bash
git add evals/README.md evals/results/2026-07-03-phase2-mcp
git add -f docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md
git commit
# UPD(evals): Record Phase 2 eval re-run and update roadmap status
```

---

### Task 12: Final verification and PR

- [ ] **Step 1: Full verification (superpowers:verification-before-completion)**

```bash
env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN .venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mkdocs build --strict
grep -rn "tool_funcs\|build_universal_server" src/ tests/ docs/ plugin/ | grep -v superpowers
```
Expected: suite green, strict build clean, no stale references.

- [ ] **Step 2: Plugin smoke test (roadmap exit criterion)**

Configure a scratch MCP config that runs `.venv/bin/lcp serve-all --expose json` and, via `claude -p` with `--mcp-config`, ask a signature question about `json.loads` — confirm the answer arrives through ≤3 lcp tool calls (`resolve_library` → `search` → `get_symbol`). Record the transcript path in the PR description.

- [ ] **Step 3: Push and open the PR (superpowers:finishing-a-development-branch)**

```bash
git push -u origin roadmap/phase-2-mcp-consolidation
gh pr create --base roadmap/agentic-improvements \
  --title "CODE: Consolidate MCP surface to the V2 four-tool design (Phase 2)" \
  --body "<summary: spec D0-D9 implemented; tool table before/after; eval adoption delta; NO session links>"
```

---

## Self-Review notes (done at plan time)

- **Spec coverage:** D0→Task 7 (+Client protocol test in Task 6); D1→Tasks 3–6; D2→Task 6 deletions (+`_resolve_type_to_classes` salvage in Task 4); D3→Task 3 browse mode; D4→Tasks 3–5 (member-import deviation documented in Global Constraints); D5→Task 1 (+every tool via `resolve()`/`_error`); D6→Task 2 `_fit_list` + calibrated 25 000 default + CLI flag (Task 8); D7→Task 1 `resolve()` + Task 6 `TestLibraryDisambiguation`; D8→Task 8; D9→Task 6 `SERVER_INSTRUCTIONS` + Task 9 plugin + Task 11 gate. D10–D12 are Phases 3–4 (no-op here by design).
- **Type consistency check:** `LCPServer.tools: dict[str, Callable]`; `MultiLibraryIndex.resolve() -> (name, index, error)` used by all four tools; `_search_index`/`_get_symbols`/`_overview` all take `max_bytes` kwarg and return dicts. `_symbol_summary` gains `import` in Task 3 and is reused by Task 4's member entries **without** import — members use an inline dict, not `_symbol_summary`, deliberately.
- **Known interactions:** Task 6 leaves `create_server` temporarily broken unless the Task 8 wrapper body is implemented in the same pass — the recommended path (do the 8-line wrapper early) is written into Task 6 Step 4.2.
