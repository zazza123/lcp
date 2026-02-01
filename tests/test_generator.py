"""Tests for the generator module."""

import pytest

from lcp.generator import (
    _build_symbol_id,
    _convert_param,
    _convert_signature,
    _convert_symbol,
    _param_kind_to_lcp,
    _symbol_kind_to_lcp,
    generate_lcp,
)
from lcp.models import (
    LCPDocument,
    ParamKind,
    SymbolKind,
)
from lcp.scanner import (
    ScannedModule,
    ScannedParam,
    ScannedSignature,
    ScannedSymbol,
)


class TestSymbolKindToLcp:
    """Tests for _symbol_kind_to_lcp function."""

    def test_all_kinds(self):
        assert _symbol_kind_to_lcp("function") == SymbolKind.FUNCTION
        assert _symbol_kind_to_lcp("class") == SymbolKind.CLASS
        assert _symbol_kind_to_lcp("method") == SymbolKind.METHOD
        assert _symbol_kind_to_lcp("attribute") == SymbolKind.ATTRIBUTE
        assert _symbol_kind_to_lcp("module") == SymbolKind.MODULE
        assert _symbol_kind_to_lcp("constant") == SymbolKind.CONSTANT

    def test_unknown_kind(self):
        # Should default to function
        assert _symbol_kind_to_lcp("unknown") == SymbolKind.FUNCTION


class TestParamKindToLcp:
    """Tests for _param_kind_to_lcp function."""

    def test_all_kinds(self):
        assert _param_kind_to_lcp("positional") == ParamKind.POSITIONAL
        assert _param_kind_to_lcp("keyword") == ParamKind.KEYWORD
        assert _param_kind_to_lcp("positional_only") == ParamKind.POSITIONAL_ONLY
        assert _param_kind_to_lcp("keyword_only") == ParamKind.KEYWORD_ONLY
        assert _param_kind_to_lcp("rest") == ParamKind.REST

    def test_unknown_kind(self):
        assert _param_kind_to_lcp("unknown") is None


class TestBuildSymbolId:
    """Tests for _build_symbol_id function."""

    def test_module_symbol(self):
        symbol = ScannedSymbol(
            name="mymodule",
            qualified_name="",
            module_path="mymodule",
            kind="module",
        )
        assert _build_symbol_id(symbol) == "mymodule:"

    def test_function_symbol(self):
        symbol = ScannedSymbol(
            name="my_func",
            qualified_name="my_func",
            module_path="mymodule",
            kind="function",
        )
        assert _build_symbol_id(symbol) == "mymodule:my_func"

    def test_class_symbol(self):
        symbol = ScannedSymbol(
            name="MyClass",
            qualified_name="MyClass",
            module_path="mymodule.submodule",
            kind="class",
        )
        assert _build_symbol_id(symbol) == "mymodule.submodule:MyClass"

    def test_method_symbol(self):
        symbol = ScannedSymbol(
            name="my_method",
            qualified_name="MyClass#my_method",
            module_path="mymodule",
            kind="method",
        )
        assert _build_symbol_id(symbol) == "mymodule:MyClass#my_method"


class TestConvertParam:
    """Tests for _convert_param function."""

    def test_required_param(self):
        scanned = ScannedParam(name="x", type_hint="int")
        param = _convert_param(scanned)
        assert param.name == "x"
        assert param.type == "int"
        assert param.required is True
        assert param.default is None

    def test_optional_param_with_simple_default(self):
        scanned = ScannedParam(name="x", type_hint="int", default=10)
        param = _convert_param(scanned)
        assert param.required is False
        assert param.default == 10

    def test_optional_param_with_none_default(self):
        scanned = ScannedParam(name="x", type_hint="Optional[str]", default=None)
        param = _convert_param(scanned)
        assert param.required is False
        assert param.default is None

    def test_param_without_type_hint(self):
        scanned = ScannedParam(name="x")
        param = _convert_param(scanned)
        assert param.type == "Any"

    def test_variadic_param(self):
        scanned = ScannedParam(name="args", type_hint="Any", kind="rest")
        param = _convert_param(scanned)
        assert param.variadic is True
        assert param.kind == ParamKind.REST


class TestConvertSignature:
    """Tests for _convert_signature function."""

    def test_simple_signature(self):
        scanned = ScannedSignature(
            params=[ScannedParam(name="x", type_hint="int")],
            return_type="str",
            is_async=False,
        )
        sig = _convert_signature(scanned)
        assert len(sig.params) == 1
        assert sig.returns == "str"
        assert sig.async_ is False

    def test_async_signature(self):
        scanned = ScannedSignature(
            params=[],
            return_type="dict",
            is_async=True,
        )
        sig = _convert_signature(scanned)
        assert sig.async_ is True

    def test_empty_params(self):
        scanned = ScannedSignature(params=[], return_type="None")
        sig = _convert_signature(scanned)
        assert sig.params is None or len(sig.params) == 0


class TestConvertSymbol:
    """Tests for _convert_symbol function."""

    def test_convert_function(self):
        scanned = ScannedSymbol(
            name="my_func",
            qualified_name="my_func",
            module_path="mymodule",
            kind="function",
            summary="A test function.",
            signature=ScannedSignature(
                params=[ScannedParam(name="x", type_hint="int")],
                return_type="int",
            ),
        )
        symbol_id, symbol = _convert_symbol(scanned)
        assert symbol_id == "mymodule:my_func"
        assert symbol.kind == SymbolKind.FUNCTION
        assert symbol.semantics.summary == "A test function."
        assert symbol.signatures is not None
        assert len(symbol.signatures) == 1

    def test_convert_class(self):
        scanned = ScannedSymbol(
            name="MyClass",
            qualified_name="MyClass",
            module_path="mymodule",
            kind="class",
            summary="A test class.",
        )
        symbol_id, symbol = _convert_symbol(scanned)
        assert symbol_id == "mymodule:MyClass"
        assert symbol.kind == SymbolKind.CLASS

    def test_convert_module(self):
        scanned = ScannedSymbol(
            name="mymodule",
            qualified_name="",
            module_path="mymodule",
            kind="module",
            summary="Module mymodule",
        )
        symbol_id, symbol = _convert_symbol(scanned)
        assert symbol_id == "mymodule:"
        assert symbol.kind == SymbolKind.MODULE

    def test_default_summary(self):
        scanned = ScannedSymbol(
            name="my_func",
            qualified_name="my_func",
            module_path="mymodule",
            kind="function",
            summary=None,
        )
        _, symbol = _convert_symbol(scanned)
        assert "Function" in symbol.semantics.summary


class TestGenerateLcp:
    """Tests for generate_lcp function."""

    def test_generate_minimal(self):
        scanned = ScannedModule(
            name="testlib",
            version="1.0.0",
            symbols=[
                ScannedSymbol(
                    name="testlib",
                    qualified_name="",
                    module_path="testlib",
                    kind="module",
                    summary="Test library.",
                ),
            ],
        )
        doc = generate_lcp(scanned)
        assert isinstance(doc, LCPDocument)
        assert doc.manifest.library.name == "testlib"
        assert doc.manifest.library.version == "1.0.0"
        assert "testlib:" in doc.symbols

    def test_generate_with_functions(self):
        scanned = ScannedModule(
            name="testlib",
            version="1.0.0",
            symbols=[
                ScannedSymbol(
                    name="testlib",
                    qualified_name="",
                    module_path="testlib",
                    kind="module",
                    summary="Test library.",
                ),
                ScannedSymbol(
                    name="my_func",
                    qualified_name="my_func",
                    module_path="testlib",
                    kind="function",
                    summary="A function.",
                    signature=ScannedSignature(
                        params=[ScannedParam(name="x", type_hint="int")],
                        return_type="int",
                    ),
                ),
            ],
        )
        doc = generate_lcp(scanned)
        assert "testlib:my_func" in doc.symbols
        func_symbol = doc.symbols["testlib:my_func"]
        assert func_symbol.kind == SymbolKind.FUNCTION

    def test_generate_with_class_members(self):
        scanned = ScannedModule(
            name="testlib",
            version="1.0.0",
            symbols=[
                ScannedSymbol(
                    name="MyClass",
                    qualified_name="MyClass",
                    module_path="testlib",
                    kind="class",
                    summary="A class.",
                    members=[
                        ScannedSymbol(
                            name="my_method",
                            qualified_name="MyClass#my_method",
                            module_path="testlib",
                            kind="method",
                            summary="A method.",
                        ),
                    ],
                ),
            ],
        )
        doc = generate_lcp(scanned)
        assert "testlib:MyClass" in doc.symbols
        assert "testlib:MyClass#my_method" in doc.symbols

    def test_manifest_fields(self):
        scanned = ScannedModule(name="testlib", version="2.1.0", symbols=[])
        doc = generate_lcp(scanned)
        assert doc.manifest.schema_version == "1.0"
        assert doc.manifest.library.language == "python"
        assert doc.manifest.symbol_resolution == "fully-qualified"
        assert doc.manifest.generation is not None
        assert doc.manifest.generation.tool == "lcp"

    def test_detailed_index(self):
        scanned = ScannedModule(
            name="testlib",
            version="1.0.0",
            symbols=[
                ScannedSymbol(
                    name="my_func",
                    qualified_name="my_func",
                    module_path="testlib",
                    kind="function",
                    summary="A function.",
                    source_file="/path/to/file.py",
                    source_lines=(10, 20),
                ),
            ],
        )
        doc = generate_lcp(scanned)
        assert doc.detailed_index is not None
        assert "testlib:my_func" in doc.detailed_index
        entry = doc.detailed_index["testlib:my_func"]
        assert entry.implementation.path == "/path/to/file.py"
        assert entry.implementation.lines == [10, 20]
