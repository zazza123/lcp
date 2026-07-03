"""Tests for the MCP server module."""

from __future__ import annotations

import asyncio
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lcp.generator import generate_lcp
from lcp.mcp_server import (
    DEFAULT_MAX_RESPONSE_BYTES,
    LCPIndex,
    MultiLibraryIndex,
    _DEFAULT_REGISTRY_URL,
    _error,
    _fetch_from_registry,
    _fit_list,
    _import_statement,
    _search_index,
    _symbol_name,
    create_server,
    create_universal_server,
    load_lcp_document,
    resolve_library_document,
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
from lcp.scanner import scan_package


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


@pytest.fixture
def sample_lcp_file(tmp_path: Path) -> Path:
    """Generate an LCP file from sample_module for testing."""
    # Scan the sample module
    import tests.sample_module  # noqa: F401 - ensures the module is importable before scan_package

    scanned = scan_package("tests.sample_module", include_private=False, recursive=False)
    lcp_doc = generate_lcp(scanned)

    # Write to temp file
    lcp_path = tmp_path / "sample.lcp.json"
    lcp_doc.to_file(str(lcp_path))

    return lcp_path


@pytest.fixture
def lcp_index(sample_lcp_file: Path) -> LCPIndex:
    """Create an LCPIndex from the sample LCP file."""
    doc = load_lcp_document(sample_lcp_file)
    return LCPIndex(doc)


@pytest.fixture
def mcp_server(sample_lcp_file: Path):
    """Create an MCP server from the sample LCP file."""
    return create_server(sample_lcp_file)


# ---------------------------------------------------------------------------
# Helper: retrieve a tool's callable from a FastMCP server
# ---------------------------------------------------------------------------

def _get_tool_fn(server, tool_name: str):
    """Return the raw callable for *tool_name* registered on *server*."""
    try:
        tool = asyncio.run(server.get_tool(tool_name))
        return tool.fn
    except Exception:
        return None


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


class TestLoadLCPDocument:
    """Tests for load_lcp_document function."""

    def test_load_valid_file(self, sample_lcp_file: Path):
        """Should load a valid LCP file."""
        doc = load_lcp_document(sample_lcp_file)
        assert doc.manifest.library.name == "tests.sample_module"
        assert len(doc.symbols) > 0

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="LCP file not found"):
            load_lcp_document(tmp_path / "nonexistent.json")

    def test_load_gz_file(self, sample_lcp_file: Path, tmp_path: Path):
        """Should transparently decompress and load a .lcp.json.gz file."""
        import gzip

        doc_orig = load_lcp_document(sample_lcp_file)
        gz_path = tmp_path / "sample.lcp.json.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(doc_orig.to_json().encode("utf-8"))

        doc = load_lcp_document(gz_path)
        assert doc.manifest.library.name == doc_orig.manifest.library.name
        assert len(doc.symbols) == len(doc_orig.symbols)


class TestLCPIndex:
    """Tests for LCPIndex class."""

    def test_symbols_by_id(self, lcp_index: LCPIndex):
        """Should index all symbols by ID."""
        assert len(lcp_index.symbols_by_id) > 0
        # Check a known symbol exists
        symbol_ids = list(lcp_index.symbols_by_id.keys())
        assert any("simple_function" in sid for sid in symbol_ids)

    def test_symbols_by_module(self, lcp_index: LCPIndex):
        """Should group symbols by module."""
        assert "tests.sample_module" in lcp_index.symbols_by_module
        module_symbols = lcp_index.symbols_by_module["tests.sample_module"]
        assert len(module_symbols) > 0

    def test_symbols_by_kind(self, lcp_index: LCPIndex):
        """Should group symbols by kind."""
        assert "function" in lcp_index.symbols_by_kind
        assert "class" in lcp_index.symbols_by_kind
        assert len(lcp_index.symbols_by_kind["function"]) > 0
        assert len(lcp_index.symbols_by_kind["class"]) > 0

    def test_class_members(self, lcp_index: LCPIndex):
        """Should index class members."""
        # Find a class ID
        class_ids = [
            sid for sid in lcp_index.symbols_by_id.keys()
            if lcp_index.symbols_by_id[sid].kind.value == "class"
        ]
        assert len(class_ids) > 0

        # Check if class has members indexed
        for class_id in class_ids:
            if class_id in lcp_index.class_members:
                members = lcp_index.class_members[class_id]
                assert all("#" in member_id for member_id in members)

    def test_modules_set(self, lcp_index: LCPIndex):
        """Should collect all unique modules."""
        assert "tests.sample_module" in lcp_index.modules


class TestCreateServer:
    """Tests for create_server function."""

    def test_creates_server(self, sample_lcp_file: Path):
        """Should create a FastMCP server."""
        server = create_server(sample_lcp_file)
        assert server is not None
        assert server.name == "lcp-tests.sample_module"

    def test_custom_name(self, sample_lcp_file: Path):
        """Should use custom server name."""
        server = create_server(sample_lcp_file, name="custom-name")
        assert server.name == "custom-name"


class TestGetManifestTool:
    """Tests for get_manifest tool."""

    def test_returns_manifest_info(self, mcp_server):
        """Should return library metadata."""
        # Get the tool function
        tool_fn = _get_tool_fn(mcp_server, "get_manifest")
        assert tool_fn is not None
        result = tool_fn()

        assert result["name"] == "tests.sample_module"
        assert "version" in result
        assert result["language"] == "python"
        assert "schema_version" in result


class TestListModulesTool:
    """Tests for list_modules tool."""

    def test_returns_modules(self, mcp_server):
        """Should return list of modules."""
        tool_fn = _get_tool_fn(mcp_server, "list_modules")
        assert tool_fn is not None
        result = tool_fn()

        assert isinstance(result, list)
        assert "tests.sample_module" in result


class TestListSymbolsTool:
    """Tests for list_symbols tool."""

    def test_returns_all_symbols(self, mcp_server):
        """Should return all symbols when no filter."""
        tool_fn = _get_tool_fn(mcp_server, "list_symbols")
        assert tool_fn is not None
        result = tool_fn()

        assert isinstance(result, list)
        assert len(result) > 0
        # Check structure
        assert all("id" in s and "kind" in s and "summary" in s for s in result)

    def test_filter_by_module(self, mcp_server):
        """Should filter by module."""
        tool_fn = _get_tool_fn(mcp_server, "list_symbols")
        assert tool_fn is not None

        result = tool_fn(module="tests.sample_module")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_filter_by_kind(self, mcp_server):
        """Should filter by kind."""
        tool_fn = _get_tool_fn(mcp_server, "list_symbols")
        assert tool_fn is not None

        result = tool_fn(kind="function")
        assert isinstance(result, list)
        assert all(s["kind"] == "function" for s in result)

    def test_invalid_kind(self, mcp_server):
        """Should return error for invalid kind."""
        tool_fn = _get_tool_fn(mcp_server, "list_symbols")
        assert tool_fn is not None

        result = tool_fn(kind="invalid_kind")
        assert len(result) == 1
        assert "error" in result[0]


class TestGetSymbolTool:
    """Tests for get_symbol tool."""

    def test_returns_symbol(self, mcp_server, lcp_index):
        """Should return full symbol data."""
        tool_fn = _get_tool_fn(mcp_server, "get_symbol")
        assert tool_fn is not None

        # Get a known symbol ID
        symbol_id = list(lcp_index.symbols_by_id.keys())[0]
        result = tool_fn(symbol_id=symbol_id)

        assert "id" in result
        assert "kind" in result
        assert "semantics" in result
        assert "error" not in result

    def test_not_found(self, mcp_server):
        """Should return error for unknown symbol."""
        tool_fn = _get_tool_fn(mcp_server, "get_symbol")
        assert tool_fn is not None

        result = tool_fn(symbol_id="nonexistent:symbol")
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestSearchSymbolsTool:
    """Tests for search_symbols tool."""

    def test_search_by_name(self, mcp_server):
        """Should find symbols by name."""
        tool_fn = _get_tool_fn(mcp_server, "search_symbols")
        assert tool_fn is not None

        result = tool_fn(query="simple")
        assert isinstance(result, list)
        assert len(result) > 0
        # Should find simple_function and/or SimpleClass
        assert any("simple" in s["id"].lower() for s in result)

    def test_search_by_summary(self, mcp_server):
        """Should find symbols by summary text."""
        tool_fn = _get_tool_fn(mcp_server, "search_symbols")
        assert tool_fn is not None

        result = tool_fn(query="add two numbers")
        assert isinstance(result, list)
        # Should find simple_function which has "Add two numbers" in summary

    def test_search_no_results(self, mcp_server):
        """Should return empty list for no matches."""
        tool_fn = _get_tool_fn(mcp_server, "search_symbols")
        assert tool_fn is not None

        result = tool_fn(query="xyznonexistent123")
        assert result == []


class TestGetClassMembersTool:
    """Tests for get_class_members tool."""

    def test_returns_members(self, mcp_server, lcp_index):
        """Should return class members."""
        tool_fn = _get_tool_fn(mcp_server, "get_class_members")
        # Find a class ID
        class_id = None
        for sid, symbol in lcp_index.symbols_by_id.items():
            if symbol.kind.value == "class" and "SimpleClass" in sid:
                class_id = sid
                break
        assert tool_fn is not None

        if class_id and class_id in lcp_index.class_members:
            result = tool_fn(class_id=class_id)
            assert isinstance(result, list)
            # Check structure
            for member in result:
                if "error" not in member:
                    assert "id" in member
                    assert "kind" in member

    def test_class_not_found(self, mcp_server):
        """Should return error for unknown class."""
        tool_fn = _get_tool_fn(mcp_server, "get_class_members")
        assert tool_fn is not None

        result = tool_fn(class_id="nonexistent:Class")
        assert len(result) == 1
        assert "error" in result[0]

    def test_not_a_class(self, mcp_server, lcp_index):
        """Should return error if symbol is not a class."""
        tool_fn = _get_tool_fn(mcp_server, "get_class_members")
        # Find a function ID
        func_id = None
        for sid, symbol in lcp_index.symbols_by_id.items():
            if symbol.kind.value == "function":
                func_id = sid
                break
        assert tool_fn is not None

        if func_id:
            result = tool_fn(class_id=func_id)
            assert len(result) == 1
            assert "error" in result[0]
            assert "not a class" in result[0]["error"]


class TestGetUsageGuideTool:
    """Tests for get_usage_guide tool."""

    def test_returns_workflow(self, mcp_server):
        """Should return recommended workflow and tips."""
        tool_fn = _get_tool_fn(mcp_server, "get_usage_guide")
        assert tool_fn is not None
        result = tool_fn()

        assert "recommended_workflow" in result
        assert isinstance(result["recommended_workflow"], list)
        assert len(result["recommended_workflow"]) > 0

        # Check workflow structure
        first_step = result["recommended_workflow"][0]
        assert "step" in first_step
        assert "action" in first_step
        assert "purpose" in first_step

        assert "cost_optimization" in result
        assert "common_mistakes" in result
        assert isinstance(result["common_mistakes"], list)


class TestExploreReturnTypeTool:
    """Tests for explore_return_type tool."""

    def test_returns_type_info(self, mcp_server, lcp_index):
        """Should return return type information."""
        tool_fn = _get_tool_fn(mcp_server, "explore_return_type")
        assert tool_fn is not None

        # Find a function with a return type
        func_id = None
        for sid, symbol in lcp_index.symbols_by_id.items():
            if symbol.kind.value == "function" and symbol.signatures:
                sig = symbol.signatures[0]
                if sig.returns:
                    func_id = sid
                    break

        if func_id:
            result = tool_fn(symbol_id=func_id)
            assert "symbol_id" in result
            assert "return_type" in result or "error" in result or "message" in result

    def test_symbol_not_found(self, mcp_server):
        """Should return error for unknown symbol."""
        tool_fn = _get_tool_fn(mcp_server, "explore_return_type")
        assert tool_fn is not None

        result = tool_fn(symbol_id="nonexistent:func")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_no_signature(self, mcp_server, lcp_index):
        """Should handle symbols without signatures."""
        tool_fn = _get_tool_fn(mcp_server, "explore_return_type")
        # Find a module symbol (no signature)
        module_id = None
        for sid, symbol in lcp_index.symbols_by_id.items():
            if symbol.kind.value == "module":
                module_id = sid
                break
        assert tool_fn is not None

        if module_id:
            result = tool_fn(symbol_id=module_id)
            assert "error" in result


class TestGetSuggestionsTool:
    """Tests for get_suggestions tool."""

    def test_returns_suggestions(self, mcp_server):
        """Should return suggestions based on task."""
        tool_fn = _get_tool_fn(mcp_server, "get_suggestions")
        assert tool_fn is not None
        result = tool_fn(task_description="sample module function")

        assert "task" in result
        assert "suggested_modules" in result
        assert "suggested_symbols" in result
        assert "next_steps" in result
        assert isinstance(result["next_steps"], list)

    def test_no_matches(self, mcp_server):
        """Should provide fallback suggestions when no matches."""
        tool_fn = _get_tool_fn(mcp_server, "get_suggestions")
        assert tool_fn is not None

        result = tool_fn(task_description="xyznonexistent123")

        assert "next_steps" in result
        assert len(result["next_steps"]) > 0
        # Should suggest browsing modules/symbols
        assert any("list_modules" in step or "list_symbols" in step for step in result["next_steps"])

    def test_finds_matching_modules(self, mcp_server):
        """Should find modules matching task keywords."""
        tool_fn = _get_tool_fn(mcp_server, "get_suggestions")
        assert tool_fn is not None

        result = tool_fn(task_description="sample")

        # Should find tests.sample_module
        assert "tests.sample_module" in result["suggested_modules"]


# ---------------------------------------------------------------------------
# Tests for MultiLibraryIndex
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tests for resolve_library_document
# ---------------------------------------------------------------------------


class TestResolveLibraryDocument:
    """Tests for the resolve_library_document helper."""

    def test_scan_installed_package(self, tmp_path: Path):
        """Should successfully scan an installed package."""
        doc, source = resolve_library_document(
            "tests.sample_module",
            cache_dir=tmp_path / "cache",
            no_cache=True,
        )
        assert doc is not None
        assert source == "scan"
        assert len(doc.symbols) > 0

    def test_caches_result(self, tmp_path: Path):
        """Should write a cache file and use it on second call."""
        cache_dir = tmp_path / "cache"
        # First call: scan
        doc1, source1 = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            no_cache=False,
        )
        assert source1 == "scan"
        # Cache directory should exist
        assert cache_dir.exists()

        # Second call should hit cache (version matches)
        doc2, source2 = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            no_cache=False,
        )
        assert source2 == "cache"
        assert len(doc2.symbols) == len(doc1.symbols)

    def test_no_cache_flag(self, tmp_path: Path):
        """Should always scan when no_cache=True."""
        cache_dir = tmp_path / "cache"
        # Populate the cache first
        resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            no_cache=False,
        )
        # Second call with no_cache=True should still scan
        _, source = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            no_cache=True,
        )
        assert source == "scan"

    def test_error_for_missing_package(self, tmp_path: Path):
        """Should raise ImportError for packages that cannot be scanned."""
        with pytest.raises(ImportError, match="Cannot resolve library"):
            resolve_library_document(
                "nonexistent_package_xyz_123",
                cache_dir=tmp_path / "cache",
                no_cache=True,
            )

    def test_registry_fallback_on_scan_failure(self, tmp_path: Path, sample_lcp_file: Path):
        """Should fall back to registry when local scan fails."""
        doc = load_lcp_document(sample_lcp_file)
        manifest_json = doc.model_dump_json().encode()

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_json
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result_doc, source = resolve_library_document(
                "nonexistent_package_xyz_123",
                cache_dir=tmp_path / "cache",
                no_cache=True,
                registry_url="https://registry.example.com",
            )

        assert source == "registry"
        assert result_doc is not None

    def test_registry_not_used_when_scan_succeeds(self, tmp_path: Path):
        """Should not contact registry when local scan succeeds."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            doc, source = resolve_library_document(
                "tests.sample_module",
                cache_dir=tmp_path / "cache",
                no_cache=True,
                registry_url="https://registry.example.com",
            )

        assert source == "scan"
        mock_urlopen.assert_not_called()

    def test_registry_fallback_disabled_without_url(self, tmp_path: Path):
        """Should raise ImportError if no registry_url is set and scan fails."""
        with pytest.raises(ImportError, match="Cannot resolve library"):
            resolve_library_document(
                "nonexistent_package_xyz_123",
                cache_dir=tmp_path / "cache",
                no_cache=True,
                registry_url=None,
            )

    def test_registry_http_error_propagates(self, tmp_path: Path):
        """Should raise ImportError when registry returns HTTP error."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="http://example.com", code=404, msg="Not Found", hdrs=None, fp=None  # type: ignore[arg-type]
            ),
        ):
            with pytest.raises(ImportError, match="Cannot resolve library"):
                resolve_library_document(
                    "nonexistent_package_xyz_123",
                    cache_dir=tmp_path / "cache",
                    no_cache=True,
                    registry_url="https://registry.example.com",
                )

    def test_registry_saves_to_cache(self, tmp_path: Path, sample_lcp_file: Path):
        """Registry result should be cached when no_cache is False."""
        doc = load_lcp_document(sample_lcp_file)
        manifest_json = doc.model_dump_json().encode()
        cache_dir = tmp_path / "cache"

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_json
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            _, source = resolve_library_document(
                "nonexistent_package_xyz_123",
                cache_dir=cache_dir,
                no_cache=False,
                registry_url="https://registry.example.com",
            )

        assert source == "registry"
        assert cache_dir.exists()


# ---------------------------------------------------------------------------
# Tests for _fetch_from_registry
# ---------------------------------------------------------------------------


class TestFetchFromRegistry:
    """Tests for the _fetch_from_registry helper."""

    def test_successful_fetch(self, sample_lcp_file: Path):
        """Should return a valid LCPDocument on a successful 200 response."""
        import gzip

        doc = load_lcp_document(sample_lcp_file)
        manifest_gz = gzip.compress(doc.model_dump_json().encode())

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_gz
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            result = _fetch_from_registry(
                "mylib", "https://registry.example.com", version="1.0.0"
            )

        mock_open.assert_called_once_with(
            "https://registry.example.com/manifests/python/m/mylib/1.0.0.lcp.json.gz",
            timeout=10,
        )
        assert result is not None

    def test_uses_latest_json_pointer_when_no_version(self, sample_lcp_file: Path):
        """When version is None, the manifest is resolved via latest.json."""
        import gzip

        doc = load_lcp_document(sample_lcp_file)
        manifest_gz = gzip.compress(doc.model_dump_json().encode())

        pointer_resp = MagicMock()
        pointer_resp.read.return_value = json.dumps(
            {"version": "1.0.0", "manifest": "1.0.0.lcp.json.gz"}
        ).encode()
        pointer_resp.__enter__ = lambda s: s
        pointer_resp.__exit__ = MagicMock(return_value=False)

        manifest_resp = MagicMock()
        manifest_resp.read.return_value = manifest_gz
        manifest_resp.__enter__ = lambda s: s
        manifest_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.urlopen", side_effect=[pointer_resp, manifest_resp]
        ) as mock_open:
            result = _fetch_from_registry("mylib", "https://registry.example.com")

        urls = [call.args[0] for call in mock_open.call_args_list]
        assert urls[0] == "https://registry.example.com/manifests/python/m/mylib/latest.json"
        assert urls[1] == "https://registry.example.com/manifests/python/m/mylib/1.0.0.lcp.json.gz"
        assert result is not None

    def test_invalid_latest_pointer_raises_import_error(self):
        """A latest.json without a valid 'manifest' field should raise."""
        pointer_resp = MagicMock()
        pointer_resp.read.return_value = json.dumps({"version": "1.0.0"}).encode()
        pointer_resp.__enter__ = lambda s: s
        pointer_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=pointer_resp):
            with pytest.raises(ImportError, match="missing a valid"):
                _fetch_from_registry("mylib", "https://registry.example.com")

    def test_dotted_name_uses_hyphenated_slug(self, sample_lcp_file: Path):
        """A dotted import name should map to the hyphenated registry slug."""
        import gzip

        doc = load_lcp_document(sample_lcp_file)
        manifest_gz = gzip.compress(doc.model_dump_json().encode())

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_gz
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            _fetch_from_registry(
                "google.adk", "https://registry.example.com", version="2.2.0"
            )

        called_url = mock_open.call_args[0][0]
        assert called_url == (
            "https://registry.example.com/manifests/python/g/google-adk/2.2.0.lcp.json.gz"
        )

    def test_trailing_slash_stripped(self, sample_lcp_file: Path):
        """Registry URL trailing slash should be normalised."""
        import gzip

        doc = load_lcp_document(sample_lcp_file)
        manifest_gz = gzip.compress(doc.model_dump_json().encode())

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_gz
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            _fetch_from_registry("mylib", "https://registry.example.com/", version="2.0.0")

        called_url = mock_open.call_args[0][0]
        assert called_url == "https://registry.example.com/manifests/python/m/mylib/2.0.0.lcp.json.gz"

    def test_http_error_raises_import_error(self):
        """HTTPError from the registry should raise ImportError."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="http://example.com", code=404, msg="Not Found", hdrs=None, fp=None  # type: ignore[arg-type]
            ),
        ):
            with pytest.raises(ImportError, match="Registry returned HTTP 404"):
                _fetch_from_registry("mylib", "https://registry.example.com")

    def test_url_error_raises_import_error(self):
        """URLError (network failure) should raise ImportError."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(ImportError, match="Registry fetch failed"):
                _fetch_from_registry("mylib", "https://registry.example.com")

    def test_timeout_raises_import_error(self):
        """TimeoutError should raise ImportError."""
        with patch(
            "urllib.request.urlopen",
            side_effect=TimeoutError(),
        ):
            with pytest.raises(ImportError, match="Registry fetch timed out"):
                _fetch_from_registry("mylib", "https://registry.example.com")

    def test_invalid_json_raises_import_error(self):
        """Non-JSON response body should raise ImportError."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json {"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(ImportError, match="not a valid LCP document"):
                _fetch_from_registry(
                    "mylib", "https://registry.example.com", version="1.0.0"
                )

    def test_invalid_scheme_raises_import_error(self):
        """Non-HTTP(S) registry URL should raise ImportError without making a request."""
        with patch("urllib.request.urlopen") as mock_open:
            with pytest.raises(ImportError, match="must use http or https scheme"):
                _fetch_from_registry("mylib", "ftp://registry.example.com")
        mock_open.assert_not_called()

    def test_path_traversal_in_name_raises_import_error(self):
        """Package name with path-traversal characters should raise ImportError."""
        with patch("urllib.request.urlopen") as mock_open:
            with pytest.raises(ImportError, match="Invalid package name"):
                _fetch_from_registry("../secret", "https://registry.example.com")
        mock_open.assert_not_called()

    def test_default_registry_url_is_official_registry(self):
        """_DEFAULT_REGISTRY_URL should point to the official lcp-registry."""
        assert "zazza123/lcp-registry" in _DEFAULT_REGISTRY_URL
        assert _DEFAULT_REGISTRY_URL.startswith("https://")

    def test_url_contains_manifests_path(self, sample_lcp_file: Path):
        """Constructed URL must follow manifests/{language}/{first}/{name}/{version}.lcp.json.gz layout."""
        import gzip

        doc = load_lcp_document(sample_lcp_file)
        manifest_gz = gzip.compress(doc.model_dump_json().encode())

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_gz
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            _fetch_from_registry(
                "requests", "https://registry.example.com", language="python", version="2.31.0"
            )

        called_url = mock_open.call_args[0][0]
        assert called_url == "https://registry.example.com/manifests/python/r/requests/2.31.0.lcp.json.gz"


# ---------------------------------------------------------------------------
# Tests for create_universal_server
# ---------------------------------------------------------------------------


@pytest.fixture
def universal_server(tmp_path: Path):
    """Universal MCP server with a temporary cache dir."""
    return create_universal_server(
        name="lcp-test-universal",
        cache_dir=tmp_path / "cache",
        no_cache=True,
    )


class TestCreateUniversalServer:
    """Tests for create_universal_server."""

    def test_creates_server(self, universal_server):
        """Should create a FastMCP server."""
        assert universal_server is not None
        assert universal_server.name == "lcp-test-universal"

    def test_has_expected_tools(self, universal_server):
        """Universal server should expose all expected tools."""
        expected = {
            "resolve_library",
            "list_libraries",
            "get_usage_guide",
            "get_manifest",
            "list_modules",
            "list_symbols",
            "get_symbol",
            "search_symbols",
            "get_class_members",
            "explore_return_type",
            "get_suggestions",
        }
        for name in expected:
            tool = asyncio.run(universal_server.get_tool(name))
            assert tool is not None, f"Expected tool '{name}' not found"


class TestResolveLibraryTool:
    """Tests for the resolve_library tool in the universal server."""

    def test_resolve_installed_package(self, universal_server):
        """Should load an installed package and return summary."""
        fn = _get_tool_fn(universal_server, "resolve_library")
        assert fn is not None

        result = fn(name="tests.sample_module")
        assert result.get("status") == "loaded"
        assert "symbol_count" in result
        assert result["symbol_count"] > 0
        assert result["source"] == "scan"

    def test_resolve_missing_package(self, universal_server):
        """Should return error dict for uninstalled package."""
        fn = _get_tool_fn(universal_server, "resolve_library")
        assert fn is not None

        result = fn(name="nonexistent_package_xyz_123")
        assert "error" in result

    def test_resolve_via_registry_fallback(self, tmp_path: Path, sample_lcp_file: Path):
        """resolve_library should use registry when scan fails and registry_url is set."""
        doc = load_lcp_document(sample_lcp_file)
        manifest_json = doc.model_dump_json().encode()

        mock_response = MagicMock()
        mock_response.read.return_value = manifest_json
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        server = create_universal_server(
            name="lcp-test-registry",
            cache_dir=tmp_path / "cache",
            no_cache=True,
            registry_url="https://registry.example.com",
        )
        fn = _get_tool_fn(server, "resolve_library")

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = fn(name="nonexistent_package_xyz_123")

        assert result.get("status") == "loaded"
        assert result.get("source") == "registry"

    def test_records_scan_source(self, universal_server):
        """Resolved library should be listed with its resolution source."""
        resolve_fn = _get_tool_fn(universal_server, "resolve_library")
        list_libs_fn = _get_tool_fn(universal_server, "list_libraries")
        assert resolve_fn is not None
        assert list_libs_fn is not None

        resolve_fn(name="tests.sample_module")
        libs = list_libs_fn()
        assert len(libs) == 1
        assert libs[0]["source"] == "scan"


class TestListLibrariesTool:
    """Tests for list_libraries tool."""

    def test_empty_initially(self, universal_server):
        """Should return empty list before any resolve_library calls."""
        fn = _get_tool_fn(universal_server, "list_libraries")
        assert fn is not None
        assert fn() == []

    def test_lists_after_resolve(self, universal_server):
        """Should list library after it has been resolved."""
        resolve_fn = _get_tool_fn(universal_server, "resolve_library")
        list_fn = _get_tool_fn(universal_server, "list_libraries")
        assert resolve_fn is not None and list_fn is not None

        resolve_fn(name="tests.sample_module")
        libs = list_fn()
        assert len(libs) == 1
        assert libs[0]["name"] == "tests.sample_module"


class TestUniversalToolsWithoutLibrary:
    """Universal tools should return error dicts when no library is loaded."""

    def test_get_manifest_no_library(self, universal_server):
        fn = _get_tool_fn(universal_server, "get_manifest")
        assert fn is not None
        result = fn()
        assert "error" in result

    def test_list_modules_no_library(self, universal_server):
        fn = _get_tool_fn(universal_server, "list_modules")
        assert fn is not None
        result = fn()
        assert "error" in result

    def test_list_symbols_no_library(self, universal_server):
        fn = _get_tool_fn(universal_server, "list_symbols")
        assert fn is not None
        result = fn()
        assert len(result) == 1 and "error" in result[0]

    def test_get_symbol_no_library(self, universal_server):
        fn = _get_tool_fn(universal_server, "get_symbol")
        assert fn is not None
        result = fn(symbol_id="json:loads")
        assert "error" in result

    def test_search_symbols_no_library(self, universal_server):
        fn = _get_tool_fn(universal_server, "search_symbols")
        assert fn is not None
        result = fn(query="test")
        assert len(result) == 1 and "error" in result[0]


class TestUniversalToolsWithLibrary:
    """Universal tools should work correctly after resolve_library is called."""

    @pytest.fixture(autouse=True)
    def _load_library(self, universal_server):
        """Pre-load sample_module into the universal server."""
        resolve_fn = _get_tool_fn(universal_server, "resolve_library")
        resolve_fn(name="tests.sample_module")

    def test_get_manifest(self, universal_server):
        fn = _get_tool_fn(universal_server, "get_manifest")
        result = fn()
        assert result.get("name") == "tests.sample_module"
        assert "version" in result

    def test_list_modules(self, universal_server):
        fn = _get_tool_fn(universal_server, "list_modules")
        result = fn()
        assert isinstance(result, list)
        assert "tests.sample_module" in result

    def test_list_symbols(self, universal_server):
        fn = _get_tool_fn(universal_server, "list_symbols")
        result = fn()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_list_symbols_with_library_param(self, universal_server):
        """Explicit library= parameter should target that library."""
        fn = _get_tool_fn(universal_server, "list_symbols")
        result = fn(library="tests.sample_module")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_list_symbols_unknown_library(self, universal_server):
        """Explicit library= for an unloaded library should return error."""
        fn = _get_tool_fn(universal_server, "list_symbols")
        result = fn(library="not_loaded")
        assert len(result) == 1 and "error" in result[0]

    def test_get_symbol(self, universal_server, lcp_index):
        fn = _get_tool_fn(universal_server, "get_symbol")
        symbol_id = next(iter(lcp_index.symbols_by_id))
        result = fn(symbol_id=symbol_id)
        assert "id" in result or "error" in result

    def test_search_symbols(self, universal_server):
        fn = _get_tool_fn(universal_server, "search_symbols")
        result = fn(query="simple")
        assert isinstance(result, list)
        assert any("simple" in s["id"].lower() for s in result)

    def test_get_suggestions(self, universal_server):
        fn = _get_tool_fn(universal_server, "get_suggestions")
        result = fn(task_description="sample module function")
        assert "task" in result
        assert "suggested_modules" in result

    def test_get_usage_guide_has_multi_library_tips(self, universal_server):
        fn = _get_tool_fn(universal_server, "get_usage_guide")
        result = fn()
        assert "multi_library_tips" in result
        assert "resolve_library" in result["recommended_workflow"][0]["action"]
