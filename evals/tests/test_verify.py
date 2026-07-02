from harness.verify import resolve_dotted, resolve_symbol


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
