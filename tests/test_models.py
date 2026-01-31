"""Tests for the models module."""

import json
from datetime import datetime, timezone

import pytest

from lcp_python_sdk.models import (
    Artifact,
    DetailedIndexEntry,
    Distribution,
    EffectCategory,
    Effects,
    Example,
    Generation,
    LCPDocument,
    Library,
    Manifest,
    Param,
    ParamKind,
    RaisesEntry,
    Semantics,
    Signature,
    Stability,
    StabilityLevel,
    Symbol,
    SymbolKind,
    TypeRef,
)


class TestSymbolKind:
    """Tests for SymbolKind enum."""

    def test_all_kinds_exist(self):
        assert SymbolKind.FUNCTION == "function"
        assert SymbolKind.CLASS == "class"
        assert SymbolKind.METHOD == "method"
        assert SymbolKind.ATTRIBUTE == "attribute"
        assert SymbolKind.MODULE == "module"
        assert SymbolKind.CONSTANT == "constant"


class TestParamKind:
    """Tests for ParamKind enum."""

    def test_all_kinds_exist(self):
        assert ParamKind.POSITIONAL == "positional"
        assert ParamKind.KEYWORD == "keyword"
        assert ParamKind.POSITIONAL_ONLY == "positional_only"
        assert ParamKind.KEYWORD_ONLY == "keyword_only"
        assert ParamKind.REST == "rest"


class TestTypeRef:
    """Tests for TypeRef model."""

    def test_simple_type_ref(self):
        ref = TypeRef(kind="named", name="str")
        assert ref.kind == "named"
        assert ref.name == "str"

    def test_array_type_ref(self):
        ref = TypeRef(kind="array", items="int")
        assert ref.kind == "array"
        assert ref.items == "int"

    def test_map_type_ref(self):
        ref = TypeRef(kind="map", key="str", value="int")
        assert ref.kind == "map"
        assert ref.key == "str"
        assert ref.value == "int"

    def test_union_type_ref(self):
        ref = TypeRef(kind="union", args=["str", "int"])
        assert ref.kind == "union"
        assert ref.args == ["str", "int"]


class TestSemantics:
    """Tests for Semantics model."""

    def test_minimal_semantics(self):
        sem = Semantics(summary="A brief summary.")
        assert sem.summary == "A brief summary."
        assert sem.description is None
        assert sem.examples is None

    def test_full_semantics(self):
        sem = Semantics(
            summary="A brief summary.",
            description="A longer description.",
            examples=[Example(code="print('hello')", description="Say hello")],
        )
        assert sem.summary == "A brief summary."
        assert sem.description == "A longer description."
        assert len(sem.examples) == 1
        assert sem.examples[0].code == "print('hello')"


class TestParam:
    """Tests for Param model."""

    def test_required_param(self):
        param = Param(name="x", type="int")
        assert param.name == "x"
        assert param.type == "int"
        assert param.required is True
        assert param.default is None

    def test_optional_param(self):
        param = Param(name="x", type="int", required=False, default=10)
        assert param.required is False
        assert param.default == 10

    def test_variadic_param(self):
        param = Param(name="args", type="Any", variadic=True, kind=ParamKind.REST)
        assert param.variadic is True
        assert param.kind == ParamKind.REST


class TestSignature:
    """Tests for Signature model."""

    def test_simple_signature(self):
        sig = Signature(
            params=[Param(name="x", type="int")],
            returns="int",
        )
        assert len(sig.params) == 1
        assert sig.returns == "int"
        assert sig.async_ is False

    def test_async_signature(self):
        sig = Signature(async_=True, returns="dict")
        assert sig.async_ is True

    def test_signature_with_raises(self):
        sig = Signature(
            returns="int",
            raises=[RaisesEntry(type="ValueError", condition="if x < 0")],
        )
        assert len(sig.raises) == 1
        assert sig.raises[0].type == "ValueError"


class TestSymbol:
    """Tests for Symbol model."""

    def test_minimal_symbol(self):
        symbol = Symbol(
            kind=SymbolKind.FUNCTION,
            semantics=Semantics(summary="A function."),
        )
        assert symbol.kind == SymbolKind.FUNCTION
        assert symbol.semantics.summary == "A function."

    def test_full_symbol(self):
        symbol = Symbol(
            kind=SymbolKind.METHOD,
            module="mymodule",
            signatures=[
                Signature(params=[Param(name="self", type="Any")], returns="None")
            ],
            semantics=Semantics(summary="A method."),
            effects=Effects(categories=[EffectCategory.IO]),
            stability=Stability(level=StabilityLevel.STABLE, since="1.0.0"),
            requires=["other_module"],
        )
        assert symbol.module == "mymodule"
        assert len(symbol.signatures) == 1
        assert symbol.effects.categories == [EffectCategory.IO]
        assert symbol.stability.level == StabilityLevel.STABLE


class TestManifest:
    """Tests for Manifest model."""

    def test_minimal_manifest(self):
        manifest = Manifest(
            library=Library(name="mylib", version="1.0.0", language="python")
        )
        assert manifest.schema_version == "1.0"
        assert manifest.library.name == "mylib"
        assert manifest.symbol_resolution == "fully-qualified"

    def test_full_manifest(self):
        manifest = Manifest(
            library=Library(name="mylib", version="1.0.0", language="python"),
            distribution=Distribution.PYPI,
            license="MIT",
            generation=Generation(
                tool="lcp-python-sdk",
                version="0.1.0",
                date=datetime.now(timezone.utc),
            ),
        )
        assert manifest.distribution == Distribution.PYPI
        assert manifest.license == "MIT"
        assert manifest.generation.tool == "lcp-python-sdk"


class TestLCPDocument:
    """Tests for LCPDocument model."""

    def test_minimal_document(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="mylib", version="1.0.0", language="python")
            ),
            symbols={
                "mylib:func": Symbol(
                    kind=SymbolKind.FUNCTION,
                    semantics=Semantics(summary="A function."),
                )
            },
        )
        assert doc.manifest.library.name == "mylib"
        assert "mylib:func" in doc.symbols

    def test_to_dict(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="mylib", version="1.0.0", language="python")
            ),
            symbols={
                "mylib:func": Symbol(
                    kind=SymbolKind.FUNCTION,
                    semantics=Semantics(summary="A function."),
                )
            },
        )
        data = doc.to_dict()
        assert isinstance(data, dict)
        assert data["manifest"]["library"]["name"] == "mylib"
        assert "mylib:func" in data["symbols"]

    def test_to_json(self):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="mylib", version="1.0.0", language="python")
            ),
            symbols={},
        )
        json_str = doc.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["manifest"]["library"]["name"] == "mylib"

    def test_to_file(self, temp_dir):
        doc = LCPDocument(
            manifest=Manifest(
                library=Library(name="mylib", version="1.0.0", language="python")
            ),
            symbols={},
        )
        path = temp_dir / "output.lcp.json"
        doc.to_file(str(path))

        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert data["manifest"]["library"]["name"] == "mylib"


class TestDetailedIndex:
    """Tests for detailed index models."""

    def test_artifact(self):
        artifact = Artifact(path="src/main.py", lines=[10, 20], availability="full")
        assert artifact.path == "src/main.py"
        assert artifact.lines == [10, 20]

    def test_detailed_index_entry(self):
        entry = DetailedIndexEntry(
            implementation=Artifact(path="src/main.py", lines=[10, 20])
        )
        assert entry.implementation.path == "src/main.py"
