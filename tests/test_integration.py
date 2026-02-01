"""Integration tests for the lcp."""

import json

import pytest

from lcp import (
    LCPDocument,
    LCPValidationError,
    generate_lcp,
    is_valid,
    scan,
    scan_package,
    validate_document,
)


class TestScanFunction:
    """Tests for the main scan() function."""

    def test_scan_builtin_module(self):
        doc = scan("json")
        assert isinstance(doc, LCPDocument)
        assert doc.manifest.library.name == "json"
        assert len(doc.symbols) > 0

    def test_scan_with_validation(self):
        doc = scan("collections", validate=True)
        assert is_valid(doc)

    def test_scan_without_validation(self):
        doc = scan("json", validate=False)
        assert isinstance(doc, LCPDocument)

    def test_scan_include_private(self):
        doc_public = scan("json", include_private=False)
        doc_private = scan("json", include_private=True)
        # Private scan might have more symbols
        assert len(doc_private.symbols) >= len(doc_public.symbols)

    def test_scan_nonexistent_package(self):
        with pytest.raises(ImportError):
            scan("nonexistent_package_12345")


class TestFullPipeline:
    """Tests for the full scan -> generate -> validate pipeline."""

    def test_json_module(self):
        """Test complete pipeline with json module."""
        # Scan
        scanned = scan_package("json", recursive=False)
        assert scanned.name == "json"
        assert len(scanned.symbols) > 0

        # Generate
        doc = generate_lcp(scanned)
        assert isinstance(doc, LCPDocument)

        # Validate
        errors = validate_document(doc)
        assert errors == [], f"Validation errors: {errors}"

        # Check structure
        assert doc.manifest.schema_version == "1.0"
        assert doc.manifest.library.language == "python"
        assert "json:" in doc.symbols  # Module symbol
        
        # Check for known json functions
        symbol_ids = list(doc.symbols.keys())
        assert any("loads" in sid for sid in symbol_ids)
        assert any("dumps" in sid for sid in symbol_ids)

    def test_collections_module(self):
        """Test complete pipeline with collections module."""
        doc = scan("collections", recursive=False)

        assert doc.manifest.library.name == "collections"
        assert is_valid(doc)

        # Check for known collections classes
        symbol_ids = list(doc.symbols.keys())
        assert any("Counter" in sid for sid in symbol_ids)
        assert any("deque" in sid for sid in symbol_ids)

    def test_output_json_serializable(self):
        """Test that output is JSON serializable."""
        doc = scan("json", recursive=False)
        
        # Convert to dict
        data = doc.to_dict()
        assert isinstance(data, dict)

        # Serialize to JSON
        json_str = doc.to_json()
        assert isinstance(json_str, str)

        # Parse back
        parsed = json.loads(json_str)
        assert parsed["manifest"]["library"]["name"] == "json"

    def test_output_to_file(self, temp_dir):
        """Test writing output to file."""
        doc = scan("json", recursive=False)
        output_path = temp_dir / "json.lcp.json"

        doc.to_file(str(output_path))
        assert output_path.exists()

        with open(output_path) as f:
            data = json.load(f)

        assert data["manifest"]["library"]["name"] == "json"


class TestSymbolIdFormat:
    """Tests for LCP symbol ID format compliance."""

    def test_module_symbol_id(self):
        """Module symbols should have format 'module:'"""
        doc = scan("json", recursive=False)
        module_symbols = [
            (sid, sym) for sid, sym in doc.symbols.items()
            if sym.kind.value == "module"
        ]
        for sid, sym in module_symbols:
            assert sid.endswith(":"), f"Module symbol ID should end with ':': {sid}"

    def test_function_symbol_id(self):
        """Function symbols should have format 'module:name'"""
        doc = scan("json", recursive=False)
        func_symbols = [
            (sid, sym) for sid, sym in doc.symbols.items()
            if sym.kind.value == "function"
        ]
        for sid, sym in func_symbols:
            assert ":" in sid, f"Function symbol ID should contain ':': {sid}"
            parts = sid.split(":")
            assert len(parts) == 2, f"Function symbol ID should have format 'module:name': {sid}"
            assert parts[1] != "", f"Function symbol ID should have non-empty name: {sid}"

    def test_method_symbol_id(self):
        """Method symbols should have format 'module:Class#method'"""
        doc = scan("collections", recursive=False)
        method_symbols = [
            (sid, sym) for sid, sym in doc.symbols.items()
            if sym.kind.value == "method"
        ]
        for sid, sym in method_symbols:
            assert "#" in sid, f"Method symbol ID should contain '#': {sid}"


class TestLCPSchemaCompliance:
    """Tests for LCP v1 schema compliance."""

    def test_required_fields_present(self):
        """Test that all required fields are present."""
        doc = scan("json", recursive=False)
        data = doc.to_dict()

        # Manifest required fields
        assert "schema_version" in data["manifest"]
        assert data["manifest"]["schema_version"] == "1.0"
        assert "library" in data["manifest"]
        assert "name" in data["manifest"]["library"]
        assert "version" in data["manifest"]["library"]
        assert "language" in data["manifest"]["library"]

        # Symbol required fields
        for sid, sym in data["symbols"].items():
            assert "kind" in sym, f"Symbol {sid} missing 'kind'"
            assert "semantics" in sym, f"Symbol {sid} missing 'semantics'"
            assert "summary" in sym["semantics"], f"Symbol {sid} missing 'semantics.summary'"

    def test_valid_symbol_kinds(self):
        """Test that all symbol kinds are valid."""
        valid_kinds = {"function", "class", "method", "attribute", "module", "constant"}
        doc = scan("json", recursive=False)
        
        for sid, sym in doc.symbols.items():
            assert sym.kind.value in valid_kinds, f"Invalid kind '{sym.kind}' for symbol {sid}"

    def test_signature_structure(self):
        """Test that signatures have correct structure."""
        doc = scan("json", recursive=False)
        
        for sid, sym in doc.symbols.items():
            if sym.signatures:
                for sig in sym.signatures:
                    if sig.params:
                        for param in sig.params:
                            assert param.name is not None
                            assert param.type is not None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_module(self):
        """Test scanning a minimal module."""
        # Create a minimal document
        doc = scan("json", recursive=False)
        # Even if filtering removes everything, should still be valid
        assert is_valid(doc)

    def test_unicode_in_docstrings(self):
        """Test handling of unicode in docstrings."""
        doc = scan("json", recursive=False)
        # Should not raise any encoding errors
        json_str = doc.to_json()
        assert isinstance(json_str, str)

    def test_circular_import_handling(self):
        """Test that circular imports don't cause infinite loops."""
        # collections has some internal circular references
        doc = scan("collections", recursive=True)
        assert isinstance(doc, LCPDocument)
