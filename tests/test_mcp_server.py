"""Tests for the MCP server module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lcp.generator import generate_lcp
from lcp.mcp_server import (
    LCPIndex,
    MultiLibraryIndex,
    create_server,
    create_universal_server,
    load_lcp_document,
    resolve_library_document,
)
from lcp.scanner import scan_package


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
    tools = asyncio.run(server._list_tools())
    for tool in tools:
        if tool.name == tool_name:
            return tool.fn
    return None


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
    """Tests for MultiLibraryIndex class."""

    def test_add_and_get(self, lcp_index: LCPIndex):
        """Should add and retrieve an index by name."""
        multi = MultiLibraryIndex()
        assert multi.get("mylib") is None
        multi.add("mylib", lcp_index)
        assert multi.get("mylib") is lcp_index

    def test_default_library(self, lcp_index: LCPIndex):
        """Last added library becomes the default."""
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index)
        multi.add("lib_b", lcp_index)
        assert multi.default_library == "lib_b"

    def test_get_default(self, lcp_index: LCPIndex):
        """get(None) returns the default library index."""
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index)
        assert multi.get(None) is lcp_index

    def test_get_none_empty(self):
        """get(None) returns None when no libraries loaded."""
        multi = MultiLibraryIndex()
        assert multi.get(None) is None

    def test_contains(self, lcp_index: LCPIndex):
        """'in' operator works after add."""
        multi = MultiLibraryIndex()
        assert "mylib" not in multi
        multi.add("mylib", lcp_index)
        assert "mylib" in multi

    def test_list_libraries(self, lcp_index: LCPIndex):
        """list_libraries returns one entry per registered library."""
        multi = MultiLibraryIndex()
        multi.add("lib_a", lcp_index)
        multi.add("lib_b", lcp_index)
        libs = multi.list_libraries()
        assert len(libs) == 2
        names = {lib["name"] for lib in libs}
        assert "lib_a" in names
        assert "lib_b" in names
        # The last-added library is the default
        default_entry = next(lib for lib in libs if lib["is_default"])
        assert default_entry["name"] == "lib_b"


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
        tools = asyncio.run(universal_server._list_tools())
        tool_names = {t.name for t in tools}
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
        assert expected.issubset(tool_names)


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

    def test_sets_default_library(self, universal_server):
        """Resolved library should become the implicit default."""
        resolve_fn = _get_tool_fn(universal_server, "resolve_library")
        list_libs_fn = _get_tool_fn(universal_server, "list_libraries")
        assert resolve_fn is not None
        assert list_libs_fn is not None

        resolve_fn(name="tests.sample_module")
        libs = list_libs_fn()
        assert len(libs) == 1
        assert libs[0]["is_default"] is True


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
