from dataclasses import dataclass, field

from harness.verify import resolve_dotted, resolve_symbol, symbol_used, verify_code
from harness.extract import CodeUsage


@dataclass
class StubCase:
    import_name: str = "json"
    required_symbols: list = field(default_factory=list)
    forbidden_symbols: list = field(default_factory=list)


class TestResolveDotted:
    def test_module_level_function(self):
        assert resolve_dotted("json.loads") is True

    def test_class_method_chain(self):
        assert resolve_dotted("pathlib.Path.resolve") is True

    def test_bare_module(self):
        assert resolve_dotted("json") is True

    def test_submodule(self):
        assert resolve_dotted("os.path.join") is True

    def test_nonexistent_attribute(self):
        assert resolve_dotted("json.load_string") is False

    def test_nonexistent_module(self):
        assert resolve_dotted("no_such_module_xyz.thing") is False


class TestResolveSymbol:
    def test_module_function(self):
        assert resolve_symbol("json:loads") is True

    def test_class_method(self):
        assert resolve_symbol("pathlib:Path#resolve") is True

    def test_missing_method(self):
        assert resolve_symbol("pathlib:Path#resolvee") is False

    def test_missing_entity(self):
        assert resolve_symbol("json:Decoder") is False

    def test_missing_module(self):
        assert resolve_symbol("no_such_module_xyz:Thing") is False

    def test_symbol_raising_on_getattr_is_unresolved(self):
        # pydantic.BaseSettings raises PydanticImportError on access
        assert resolve_symbol("pydantic:BaseSettings") is False


class TestSymbolUsed:
    def test_module_symbol_matches_dotted_path(self):
        usage = CodeUsage(dotted_paths={"json.loads"})
        assert symbol_used("json:loads", usage) is True

    def test_module_symbol_absent(self):
        assert symbol_used("json:loads", CodeUsage()) is False

    def test_method_symbol_matches_method_name(self):
        usage = CodeUsage(method_names={"resolve"})
        assert symbol_used("pathlib:Path#resolve", usage) is True

    def test_method_symbol_matches_full_path(self):
        usage = CodeUsage(dotted_paths={"pathlib.Path.resolve"})
        assert symbol_used("pathlib:Path#resolve", usage) is True

    def test_class_symbol_matches_from_import(self):
        usage = CodeUsage(dotted_paths={"pathlib.Path"})
        assert symbol_used("pathlib:Path", usage) is True


class TestVerifyCode:
    def test_correct_code_passes(self):
        case = StubCase(required_symbols=["json:loads"],
                        forbidden_symbols=["json:parse"])
        v = verify_code("import json\njson.loads('{}')", case)
        assert v.passed is True
        assert v.misuse_count == 0

    def test_forbidden_symbol_counts_as_misuse(self):
        case = StubCase(forbidden_symbols=["json:parse"])
        v = verify_code("import json\njson.parse('{}')", case)
        assert v.passed is False
        assert v.forbidden_used == ["json:parse"]
        # json.parse is also an unresolved usage -> misuse >= 2 is fine;
        # what matters is it is counted at least once.
        assert v.misuse_count >= 1

    def test_hallucinated_attribute_is_unresolved(self):
        v = verify_code("import json\njson.load_string('{}')", StubCase())
        assert v.passed is False
        assert "json.load_string" in v.unresolved_usages
        assert v.misuse_count == 1

    def test_missing_required_fails_without_misuse(self):
        case = StubCase(required_symbols=["json:dumps"])
        v = verify_code("import json\njson.loads('{}')", case)
        assert v.passed is False
        assert v.required_missing == ["json:dumps"]
        assert v.misuse_count == 0

    def test_no_code_is_error(self):
        v = verify_code(None, StubCase(required_symbols=["json:loads"]))
        assert v.passed is False
        assert v.error == "no code block"

    def test_syntax_error_is_error(self):
        v = verify_code("def broken(:", StubCase())
        assert v.passed is False
        assert v.error is not None and "syntax" in v.error
