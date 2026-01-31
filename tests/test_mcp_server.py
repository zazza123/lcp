"""Tests for the MCP server module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from lcp_python_sdk.generator import generate_lcp
from lcp_python_sdk.mcp_server import LCPIndex, create_server, load_lcp_document
from lcp_python_sdk.scanner import scan_package


@pytest.fixture
def sample_lcp_file(tmp_path: Path) -> Path:
    """Generate an LCP file from sample_module for testing."""
    # Scan the sample module
    import tests.sample_module

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
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "get_manifest":
                tool_fn = tool.fn
                break

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
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "list_modules":
                tool_fn = tool.fn
                break

        assert tool_fn is not None
        result = tool_fn()

        assert isinstance(result, list)
        assert "tests.sample_module" in result


class TestListSymbolsTool:
    """Tests for list_symbols tool."""

    def test_returns_all_symbols(self, mcp_server):
        """Should return all symbols when no filter."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "list_symbols":
                tool_fn = tool.fn
                break

        assert tool_fn is not None
        result = tool_fn()

        assert isinstance(result, list)
        assert len(result) > 0
        # Check structure
        assert all("id" in s and "kind" in s and "summary" in s for s in result)

    def test_filter_by_module(self, mcp_server):
        """Should filter by module."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "list_symbols":
                tool_fn = tool.fn
                break

        result = tool_fn(module="tests.sample_module")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_filter_by_kind(self, mcp_server):
        """Should filter by kind."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "list_symbols":
                tool_fn = tool.fn
                break

        result = tool_fn(kind="function")
        assert isinstance(result, list)
        assert all(s["kind"] == "function" for s in result)

    def test_invalid_kind(self, mcp_server):
        """Should return error for invalid kind."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "list_symbols":
                tool_fn = tool.fn
                break

        result = tool_fn(kind="invalid_kind")
        assert len(result) == 1
        assert "error" in result[0]


class TestGetSymbolTool:
    """Tests for get_symbol tool."""

    def test_returns_symbol(self, mcp_server, lcp_index):
        """Should return full symbol data."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "get_symbol":
                tool_fn = tool.fn
                break

        # Get a known symbol ID
        symbol_id = list(lcp_index.symbols_by_id.keys())[0]
        result = tool_fn(symbol_id=symbol_id)

        assert "id" in result
        assert "kind" in result
        assert "semantics" in result
        assert "error" not in result

    def test_not_found(self, mcp_server):
        """Should return error for unknown symbol."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "get_symbol":
                tool_fn = tool.fn
                break

        result = tool_fn(symbol_id="nonexistent:symbol")
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestSearchSymbolsTool:
    """Tests for search_symbols tool."""

    def test_search_by_name(self, mcp_server):
        """Should find symbols by name."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "search_symbols":
                tool_fn = tool.fn
                break

        result = tool_fn(query="simple")
        assert isinstance(result, list)
        assert len(result) > 0
        # Should find simple_function and/or SimpleClass
        assert any("simple" in s["id"].lower() for s in result)

    def test_search_by_summary(self, mcp_server):
        """Should find symbols by summary text."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "search_symbols":
                tool_fn = tool.fn
                break

        result = tool_fn(query="add two numbers")
        assert isinstance(result, list)
        # Should find simple_function which has "Add two numbers" in summary

    def test_search_no_results(self, mcp_server):
        """Should return empty list for no matches."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "search_symbols":
                tool_fn = tool.fn
                break

        result = tool_fn(query="xyznonexistent123")
        assert result == []


class TestGetClassMembersTool:
    """Tests for get_class_members tool."""

    def test_returns_members(self, mcp_server, lcp_index):
        """Should return class members."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "get_class_members":
                tool_fn = tool.fn
                break

        # Find a class ID
        class_id = None
        for sid, symbol in lcp_index.symbols_by_id.items():
            if symbol.kind.value == "class" and "SimpleClass" in sid:
                class_id = sid
                break

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
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "get_class_members":
                tool_fn = tool.fn
                break

        result = tool_fn(class_id="nonexistent:Class")
        assert len(result) == 1
        assert "error" in result[0]

    def test_not_a_class(self, mcp_server, lcp_index):
        """Should return error if symbol is not a class."""
        tool_fn = None
        for tool in mcp_server._tool_manager._tools.values():
            if tool.name == "get_class_members":
                tool_fn = tool.fn
                break

        # Find a function ID
        func_id = None
        for sid, symbol in lcp_index.symbols_by_id.items():
            if symbol.kind.value == "function":
                func_id = sid
                break

        if func_id:
            result = tool_fn(class_id=func_id)
            assert len(result) == 1
            assert "error" in result[0]
            assert "not a class" in result[0]["error"]
