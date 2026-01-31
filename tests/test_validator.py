"""Tests for the validator module."""

import json

import pytest

from lcp_python_sdk.models import (
    LCPDocument,
    Library,
    Manifest,
    Semantics,
    Symbol,
    SymbolKind,
)
from lcp_python_sdk.validator import (
    LCPValidationError,
    is_valid,
    validate_dict,
    validate_document,
    validate_file,
    validate_or_raise,
)


class TestValidateDict:
    """Tests for validate_dict function."""

    def test_valid_minimal_document(self, sample_lcp_dict):
        errors = validate_dict(sample_lcp_dict)
        assert errors == []

    def test_invalid_missing_manifest(self):
        data = {"symbols": {}}
        errors = validate_dict(data)
        assert len(errors) > 0
        assert any("manifest" in e.lower() for e in errors)

    def test_invalid_missing_symbols(self):
        data = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": "test", "version": "1.0.0", "language": "python"},
            }
        }
        errors = validate_dict(data)
        assert len(errors) > 0
        assert any("symbols" in e.lower() for e in errors)

    def test_invalid_missing_library(self, invalid_lcp_dict):
        errors = validate_dict(invalid_lcp_dict)
        assert len(errors) > 0
        assert any("library" in e.lower() for e in errors)

    def test_invalid_schema_version(self):
        data = {
            "manifest": {
                "schema_version": "2.0",  # Invalid - must be "1.0"
                "library": {"name": "test", "version": "1.0.0", "language": "python"},
            },
            "symbols": {},
        }
        errors = validate_dict(data)
        assert len(errors) > 0

    def test_invalid_symbol_missing_kind(self):
        data = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": "test", "version": "1.0.0", "language": "python"},
            },
            "symbols": {
                "test:func": {
                    # Missing "kind"
                    "semantics": {"summary": "A function."},
                }
            },
        }
        errors = validate_dict(data)
        assert len(errors) > 0
        assert any("kind" in e.lower() for e in errors)

    def test_invalid_symbol_missing_semantics(self):
        data = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": "test", "version": "1.0.0", "language": "python"},
            },
            "symbols": {
                "test:func": {
                    "kind": "function",
                    # Missing "semantics"
                }
            },
        }
        errors = validate_dict(data)
        assert len(errors) > 0
        assert any("semantics" in e.lower() for e in errors)

    def test_invalid_symbol_kind(self):
        data = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": "test", "version": "1.0.0", "language": "python"},
            },
            "symbols": {
                "test:func": {
                    "kind": "invalid_kind",  # Not a valid kind
                    "semantics": {"summary": "A function."},
                }
            },
        }
        errors = validate_dict(data)
        assert len(errors) > 0

    def test_valid_full_document(self):
        data = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": "test", "version": "1.0.0", "language": "python"},
                "distribution": "pypi",
                "license": "MIT",
                "symbol_resolution": "fully-qualified",
            },
            "symbols": {
                "test:": {
                    "kind": "module",
                    "module": "test",
                    "semantics": {"summary": "Test module."},
                },
                "test:func": {
                    "kind": "function",
                    "module": "test",
                    "signatures": [
                        {
                            "params": [
                                {"name": "x", "type": "int", "required": True}
                            ],
                            "returns": "int",
                        }
                    ],
                    "semantics": {
                        "summary": "A function.",
                        "description": "Longer description.",
                    },
                },
            },
            "deprecations": {
                "test:old_func": {
                    "deprecated_in": "1.0.0",
                    "replaced_by": "test:func",
                }
            },
        }
        errors = validate_dict(data)
        assert errors == []


class TestValidateDocument:
    """Tests for validate_document function."""

    def test_valid_document(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="test", version="1.0.0", language="python")
            ),
            symbols={
                "test:func": Symbol(
                    kind=SymbolKind.FUNCTION,
                    semantics=Semantics(summary="A function."),
                )
            },
        )
        errors = validate_document(doc)
        assert errors == []

    def test_empty_symbols(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="test", version="1.0.0", language="python")
            ),
            symbols={},
        )
        errors = validate_document(doc)
        assert errors == []  # Empty symbols is valid


class TestValidateFile:
    """Tests for validate_file function."""

    def test_valid_file(self, sample_lcp_file):
        errors = validate_file(sample_lcp_file)
        assert errors == []

    def test_invalid_file(self, temp_dir, invalid_lcp_dict):
        path = temp_dir / "invalid.lcp.json"
        with open(path, "w") as f:
            json.dump(invalid_lcp_dict, f)

        errors = validate_file(path)
        assert len(errors) > 0


class TestIsValid:
    """Tests for is_valid function."""

    def test_valid_dict(self, sample_lcp_dict):
        assert is_valid(sample_lcp_dict) is True

    def test_invalid_dict(self, invalid_lcp_dict):
        assert is_valid(invalid_lcp_dict) is False

    def test_valid_document(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="test", version="1.0.0", language="python")
            ),
            symbols={},
        )
        assert is_valid(doc) is True


class TestValidateOrRaise:
    """Tests for validate_or_raise function."""

    def test_valid_document_no_raise(self, sample_lcp_dict):
        # Should not raise
        validate_or_raise(sample_lcp_dict)

    def test_invalid_document_raises(self, invalid_lcp_dict):
        with pytest.raises(LCPValidationError) as exc_info:
            validate_or_raise(invalid_lcp_dict)

        assert len(exc_info.value.errors) > 0
        assert "library" in str(exc_info.value).lower()

    def test_valid_lcp_document_no_raise(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="test", version="1.0.0", language="python")
            ),
            symbols={},
        )
        # Should not raise
        validate_or_raise(doc)


class TestLCPValidationError:
    """Tests for LCPValidationError exception."""

    def test_error_message(self):
        errors = ["Error 1", "Error 2", "Error 3"]
        exc = LCPValidationError(errors)
        assert exc.errors == errors
        assert "3 error(s)" in str(exc)
        assert "Error 1" in str(exc)

    def test_error_truncation(self):
        errors = [f"Error {i}" for i in range(15)]
        exc = LCPValidationError(errors)
        message = str(exc)
        assert "5 more errors" in message
