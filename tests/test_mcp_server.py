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
    LCPIndex,
    MultiLibraryIndex,
    _DEFAULT_REGISTRY_URL,
    _fetch_from_registry,
    _get_symbols,
    _overview,
    _resolve_type_to_classes,
    _save_to_cache,
    _search_index,
    _symbol_detail,
    create_server,
    create_universal_server,
    load_lcp_document,
    resolve_library_document,
)
from lcp.models import (
    Example,
    LCPDocument,
    Library,
    Manifest,
    Param,
    RaisesEntry,
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
        """A cached doc for the requested version is used for the lookup."""
        cache_dir = tmp_path / "cache"
        doc = load_lcp_document(sample_lcp_file)
        _save_to_cache(cache_dir, doc)
        cached_version = doc.manifest.library.version

        got, source = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            version=cached_version,
            scan_mode="inprocess",
        )
        got = got.document
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
                scan_mode="inprocess",
            )
        called_url = m.call_args[0][0]
        assert "9.9.9.lcp.json.gz" in called_url


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

    def test_class_members(self):
        """Should index class members under their class id."""
        idx = make_index(
            {
                "fake:Widget": make_symbol("class"),
                "fake:Widget#spin": make_symbol("method"),
                "fake:Widget#size": make_symbol("attribute"),
                "fake:loose_fn": make_symbol("function"),
            }
        )
        assert sorted(idx.class_members["fake:Widget"]) == [
            "fake:Widget#size",
            "fake:Widget#spin",
        ]
        assert "fake:loose_fn" not in idx.class_members

    def test_modules_set(self, lcp_index: LCPIndex):
        """Should collect all unique modules."""
        assert "tests.sample_module" in lcp_index.modules


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
            scan_mode="inprocess",
        )
        doc = doc.document
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
            scan_mode="inprocess",
        )
        doc1 = doc1.document
        assert source1 == "scan"
        # Cache directory should exist
        assert cache_dir.exists()

        # Second call should hit cache (version matches)
        doc2, source2 = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            no_cache=False,
            scan_mode="inprocess",
        )
        doc2 = doc2.document
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
            scan_mode="inprocess",
        )
        # Second call with no_cache=True should still scan
        _, source = resolve_library_document(
            "tests.sample_module",
            cache_dir=cache_dir,
            no_cache=True,
            scan_mode="inprocess",
        )
        assert source == "scan"

    def test_error_for_missing_package(self, tmp_path: Path):
        """Should raise ImportError for packages that cannot be scanned."""
        with pytest.raises(ImportError, match="Cannot resolve library"):
            resolve_library_document(
                "nonexistent_package_xyz_123",
                cache_dir=tmp_path / "cache",
                no_cache=True,
                scan_mode="inprocess",
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
                scan_mode="inprocess",
            )

        assert source == "registry"

    def test_registry_not_used_when_scan_succeeds(self, tmp_path: Path):
        """Should not contact registry when local scan succeeds."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            result, source = resolve_library_document(
                "tests.sample_module",
                cache_dir=tmp_path / "cache",
                no_cache=True,
                registry_url="https://registry.example.com",
                scan_mode="inprocess",
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
                scan_mode="inprocess",
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
                    scan_mode="inprocess",
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
                scan_mode="inprocess",
            )

        assert source == "registry"
        assert cache_dir.exists()


class TestResolveReportsUnresolved:
    """An agent resolving a facade must be told where the surface lives."""

    def test_resolve_document_carries_unresolved(self, tmp_path):
        from lcp.mcp_server import resolve_library_document

        result, source = resolve_library_document(
            "sample_package.convenience",
            cache_dir=tmp_path,
            no_cache=True,
            scan_mode="inprocess",
        )

        assert source == "scan"
        assert result.unresolved_reexports == [("sample_package.core", 2, 1)]

    def test_cache_and_registry_hits_carry_nothing(self, tmp_path):
        """Only a live scan can produce the diagnostic."""
        from lcp.mcp_server import resolve_library_document

        first, _ = resolve_library_document(
            "sample_package.convenience", cache_dir=tmp_path, scan_mode="inprocess"
        )
        assert first.unresolved_reexports == [("sample_package.core", 2, 1)]

        second, source = resolve_library_document(
            "sample_package.convenience", cache_dir=tmp_path, scan_mode="inprocess"
        )
        assert source == "cache"
        assert second.unresolved_reexports == []


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
# Tests for the V2 universal server surface (spec D1-D9)
# ---------------------------------------------------------------------------


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

    def test_version_mismatch_flag_when_cache_differs_from_installed(
        self, tmp_path, sample_lcp_file, monkeypatch
    ):
        """A cache hit for a version other than the installed one is flagged."""
        monkeypatch.setattr(
            "lcp.mcp_server._installed_version", lambda name: "1.0.0"
        )
        cache_dir = tmp_path / "cache"
        doc = load_lcp_document(sample_lcp_file)
        doc.manifest.library.version = "9.9.9"
        _save_to_cache(cache_dir, doc)

        server = create_universal_server(cache_dir=cache_dir)
        result = server.tools["resolve_library"](
            name="tests.sample_module", version="9.9.9"
        )
        assert result["status"] == "loaded"
        assert result["source"] == "cache"
        assert result["version_mismatch"] is True
        assert result["installed_version"] == "1.0.0"
        assert result["resolved_version"] == "9.9.9"

    def test_version_mismatch_flag_when_not_installed(
        self, tmp_path, sample_lcp_file, monkeypatch
    ):
        """Cache/registry hit with no local install → flagged, installed None."""
        monkeypatch.setattr(
            "lcp.mcp_server._installed_version", lambda name: None
        )
        cache_dir = tmp_path / "cache"
        doc = load_lcp_document(sample_lcp_file)
        _save_to_cache(cache_dir, doc)

        server = create_universal_server(cache_dir=cache_dir)
        result = server.tools["resolve_library"](name="tests.sample_module")
        assert result["status"] == "loaded"
        assert result["source"] == "cache"
        assert result["version_mismatch"] is True
        assert result["installed_version"] is None
        assert result["resolved_version"] == doc.manifest.library.version

    def test_no_mismatch_flag_on_scan_source(self, universal_server):
        """A live scan is the installed version by definition — never flagged."""
        result = universal_server.tools["resolve_library"](
            name="tests.sample_module"
        )
        assert result["source"] == "scan"
        assert "version_mismatch" not in result

    def test_no_mismatch_flag_when_cache_matches_installed(
        self, tmp_path, sample_lcp_file, monkeypatch
    ):
        cache_dir = tmp_path / "cache"
        doc = load_lcp_document(sample_lcp_file)
        cached_version = doc.manifest.library.version
        _save_to_cache(cache_dir, doc)
        monkeypatch.setattr(
            "lcp.mcp_server._installed_version", lambda name: cached_version
        )

        server = create_universal_server(cache_dir=cache_dir)
        result = server.tools["resolve_library"](name="tests.sample_module")
        assert result["source"] == "cache"
        assert "version_mismatch" not in result

    def test_note_names_origin_when_reexports_are_unresolved(self, tmp_path):
        """A facade scan attaches a note naming the unscanned origin (#58)."""
        server = create_universal_server(
            cache_dir=tmp_path / "cache", no_cache=True, scan_mode="inprocess"
        )
        result = server.tools["resolve_library"](name="sample_package.convenience")

        assert result["status"] == "loaded"
        assert "note" in result
        assert "sample_package.core" in result["note"]
        assert "2 public names" in result["note"]
        assert "defined in sample_package.core" in result["note"]
        assert "resolve_library('sample_package.core')" in result["note"]

    def test_note_flags_additional_origins_when_more_than_one(
        self, tmp_path, monkeypatch, sample_lcp_file
    ):
        """The note must not silently drop origins beyond the first (FIX 2)."""
        from lcp.subprocess_scan import ScanResult

        doc = load_lcp_document(sample_lcp_file)
        fake_result = ScanResult(
            document=doc,
            unresolved_reexports=[("pkg.core", 3, 1), ("pkg.extras", 1, 1)],
        )
        monkeypatch.setattr(
            "lcp.mcp_server.resolve_library_document",
            lambda *a, **k: (fake_result, "scan"),
        )

        server = create_universal_server(cache_dir=tmp_path / "cache", no_cache=True)
        result = server.tools["resolve_library"](name="tests.sample_module")

        assert "note" in result
        assert "pkg.core" in result["note"]
        assert "3 public names" in result["note"]
        # The other origins are now named so the agent can act on them.
        assert "pkg.extras" in result["note"]
        # Distinct names, not the same ones restated at a second location.
        assert "Further names come from" in result["note"]
        # The tail must not promise full surface when other origins exist.
        assert "for the full surface" not in result["note"]
        assert "to recover that surface" in result["note"]

    def test_note_uses_under_wording_when_ancestor_spans_several_modules(
        self, tmp_path, monkeypatch, sample_lcp_file
    ):
        """A collapsed ancestor with several contributing modules reads "under"."""
        from lcp.subprocess_scan import ScanResult

        doc = load_lcp_document(sample_lcp_file)
        fake_result = ScanResult(
            document=doc,
            unresolved_reexports=[("google.cloud.firestore_v1", 55, 26)],
        )
        monkeypatch.setattr(
            "lcp.mcp_server.resolve_library_document",
            lambda *a, **k: (fake_result, "scan"),
        )

        server = create_universal_server(cache_dir=tmp_path / "cache", no_cache=True)
        result = server.tools["resolve_library"](name="tests.sample_module")

        assert "note" in result
        assert (
            "defined under google.cloud.firestore_v1 (26 modules)" in result["note"]
        )
        # Single ancestor: the tail still promises the full surface.
        assert "for the full surface" in result["note"]
        assert "to recover that surface" not in result["note"]

    def test_note_absent_when_no_reexports_are_unresolved(self, universal_server):
        """The happy path (no lost surface) must not carry a note at all."""
        result = universal_server.tools["resolve_library"](
            name="tests.sample_module"
        )
        assert "note" not in result


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
        assert any("#instance_method" in m["id"] for m in sym["members"])


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


class TestReviewFindings:
    """Regression tests for the Phase 2 independent-review findings."""

    def test_single_oversized_symbol_still_returned(self):
        """A symbol bigger than the cap must degrade, never disappear."""
        symbols = {
            "fake:Big": make_symbol(
                "class", summary="Big.", description="d" * 30_000
            )
        }
        for i in range(300):
            symbols[f"fake:Big#m{i:03d}"] = make_symbol("method", summary="z" * 150)
        idx = make_index(symbols)
        result = _get_symbols(idx, ["fake:Big"], max_bytes=25_000)
        assert [s["id"] for s in result["symbols"]] == ["fake:Big"]
        assert "not_returned" not in result
        sym = result["symbols"][0]
        assert sym.get("members_truncated") is True
        # the returned entry itself respects the cap
        assert len(json.dumps(sym, default=str)) <= 25_000

    def test_not_found_and_truncation_hints_coexist(self):
        big = {
            f"fake:f{i:02d}": make_symbol("function", summary="y" * 400)
            for i in range(40)
        }
        idx = make_index(big)
        result = _get_symbols(idx, ["fake:missing", *sorted(big)], max_bytes=2_000)
        assert result["not_found"] == ["fake:missing"]
        assert result["truncated"] is True
        assert "not found" in result["hint"]
        assert "byte cap" in result["hint"]

    def test_overview_truncation_has_hint(self):
        idx = make_index(
            {
                f"fake.m{i:03d}:f": make_symbol("function", module=f"fake.m{i:03d}")
                for i in range(600)
            }
        )
        result = _overview(idx, max_bytes=1_000)
        assert result["truncated"] is True
        assert "hint" in result

    def test_blank_expose_fails_closed(self, tmp_path):
        server = create_universal_server(
            cache_dir=tmp_path / "cache", no_cache=True, expose=["  "]
        )
        result = server.tools["resolve_library"](name="json")
        assert result["error"]["code"] == "library_not_exposed"

    def test_resolve_reports_registration_key(self, tmp_path, sample_lcp_file):
        """The response 'name' must be the key usable as library=..."""
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
        assert result["name"] == "nonexistent_package_xyz_123"
        follow_up = server.tools["get_overview"](
            library="nonexistent_package_xyz_123"
        )
        assert "error" not in follow_up

    def test_create_server_resolve_does_not_override_manifest(
        self, sample_lcp_file
    ):
        """resolve_library must not clobber a manifest-pinned library."""
        with pytest.warns(DeprecationWarning):
            server = create_server(sample_lcp_file)
        result = server.tools["resolve_library"](name="tests.sample_module")
        assert result["status"] == "loaded"
        assert result["source"] == "manifest"
        overview = server.tools["get_overview"]()
        assert overview["library"]["source"] == "manifest"


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
        doc = generate_lcp(scan_package("sample_package"))
        index = LCPIndex(doc)
        result = _get_symbols(index, ["sample_package:CoreClass"])
        (entry,) = result["symbols"]
        assert entry["resolved_via_alias"] == "sample_package.core:CoreClass"
        assert entry["import"] == "from sample_package import CoreClass"
        member = _get_symbols(index, ["sample_package:CoreClass#do_something"])
        assert member["not_found"] == []


def _documented_symbol() -> Symbol:
    return Symbol(
        kind=SymbolKind.FUNCTION,
        module="pkg",
        signatures=[
            Signature(
                params=[Param(name="x", type="int", description="The x value.")],
                returns="str",
                returns_description="The rendered result.",
                raises=[RaisesEntry(type="ValueError", condition="If x < 0.")],
            )
        ],
        semantics=Semantics(
            summary="Do a thing.",
            examples=[
                Example(code=">>> do_thing(1)\n'ok'", description="Basic."),
                Example(code=">>> do_thing(2)\n'ok2'"),
            ],
        ),
    )


class TestStructuredFieldsInGetSymbol:
    """Phase 4: structured docstring fields flow into get_symbol responses."""

    def test_structured_fields_exposed(self):
        symbol = _documented_symbol()
        index = make_index({"pkg:do_thing": symbol}, name="pkg")
        detail = _symbol_detail(index, "pkg:do_thing", symbol, 25_000)
        sig = detail["signatures"][0]
        assert sig["params"][0]["description"] == "The x value."
        assert sig["returns_description"] == "The rendered result."
        assert sig["raises"] == [{"type": "ValueError", "condition": "If x < 0."}]
        assert len(detail["semantics"]["examples"]) == 2

    def test_examples_truncated_before_description(self):
        symbol = _documented_symbol()
        symbol.semantics.description = "prose " * 50
        big = Example(code=">>> big()\n" + "x" * 2000)
        symbol.semantics.examples = [symbol.semantics.examples[0], big]
        index = make_index({"pkg:do_thing": symbol}, name="pkg")
        detail = _symbol_detail(index, "pkg:do_thing", symbol, 1_200)
        assert detail.get("examples_truncated") is True
        assert len(json.dumps(detail, default=str)) <= 1_200
        # the description survived because examples were sacrificed first
        assert detail["semantics"]["description"].startswith("prose")

    def test_all_examples_dropped_when_budget_is_tiny(self):
        symbol = _documented_symbol()
        symbol.semantics.examples = [
            Example(code=">>> big()\n" + "x" * 3000),
            Example(code=">>> bigger()\n" + "y" * 3000),
        ]
        index = make_index({"pkg:do_thing": symbol}, name="pkg")
        detail = _symbol_detail(index, "pkg:do_thing", symbol, 900)
        assert detail.get("examples_truncated") is True
        assert "examples" not in detail.get("semantics", {})
        assert len(json.dumps(detail, default=str)) <= 900

    def test_no_truncation_marker_when_within_budget(self):
        symbol = _documented_symbol()
        index = make_index({"pkg:do_thing": symbol}, name="pkg")
        detail = _symbol_detail(index, "pkg:do_thing", symbol, 25_000)
        assert "examples_truncated" not in detail
