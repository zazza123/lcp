"""Tests for the scanner module."""

import inspect

import pytest

from lcp.scanner import (
    ScannedModule,
    ScannedParam,
    _get_param_kind,
    _is_constant,
    _is_member_from_package,
    _is_public,
    _parse_docstring,
    _scan_class,
    _scan_function,
    _scan_signature,
    _type_to_string,
    scan_module,
    scan_package,
)


class TestParseDocstring:
    """Tests for _parse_docstring function."""

    def test_none_docstring(self):
        summary, desc = _parse_docstring(None)
        assert summary is None
        assert desc is None

    def test_empty_docstring(self):
        summary, desc = _parse_docstring("")
        assert summary is None
        assert desc is None

    def test_single_line_docstring(self):
        summary, desc = _parse_docstring("A simple summary.")
        assert summary == "A simple summary."
        assert desc is None

    def test_multi_line_docstring(self):
        docstring = """A brief summary.

        This is a longer description that spans
        multiple lines.
        """
        summary, desc = _parse_docstring(docstring)
        assert summary == "A brief summary."
        assert desc is not None
        assert "longer description" in desc

    def test_multi_paragraph_summary(self):
        docstring = """First line of summary
        continued on second line.

        Description here.
        """
        summary, desc = _parse_docstring(docstring)
        assert "First line" in summary
        assert "continued" in summary


class TestTypeToString:
    """Tests for _type_to_string function."""

    def test_none_type(self):
        assert _type_to_string(None) is None

    def test_string_type(self):
        assert _type_to_string("str") == "str"

    def test_builtin_type(self):
        assert _type_to_string(int) == "int"
        assert _type_to_string(str) == "str"
        assert _type_to_string(list) == "list"

    def test_none_type_literal(self):
        assert _type_to_string(type(None)) == "None"

    def test_list_generic(self):
        from typing import List
        result = _type_to_string(List[int])
        assert "int" in result

    def test_optional_type(self):
        from typing import Optional
        result = _type_to_string(Optional[str])
        assert "Optional" in result or "str" in result

    def test_union_type(self):
        from typing import Union
        result = _type_to_string(Union[str, int])
        assert "str" in result or "Union" in result


class TestIsPublic:
    """Tests for _is_public function."""

    def test_public_name(self):
        assert _is_public("my_function") is True
        assert _is_public("MyClass") is True
        assert _is_public("CONSTANT") is True

    def test_private_name(self):
        assert _is_public("_private") is False
        assert _is_public("__very_private") is False

    def test_dunder_methods(self):
        assert _is_public("__init__") is True
        assert _is_public("__call__") is True
        assert _is_public("__iter__") is True
        assert _is_public("__str__") is True

    def test_include_private(self):
        assert _is_public("_private", include_private=True) is True
        assert _is_public("__private", include_private=True) is True


class TestIsConstant:
    """Tests for _is_constant function."""

    def test_uppercase_primitives(self):
        assert _is_constant("MAX_SIZE", 100) is True
        assert _is_constant("DEFAULT_NAME", "test") is True
        assert _is_constant("PI", 3.14) is True
        assert _is_constant("ENABLED", True) is True

    def test_lowercase_not_constant(self):
        assert _is_constant("max_size", 100) is False
        assert _is_constant("MaxSize", 100) is False

    def test_complex_values_not_constant(self):
        assert _is_constant("MY_LIST", [1, 2, 3]) is False
        assert _is_constant("MY_DICT", {"a": 1}) is False


class TestGetParamKind:
    """Tests for _get_param_kind function."""

    def test_positional_or_keyword(self):
        param = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        assert _get_param_kind(param) == "positional"

    def test_positional_only(self):
        param = inspect.Parameter("x", inspect.Parameter.POSITIONAL_ONLY)
        assert _get_param_kind(param) == "positional_only"

    def test_keyword_only(self):
        param = inspect.Parameter("x", inspect.Parameter.KEYWORD_ONLY)
        assert _get_param_kind(param) == "keyword_only"

    def test_var_positional(self):
        param = inspect.Parameter("args", inspect.Parameter.VAR_POSITIONAL)
        assert _get_param_kind(param) == "rest"


class TestScannedParam:
    """Tests for ScannedParam dataclass."""

    def test_has_default(self):
        param = ScannedParam(name="x", default=10)
        assert param.has_default is True

        param_no_default = ScannedParam(name="y")
        assert param_no_default.has_default is False

    def test_is_variadic(self):
        param = ScannedParam(name="args", kind="rest")
        assert param.is_variadic is True

        param_normal = ScannedParam(name="x", kind="positional")
        assert param_normal.is_variadic is False


class TestScanSignature:
    """Tests for _scan_signature function."""

    def test_simple_function(self):
        def func(x: int, y: str) -> bool:
            pass

        sig = _scan_signature(func)
        assert sig is not None
        assert len(sig.params) == 2
        assert sig.params[0].name == "x"
        assert sig.params[0].type_hint == "int"
        assert sig.return_type == "bool"

    def test_function_with_defaults(self):
        def func(x: int, y: int = 10) -> int:
            pass

        sig = _scan_signature(func)
        assert sig.params[1].has_default is True
        assert sig.params[1].default == 10

    def test_async_function(self):
        async def async_func() -> None:
            pass

        sig = _scan_signature(async_func)
        assert sig.is_async is True

    def test_function_without_annotations(self):
        def func(x, y):
            pass

        sig = _scan_signature(func)
        assert len(sig.params) == 2
        assert sig.params[0].type_hint is None


class TestScanFunction:
    """Tests for _scan_function function."""

    def test_scan_function(self, sample_module):
        symbol = _scan_function(
            sample_module.simple_function,
            "tests.sample_module",
        )
        assert symbol.name == "simple_function"
        assert symbol.kind == "function"
        assert symbol.summary is not None
        assert "Add two numbers" in symbol.summary
        assert symbol.signature is not None

    def test_scan_async_function(self, sample_module):
        symbol = _scan_function(
            sample_module.async_function,
            "tests.sample_module",
        )
        assert symbol.signature.is_async is True


class TestScanClass:
    """Tests for _scan_class function."""

    def test_scan_class(self, sample_module):
        symbol = _scan_class(
            sample_module.SimpleClass,
            "tests.sample_module",
        )
        assert symbol.name == "SimpleClass"
        assert symbol.kind == "class"
        assert symbol.summary is not None
        assert len(symbol.members) > 0

    def test_class_members(self, sample_module):
        symbol = _scan_class(
            sample_module.SimpleClass,
            "tests.sample_module",
        )
        member_names = [m.name for m in symbol.members]
        assert "__init__" in member_names
        assert "instance_method" in member_names
        assert "doubled" in member_names  # property
        assert "from_string" in member_names  # classmethod
        assert "static_helper" in member_names  # staticmethod

    def test_private_members_excluded(self, sample_module):
        symbol = _scan_class(
            sample_module.SimpleClass,
            "tests.sample_module",
            include_private=False,
        )
        member_names = [m.name for m in symbol.members]
        assert "_private_method" not in member_names

    def test_private_members_included(self, sample_module):
        symbol = _scan_class(
            sample_module.SimpleClass,
            "tests.sample_module",
            include_private=True,
        )
        member_names = [m.name for m in symbol.members]
        assert "_private_method" in member_names


class TestScanModule:
    """Tests for scan_module function."""

    def test_scan_module(self, sample_module):
        symbols = scan_module(sample_module)

        # Should include module itself
        module_symbols = [s for s in symbols if s.kind == "module"]
        assert len(module_symbols) == 1

        # Should include functions
        func_names = [s.name for s in symbols if s.kind == "function"]
        assert "simple_function" in func_names
        assert "function_with_defaults" in func_names
        assert "async_function" in func_names

        # Should include classes
        class_names = [s.name for s in symbols if s.kind == "class"]
        assert "SimpleClass" in class_names
        assert "ChildClass" in class_names

        # Should include constants
        const_names = [s.name for s in symbols if s.kind == "constant"]
        assert "MODULE_VERSION" in const_names
        assert "MAX_ITEMS" in const_names

    def test_scan_module_excludes_private(self, sample_module):
        symbols = scan_module(sample_module, include_private=False)
        func_names = [s.name for s in symbols if s.kind == "function"]
        assert "_private_function" not in func_names

    def test_scan_module_includes_private(self, sample_module):
        symbols = scan_module(sample_module, include_private=True)
        func_names = [s.name for s in symbols if s.kind == "function"]
        assert "_private_function" in func_names


class TestScanPackage:
    """Tests for scan_package function."""

    def test_scan_builtin_package(self):
        """Test scanning a built-in package."""
        result = scan_package("json", recursive=False)
        assert isinstance(result, ScannedModule)
        assert result.name == "json"
        assert len(result.symbols) > 0

        # Check for known json functions
        symbol_names = [s.name for s in result.symbols]
        assert "loads" in symbol_names or any("loads" in n for n in symbol_names)

    def test_scan_package_version(self):
        """Test that package version is extracted."""
        result = scan_package("json", recursive=False)
        # json is a built-in, so version might be "0.0.0"
        assert result.version is not None

    def test_scan_nonexistent_package(self):
        """Test scanning a non-existent package raises ImportError."""
        with pytest.raises(ImportError):
            scan_package("this_package_does_not_exist_12345")

    def test_scan_package_recursive(self):
        """Test recursive scanning of a package."""
        result = scan_package("json", recursive=True)
        assert len(result.symbols) > 0

    def test_scan_package_includes_namespace_submodules(self, tmp_path, monkeypatch):
        """Test recursive scanning includes namespace package submodules."""
        package_name = "scan_namespace_pkg"
        package_dir = tmp_path / package_name
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text('"""Root package."""\n')

        namespace_dir = package_dir / "templates"
        namespace_dir.mkdir()
        (namespace_dir / "adk.py").write_text(
            '"""Template module."""\n\n'
            "def important_template_function():\n"
            '    """Important function."""\n'
            '    return "ok"\n'
        )

        monkeypatch.syspath_prepend(str(tmp_path))
        result = scan_package(package_name, recursive=True)

        module_paths = {s.module_path for s in result.symbols if s.kind == "module"}
        assert f"{package_name}.templates" in module_paths
        assert f"{package_name}.templates.adk" in module_paths

        function_symbols = {
            (s.module_path, s.name) for s in result.symbols if s.kind == "function"
        }
        assert (
            f"{package_name}.templates.adk",
            "important_template_function",
        ) in function_symbols

    def test_scan_package_skips_baseexception_submodule(self, tmp_path, monkeypatch):
        """A submodule raising a BaseException subclass at import is skipped.

        Regression for #51: test subpackages call ``pytest.importorskip`` which
        raises ``Skipped`` (a ``BaseException``, not an ``Exception``). The scan
        must survive it and keep the importable symbols.
        """
        package_name = "scan_basexc_pkg"
        package_dir = tmp_path / package_name
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text('"""Root package."""\n')
        (package_dir / "good.py").write_text(
            '"""Good module."""\n\n'
            "def keep_me():\n"
            '    """Kept."""\n'
            '    return "ok"\n'
        )
        # Mimics pytest.importorskip: raises a BaseException subclass on import.
        (package_dir / "hostile.py").write_text(
            '"""Hostile module."""\n\n'
            "class _Skipped(BaseException):\n"
            "    pass\n\n"
            'raise _Skipped("could not import optional dep")\n'
        )

        monkeypatch.syspath_prepend(str(tmp_path))
        result = scan_package(package_name, recursive=True)

        function_symbols = {
            (s.module_path, s.name) for s in result.symbols if s.kind == "function"
        }
        assert (f"{package_name}.good", "keep_me") in function_symbols
        module_paths = {s.module_path for s in result.symbols if s.kind == "module"}
        assert f"{package_name}.hostile" not in module_paths

    def test_scan_package_excludes_tests_subpackage_by_default(
        self, tmp_path, monkeypatch
    ):
        """``*.tests`` subpackages are excluded by default; ``testing`` stays.

        Regression for #51 part 2: plain ``tests`` pollutes manifests, but
        ``numpy.testing``-style packages are public API and must be kept.
        """
        package_name = "scan_tests_pkg"
        package_dir = tmp_path / package_name
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text('"""Root package."""\n')

        tests_dir = package_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text(
            '"""Test subpackage."""\n\n'
            "def test_pollution():\n"
            '    """Should not be scanned."""\n'
            '    return None\n'
        )

        testing_dir = package_dir / "testing"
        testing_dir.mkdir()
        (testing_dir / "__init__.py").write_text(
            '"""Public testing utilities."""\n\n'
            "def assert_something():\n"
            '    """Public API."""\n'
            '    return None\n'
        )

        monkeypatch.syspath_prepend(str(tmp_path))
        result = scan_package(package_name, recursive=True)

        module_paths = {s.module_path for s in result.symbols if s.kind == "module"}
        assert f"{package_name}.tests" not in module_paths
        assert f"{package_name}.testing" in module_paths

        function_symbols = {
            (s.module_path, s.name) for s in result.symbols if s.kind == "function"
        }
        assert (f"{package_name}.tests", "test_pollution") not in function_symbols
        assert (f"{package_name}.testing", "assert_something") in function_symbols

    def test_scan_package_includes_tests_when_opted_in(self, tmp_path, monkeypatch):
        """``include_tests=True`` restores scanning of ``*.tests`` subpackages."""
        package_name = "scan_tests_optin_pkg"
        package_dir = tmp_path / package_name
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text('"""Root package."""\n')

        tests_dir = package_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text(
            '"""Test subpackage."""\n\n'
            "def test_included():\n"
            '    """Now scanned."""\n'
            '    return None\n'
        )

        monkeypatch.syspath_prepend(str(tmp_path))
        result = scan_package(package_name, recursive=True, include_tests=True)

        module_paths = {s.module_path for s in result.symbols if s.kind == "module"}
        assert f"{package_name}.tests" in module_paths


class TestInheritedMemberFiltering:
    """Tests for filtering inherited members from external packages."""

    def test_child_class_keeps_same_package_members(self, sample_module):
        """ChildClass inherits from SimpleClass (same package) -- inherited members kept."""
        symbol = _scan_class(
            sample_module.ChildClass,
            "sample_module",
            package_root="sample_module",
        )
        member_names = [m.name for m in symbol.members]
        assert "child_method" in member_names
        assert "instance_method" in member_names
        assert "__init__" in member_names

    def test_dict_subclass_excludes_external_methods(self, sample_module):
        """DictSubclass inherits from dict (builtins) -- dict methods excluded."""
        symbol = _scan_class(
            sample_module.DictSubclass,
            "sample_module",
            package_root="sample_module",
        )
        member_names = [m.name for m in symbol.members]
        assert "custom_method" in member_names
        assert "get" not in member_names
        assert "keys" not in member_names
        assert "values" not in member_names
        assert "items" not in member_names
        assert "pop" not in member_names

    def test_scan_module_filters_external_inherited(self, sample_module):
        """scan_module infers package_root and filters external inherited members."""
        symbols = scan_module(sample_module)
        dict_subclass = [s for s in symbols if s.name == "DictSubclass"]
        assert len(dict_subclass) == 1
        member_names = [m.name for m in dict_subclass[0].members]
        assert "custom_method" in member_names
        assert "get" not in member_names

    def test_is_member_from_package_direct_definition(self):
        """Members in cls.__dict__ always belong to the package."""

        class MyDict(dict):
            def my_method(self):
                pass

        assert _is_member_from_package(MyDict, "my_method", "some_package") is True

    def test_is_member_from_package_external_base(self):
        """Members from an external base class are excluded."""

        class MyDict(dict):
            pass

        assert _is_member_from_package(MyDict, "get", "mypackage") is False
        assert _is_member_from_package(MyDict, "keys", "mypackage") is False


class TestReexportAliases:
    """Intra-package re-exports become aliases on the canonical symbol."""

    @pytest.fixture(scope="class")
    def scanned(self):
        return scan_package("sample_package")

    def _by_id(self, scanned):
        return {
            (s.module_path, s.qualified_name): s for s in scanned.symbols
        }

    def test_root_reexport_recorded_as_alias(self, scanned):
        symbols = self._by_id(scanned)
        core_class = symbols[("sample_package.core", "CoreClass")]
        assert ("sample_package", "CoreClass") in core_class.aliases

    def test_definition_site_remains_canonical(self, scanned):
        symbols = self._by_id(scanned)
        # No symbol is scanned AT the re-export site
        assert ("sample_package", "CoreClass") not in symbols
        assert ("sample_package", "core_function") not in symbols

    def test_renamed_reexport_uses_alias_name(self, scanned):
        symbols = self._by_id(scanned)
        helper = symbols[("sample_package.extras", "helper")]
        assert ("sample_package", "aliased_helper") in helper.aliases

    def test_star_reexport_without_all_recorded(self, scanned):
        symbols = self._by_id(scanned)
        core_class = symbols[("sample_package.core", "CoreClass")]
        core_function = symbols[("sample_package.core", "core_function")]
        assert ("sample_package.convenience", "CoreClass") in core_class.aliases
        assert (
            "sample_package.convenience",
            "core_function",
        ) in core_function.aliases

    def test_all_filter_limits_aliases(self, scanned):
        symbols = self._by_id(scanned)
        core_class = symbols[("sample_package.core", "CoreClass")]
        core_function = symbols[("sample_package.core", "core_function")]
        assert ("sample_package.allexport", "CoreClass") in core_class.aliases
        # core_function is imported by allexport but excluded from __all__
        assert (
            "sample_package.allexport",
            "core_function",
        ) not in core_function.aliases

    def test_external_reexports_still_skipped(self, scanned):
        symbols = self._by_id(scanned)
        # json.loads is re-exported at the root but is NOT part of the package
        assert ("sample_package", "loads") not in symbols
        for symbol in scanned.symbols:
            for alias_module, alias_name in symbol.aliases:
                assert alias_name != "loads"

    def test_name_collision_keeps_aliases_separate(self, scanned):
        symbols = self._by_id(scanned)
        common_a = symbols[("sample_package.mod_a", "common")]
        common_b = symbols[("sample_package.mod_b", "common")]
        assert ("sample_package.re_a", "common") in common_a.aliases
        assert ("sample_package.re_b", "common") not in common_a.aliases
        assert ("sample_package.re_b", "common") in common_b.aliases
        assert ("sample_package.re_a", "common") not in common_b.aliases

    def test_symbols_without_reexports_have_no_aliases(self, sample_module):
        symbols = scan_module(sample_module)
        assert all(s.aliases == [] for s in symbols)


class TestDocstringCapture:
    """The scanner carries the raw docstring for generator-level parsing."""

    def test_scan_function_captures_raw_docstring(self):
        def documented(x):
            """Sum.

            Args:
                x: The value.
            """

        symbol = _scan_function(documented, "pkg.mod")
        assert symbol.docstring == documented.__doc__

    def test_scan_class_captures_raw_docstring_and_members(self):
        class Widget:
            """A widget.

            Args:
                size: The size.
            """

            def render(self, fmt):
                """Render.

                Args:
                    fmt: Format string.
                """

        symbol = _scan_class(Widget, "pkg.mod")
        assert symbol.docstring == Widget.__doc__
        render = next(m for m in symbol.members if m.name == "render")
        assert render.docstring == Widget.render.__doc__

    def test_non_string_doc_captured_as_none(self):
        class WeirdDoc:
            pass

        # sympy-style: __doc__ exposed as a descriptor on the class
        WeirdDoc.__doc__ = property(lambda self: "computed")
        symbol = _scan_class(WeirdDoc, "pkg.mod")
        assert symbol.docstring is None
        assert symbol.summary is None

    def test_module_docstring_captured(self, sample_module):
        symbols = scan_module(sample_module)
        module_symbol = next(s for s in symbols if s.kind == "module")
        assert module_symbol.docstring == sample_module.__doc__


class TestScannedSerialization:
    """Round-trip Scanned* dataclasses through a plain JSON dict (#52)."""

    def test_round_trip_preserves_default_states_and_tuples(self):
        import inspect
        import json

        from lcp.scanner import (
            ScannedModule,
            ScannedParam,
            ScannedSignature,
            ScannedSymbol,
            scanned_from_dict,
            scanned_to_dict,
        )

        module = ScannedModule(
            name="pkg",
            version="1.2.3",
            symbols=[
                ScannedSymbol(
                    name="f",
                    qualified_name="f",
                    module_path="pkg",
                    kind="function",
                    summary="s",
                    signature=ScannedSignature(
                        params=[
                            ScannedParam(name="a"),  # empty (no default)
                            ScannedParam(name="b", default=None),  # primitive None
                            ScannedParam(name="c", default=5),  # primitive
                            ScannedParam(name="d", default=object()),  # complex
                        ],
                        return_type="int",
                        is_async=True,
                        raises=["ValueError"],
                    ),
                    source_lines=(3, 9),
                    aliases=[("pkg", "g")],
                    members=[
                        ScannedSymbol(
                            name="m",
                            qualified_name="C.m",
                            module_path="pkg",
                            kind="method",
                        )
                    ],
                )
            ],
        )

        rebuilt = scanned_from_dict(json.loads(json.dumps(scanned_to_dict(module))))
        params = rebuilt.symbols[0].signature.params
        assert params[0].default is inspect.Parameter.empty
        assert params[0].has_default is False
        assert params[1].default is None
        assert params[1].has_default is True
        assert params[2].default == 5
        assert params[3].has_default is True
        assert not isinstance(params[3].default, (str, int, float, bool))
        assert rebuilt.symbols[0].source_lines == (3, 9)
        assert rebuilt.symbols[0].aliases == [("pkg", "g")]
        assert rebuilt.symbols[0].signature.is_async is True
        assert rebuilt.symbols[0].members[0].qualified_name == "C.m"

    def test_round_trip_matches_direct_generation(self):
        """A rebuilt module generates the identical LCP document (symbols)."""
        import json

        from lcp.generator import generate_lcp
        from lcp.scanner import scan_package, scanned_from_dict, scanned_to_dict

        scanned = scan_package("json", recursive=False)
        wire = json.loads(json.dumps(scanned_to_dict(scanned)))
        rebuilt = scanned_from_dict(wire)

        # Compare the symbol content; the manifest carries a generation
        # timestamp that differs between two generate_lcp() calls.
        direct = json.loads(generate_lcp(scanned).to_json())["symbols"]
        round_tripped = json.loads(generate_lcp(rebuilt).to_json())["symbols"]
        assert direct == round_tripped
