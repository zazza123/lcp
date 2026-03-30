"""Tests for the diff module."""

import json

import pytest

from lcp.diff import (
    DiffResult,
    SymbolDiff,
    diff_documents,
    load_lcp_document,
    update_document,
)
from lcp.models import (
    Deprecation,
    LCPDocument,
    Library,
    Manifest,
    Semantics,
    Symbol,
    SymbolKind,
)


def _make_doc(
    name: str = "test-lib",
    version: str = "1.0.0",
    symbols: dict[str, Symbol] | None = None,
) -> LCPDocument:
    """Helper to build a minimal LCPDocument."""
    return LCPDocument(
        manifest=Manifest(
            schema_version="1.0",
            library=Library(name=name, version=version, language="python"),
        ),
        symbols=symbols or {},
    )


def _make_symbol(
    kind: SymbolKind = SymbolKind.FUNCTION,
    module: str = "mod",
    summary: str = "A symbol.",
) -> Symbol:
    return Symbol(
        kind=kind,
        module=module,
        semantics=Semantics(summary=summary),
    )


# ---------------------------------------------------------------------------
# diff_documents
# ---------------------------------------------------------------------------


class TestDiffDocuments:
    """Tests for diff_documents()."""

    def test_identical_documents(self):
        symbols = {"mod:func": _make_symbol()}
        old = _make_doc(version="1.0.0", symbols=symbols)
        new = _make_doc(version="1.1.0", symbols=dict(symbols))

        result = diff_documents(old, new)

        assert result.removed == []
        assert result.added == []
        assert result.deprecated == {}
        assert result.old_version == "1.0.0"
        assert result.new_version == "1.1.0"
        assert result.library_name == "test-lib"

    def test_removed_symbols_detected(self):
        old = _make_doc(
            version="1.0.0",
            symbols={
                "mod:func_a": _make_symbol(summary="Function A"),
                "mod:func_b": _make_symbol(summary="Function B"),
            },
        )
        new = _make_doc(
            version="2.0.0",
            symbols={
                "mod:func_a": _make_symbol(summary="Function A"),
            },
        )

        result = diff_documents(old, new)

        assert len(result.removed) == 1
        assert result.removed[0].symbol_id == "mod:func_b"
        assert result.added == []

    def test_added_symbols_detected(self):
        old = _make_doc(
            version="1.0.0",
            symbols={"mod:func_a": _make_symbol()},
        )
        new = _make_doc(
            version="2.0.0",
            symbols={
                "mod:func_a": _make_symbol(),
                "mod:func_b": _make_symbol(summary="New function"),
            },
        )

        result = diff_documents(old, new)

        assert result.removed == []
        assert len(result.added) == 1
        assert result.added[0].symbol_id == "mod:func_b"

    def test_removed_and_added(self):
        old = _make_doc(
            version="1.0.0",
            symbols={
                "mod:old_func": _make_symbol(summary="Old"),
                "mod:common": _make_symbol(summary="Common"),
            },
        )
        new = _make_doc(
            version="2.0.0",
            symbols={
                "mod:common": _make_symbol(summary="Common"),
                "mod:new_func": _make_symbol(summary="New"),
            },
        )

        result = diff_documents(old, new)

        assert len(result.removed) == 1
        assert result.removed[0].symbol_id == "mod:old_func"
        assert len(result.added) == 1
        assert result.added[0].symbol_id == "mod:new_func"

    def test_deprecation_entries_created(self):
        old = _make_doc(
            version="1.0.0",
            symbols={"mod:func_a": _make_symbol()},
        )
        new = _make_doc(
            version="2.0.0",
            symbols={},
        )

        result = diff_documents(old, new)

        assert "mod:func_a" in result.deprecated
        dep = result.deprecated["mod:func_a"]
        assert isinstance(dep, Deprecation)
        assert dep.deprecated_in == "2.0.0"

    def test_empty_documents(self):
        old = _make_doc(version="0.1.0", symbols={})
        new = _make_doc(version="0.2.0", symbols={})

        result = diff_documents(old, new)

        assert result.removed == []
        assert result.added == []
        assert result.deprecated == {}

    def test_symbol_diff_kind_and_module(self):
        old = _make_doc(
            version="1.0.0",
            symbols={
                "pkg:MyClass": _make_symbol(
                    kind=SymbolKind.CLASS, module="pkg", summary="A class."
                ),
            },
        )
        new = _make_doc(version="2.0.0", symbols={})

        result = diff_documents(old, new)

        assert result.removed[0].kind == "class"
        assert result.removed[0].module == "pkg"
        assert result.removed[0].summary == "A class."

    def test_results_sorted(self):
        old = _make_doc(
            version="1.0.0",
            symbols={
                "mod:z_func": _make_symbol(),
                "mod:a_func": _make_symbol(),
                "mod:m_func": _make_symbol(),
            },
        )
        new = _make_doc(version="2.0.0", symbols={})

        result = diff_documents(old, new)

        ids = [s.symbol_id for s in result.removed]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# DiffResult serialization
# ---------------------------------------------------------------------------


class TestDiffResultSerialization:
    """Tests for DiffResult serialization methods."""

    def test_to_dict(self):
        result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="mylib",
            removed=[SymbolDiff("mod:f", "function", "mod", "A func")],
            added=[SymbolDiff("mod:g", "function", "mod", "New func")],
            deprecated={"mod:f": Deprecation(deprecated_in="2.0.0")},
        )

        data = result.to_dict()

        assert data["library"] == "mylib"
        assert data["old_version"] == "1.0.0"
        assert data["new_version"] == "2.0.0"
        assert data["summary"]["removed"] == 1
        assert data["summary"]["added"] == 1
        assert len(data["removed"]) == 1
        assert data["removed"][0]["symbol_id"] == "mod:f"
        assert len(data["added"]) == 1
        assert data["deprecations"]["mod:f"]["deprecated_in"] == "2.0.0"

    def test_to_json(self):
        result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="mylib",
        )
        output = result.to_json()
        parsed = json.loads(output)
        assert parsed["library"] == "mylib"

    def test_to_dict_empty(self):
        result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="mylib",
        )
        data = result.to_dict()
        assert data["summary"]["removed"] == 0
        assert data["summary"]["added"] == 0
        assert data["removed"] == []
        assert data["added"] == []
        assert data["deprecations"] == {}


# ---------------------------------------------------------------------------
# load_lcp_document
# ---------------------------------------------------------------------------


class TestLoadLCPDocument:
    """Tests for load_lcp_document()."""

    def test_load_valid_file(self, temp_dir):
        doc = _make_doc(version="1.0.0", symbols={"mod:f": _make_symbol()})
        path = temp_dir / "doc.lcp.json"
        doc.to_file(str(path))

        loaded = load_lcp_document(str(path))

        assert loaded.manifest.library.name == "test-lib"
        assert "mod:f" in loaded.symbols

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_lcp_document("/nonexistent/path.json")

    def test_load_invalid_json(self, temp_dir):
        path = temp_dir / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_lcp_document(str(path))


# ---------------------------------------------------------------------------
# update_document
# ---------------------------------------------------------------------------


class TestUpdateDocument:
    """Tests for update_document()."""

    def test_merges_deprecations_into_document(self):
        new_doc = _make_doc(
            version="2.0.0",
            symbols={"mod:func_a": _make_symbol()},
        )
        diff_result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="test-lib",
            deprecated={"mod:func_b": Deprecation(deprecated_in="2.0.0")},
        )

        updated = update_document(new_doc, diff_result)

        assert updated.deprecations is not None
        assert "mod:func_b" in updated.deprecations
        assert updated.deprecations["mod:func_b"].deprecated_in == "2.0.0"

    def test_preserves_existing_deprecations(self):
        new_doc = LCPDocument(
            manifest=Manifest(
                schema_version="1.0",
                library=Library(name="test-lib", version="2.0.0", language="python"),
            ),
            symbols={"mod:func_a": _make_symbol()},
            deprecations={
                "mod:old_func": Deprecation(
                    deprecated_in="1.5.0", notes="Use func_a instead"
                ),
            },
        )
        diff_result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="test-lib",
            deprecated={"mod:func_b": Deprecation(deprecated_in="2.0.0")},
        )

        updated = update_document(new_doc, diff_result)

        assert "mod:old_func" in updated.deprecations
        assert updated.deprecations["mod:old_func"].deprecated_in == "1.5.0"
        assert updated.deprecations["mod:old_func"].notes == "Use func_a instead"
        assert "mod:func_b" in updated.deprecations

    def test_does_not_overwrite_existing_entry(self):
        new_doc = LCPDocument(
            manifest=Manifest(
                schema_version="1.0",
                library=Library(name="test-lib", version="3.0.0", language="python"),
            ),
            symbols={},
            deprecations={
                "mod:func": Deprecation(
                    deprecated_in="2.0.0", notes="Original note"
                ),
            },
        )
        diff_result = DiffResult(
            old_version="2.0.0",
            new_version="3.0.0",
            library_name="test-lib",
            deprecated={
                "mod:func": Deprecation(deprecated_in="3.0.0"),
            },
        )

        updated = update_document(new_doc, diff_result)

        # Should keep the original entry, not overwrite
        assert updated.deprecations["mod:func"].deprecated_in == "2.0.0"
        assert updated.deprecations["mod:func"].notes == "Original note"

    def test_no_deprecations_returns_none(self):
        new_doc = _make_doc(version="2.0.0", symbols={})
        diff_result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="test-lib",
        )

        updated = update_document(new_doc, diff_result)

        assert updated.deprecations is None

    def test_does_not_mutate_original(self):
        new_doc = _make_doc(version="2.0.0", symbols={})
        diff_result = DiffResult(
            old_version="1.0.0",
            new_version="2.0.0",
            library_name="test-lib",
            deprecated={"mod:func": Deprecation(deprecated_in="2.0.0")},
        )

        updated = update_document(new_doc, diff_result)

        assert new_doc.deprecations is None
        assert updated.deprecations is not None
