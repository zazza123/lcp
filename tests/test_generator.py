"""Tests for the generator module."""

import json
import os
import sys

import tests.repro_fixture as reprofix
from lcp.generator import (
    _build_detailed_index_entry,
    _build_symbol_id,
    _convert_param,
    _convert_signature,
    _convert_symbol,
    _param_kind_to_lcp,
    _relativize_source_path,
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
    _ExprDefault,
    scan_module,
    scan_package,
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
        # #72: no site-packages/dist-packages/pythonX.Y marker in this path,
        # so it falls back to the bare basename rather than leaking the
        # absolute machine-specific path.
        assert entry.implementation.path == "file.py"
        assert entry.implementation.lines == [10, 20]


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


DOCSTRING = '''Do a thing.

Longer prose here.

Args:
    x (int): The x value.
    missing: Documented but not introspected.

Returns:
    str: The rendered result.

Raises:
    ValueError: If x is negative.

Examples:
    >>> do_thing(1)
    'ok'
'''


def _scanned_documented_function():
    return ScannedSymbol(
        name="do_thing",
        qualified_name="do_thing",
        module_path="pkg.mod",
        kind="function",
        summary="Do a thing.",
        description="Longer prose here.\n\nArgs:\n    x (int): The x value.",
        docstring=DOCSTRING,
        signature=ScannedSignature(
            params=[ScannedParam(name="x", type_hint="int")],
            return_type="str",
        ),
    )


class TestStructuredDocstrings:
    """Generator merges docstring extras into the LCP models (spec D11)."""

    def test_param_description_merged_by_name(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        params = symbol.signatures[0].params
        assert params[0].name == "x"
        assert params[0].description == "The x value."

    def test_unmatched_docstring_entry_never_invents_a_param(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        names = [p.name for p in symbol.signatures[0].params]
        assert names == ["x"]  # "missing" documented but not introspected

    def test_raises_and_returns_description(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        sig = symbol.signatures[0]
        assert sig.raises[0].type == "ValueError"
        assert sig.raises[0].condition == "If x is negative."
        assert sig.returns_description == "The rendered result."

    def test_examples_populated(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        examples = symbol.semantics.examples
        assert len(examples) == 1
        assert ">>> do_thing(1)" in examples[0].code

    def test_summary_and_description_unchanged(self):
        scanned = _scanned_documented_function()
        _, symbol = _convert_symbol(scanned)
        # description keeps the scanner's full post-summary remainder —
        # information the parser drops (mid-doc Note sections) must survive.
        assert symbol.semantics.summary == scanned.summary
        assert symbol.semantics.description == scanned.description

    def test_introspection_wins_on_type(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        # docstring says "x (int)" but the introspected type is the source
        # of truth; docstring only contributes the description text
        assert symbol.signatures[0].params[0].type == "int"

    def test_no_docstring_falls_back_to_today(self):
        scanned = _scanned_documented_function()
        scanned.docstring = None
        _, symbol = _convert_symbol(scanned)
        sig = symbol.signatures[0]
        assert sig.raises is None
        assert sig.returns_description is None
        assert symbol.semantics.examples is None
        assert sig.params[0].description is None

    def test_fail_open_on_parser_exception(self, monkeypatch):
        import lcp.docstrings as docstrings_mod

        def boom(text):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(docstrings_mod, "_parse", boom)
        scanned = _scanned_documented_function()
        _, symbol = _convert_symbol(scanned)
        assert symbol.semantics.summary == scanned.summary
        assert symbol.semantics.description == scanned.description
        assert symbol.signatures[0].raises is None


class TestConvertParamExprDefault:
    """#72: expr defaults are emitted verbatim, not as '...'."""

    def test_expr_default_emitted_verbatim(self):
        scanned = ScannedParam(
            name="exe", type_hint="str", default=_ExprDefault("sys.executable")
        )
        param = _convert_param(scanned)
        assert param.required is False
        assert param.default == "sys.executable"


class TestRelativizeSourcePath:
    """#72: detailed_index paths are package-relative, never absolute."""

    def test_site_packages_tail(self):
        p = "/tmp/x/venv/lib/python3.12/site-packages/requests/sessions.py"
        assert _relativize_source_path(p) == "requests/sessions.py"

    def test_stdlib_tail(self):
        p = "/home/u/.pyenv/versions/3.12.0/lib/python3.12/contextlib.py"
        assert _relativize_source_path(p) == "contextlib.py"

    def test_nested_stdlib_tail(self):
        p = "/home/u/.pyenv/versions/3.12.0/lib/python3.12/importlib/metadata.py"
        assert _relativize_source_path(p) == "importlib/metadata.py"

    def test_unknown_layout_falls_back_to_basename(self):
        assert _relativize_source_path("/home/u/proj/src/lcp/scanner.py") == "scanner.py"

    def test_build_entry_relativizes(self):
        scanned = ScannedSymbol(
            name="Session",
            qualified_name="Session",
            module_path="requests",
            kind="class",
            source_file="/tmp/venv/lib/python3.12/site-packages/requests/sessions.py",
            source_lines=(1, 10),
        )
        entry = _build_detailed_index_entry(scanned)
        assert entry.implementation.path == "requests/sessions.py"


class TestReproducibilityInvariant:
    """#72: no generated manifest string may embed an environment root."""

    def _manifest_json(self):
        symbols = scan_module(reprofix)
        scanned = ScannedModule(
            name="repro_fixture", version="0.0.0", symbols=symbols
        )
        doc = generate_lcp(scanned)
        return doc.model_dump_json()

    def test_no_env_roots_in_manifest(self):
        blob = self._manifest_json()
        for root in (sys.prefix, sys.base_prefix, os.path.expanduser("~")):
            assert root not in blob, f"environment root leaked: {root}"
        assert sys.executable not in blob

    def test_two_scans_are_identical(self):
        # generation.date is a live wall-clock timestamp (datetime.now(UTC) in
        # generator.py), not an environment root — exclude it so this checks
        # content determinism, the invariant this test targets.
        first = json.loads(self._manifest_json())
        second = json.loads(self._manifest_json())
        del first["manifest"]["generation"]["date"]
        del second["manifest"]["generation"]["date"]
        assert first == second

    def test_frozenset_constant_is_sorted(self):
        symbols = scan_module(reprofix)
        schemes = next(s for s in symbols if s.name == "SCHEMES")
        assert schemes.summary == "frozenset constant: frozenset({'ftp', 'http', 'https'})"

    def test_computed_string_defaults_are_symbolic(self):
        # The resolved timestamp / resolved os.linesep must not be emitted;
        # the source expressions must be.
        d = json.loads(self._manifest_json())
        make_tmp = d["symbols"]["tests.repro_fixture:make_tmp"]
        params = {p["name"]: p.get("default") for p in make_tmp["signatures"][0]["params"]}
        assert params["stamp"] == 'datetime.now().strftime("%Y%m%d")'
        assert params["sep"] == "os.linesep"
        assert params["label"] == "run"
