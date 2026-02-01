"""Pydantic models for LCP (Library Context Protocol) structures."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SymbolKind(str, Enum):
    """Kind of symbol in the library."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    ATTRIBUTE = "attribute"
    MODULE = "module"
    CONSTANT = "constant"


class StabilityLevel(str, Enum):
    """Stability level of a symbol."""

    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class EffectCategory(str, Enum):
    """Categories of side effects."""

    IO = "io"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"


class ParamKind(str, Enum):
    """Kind of parameter."""

    POSITIONAL = "positional"
    KEYWORD = "keyword"
    POSITIONAL_ONLY = "positional_only"
    KEYWORD_ONLY = "keyword_only"
    REST = "rest"


class Platform(str, Enum):
    """Supported platforms."""

    LINUX = "linux"
    DARWIN = "darwin"
    WIN32 = "win32"
    OTHER = "other"


class Distribution(str, Enum):
    """Package distribution registry."""

    PYPI = "pypi"
    NPM = "npm"
    CARGO = "cargo"
    MAVEN = "maven"
    NUGET = "nuget"
    OTHER = "other"


class TypeRef(BaseModel):
    """Reference to a type."""

    kind: str | None = None
    name: str | None = None
    items: TypeRef | str | None = None
    key: TypeRef | str | None = None
    value: TypeRef | str | None = None
    elements: list[TypeRef | str] | None = None
    args: list[TypeRef | str] | None = None

    model_config = ConfigDict(extra="allow")


class Example(BaseModel):
    """Code example."""

    code: str
    description: str | None = None

    model_config = ConfigDict(extra="allow")


class Semantics(BaseModel):
    """Semantic description of a symbol."""

    summary: str
    description: str | None = None
    examples: list[Example] | None = None

    model_config = ConfigDict(extra="allow")


class Effects(BaseModel):
    """Side effects of a symbol."""

    categories: list[EffectCategory] | None = None
    idempotent: bool | None = None
    thread_safe: bool | None = None
    deterministic: bool | None = None

    model_config = ConfigDict(extra="allow")


class Stability(BaseModel):
    """Stability information for a symbol."""

    level: StabilityLevel | None = None
    since: str | None = None
    notes: str | None = None
    tracking_issue: str | None = None

    model_config = ConfigDict(extra="allow")


class Param(BaseModel):
    """Function/method parameter."""

    name: str
    type: TypeRef | str
    required: bool = True
    default: Any | None = None
    variadic: bool = False
    kind: ParamKind | None = None
    description: str | None = None

    model_config = ConfigDict(extra="allow")


class RaisesEntry(BaseModel):
    """Exception that can be raised."""

    type: str
    condition: str | None = None

    model_config = ConfigDict(extra="allow")


class Signature(BaseModel):
    """Function/method signature."""

    when: str | None = None
    async_: bool = Field(default=False, alias="async")
    params: list[Param] | None = None
    returns: TypeRef | str | None = None
    raises: list[RaisesEntry] | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Symbol(BaseModel):
    """A symbol in the library (function, class, method, etc.)."""

    kind: SymbolKind
    module: str | None = None
    signatures: list[Signature] | None = None
    semantics: Semantics
    effects: Effects | None = None
    stability: Stability | None = None
    requires: list[str] | None = None

    model_config = ConfigDict(extra="allow")


class Deprecation(BaseModel):
    """Deprecation information for a symbol."""

    deprecated_in: str
    replaced_by: str | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="allow")


class Artifact(BaseModel):
    """Source artifact reference."""

    path: str
    lines: list[int] | None = None
    availability: str | None = None

    model_config = ConfigDict(extra="allow")


class DetailedIndexEntry(BaseModel):
    """Detailed index entry linking symbol to source."""

    implementation: Artifact | None = None

    model_config = ConfigDict(extra="allow")


class Compatibility(BaseModel):
    """Runtime/platform compatibility."""

    python: str | None = None
    node: str | None = None
    platforms: list[Platform] | None = None

    model_config = ConfigDict(extra="allow")


class Changelog(BaseModel):
    """Changelog information."""

    url: str
    format: str | None = None

    model_config = ConfigDict(extra="allow")


class Generation(BaseModel):
    """Generation metadata."""

    tool: str | None = None
    version: str | None = None
    date: datetime | None = None

    model_config = ConfigDict(extra="allow")


class Library(BaseModel):
    """Library metadata."""

    name: str
    version: str
    language: str = "python"
    runtime_language: str | None = None
    bindings: str | None = None

    model_config = ConfigDict(extra="allow")


class Manifest(BaseModel):
    """LCP manifest section."""

    schema_version: str = "1.0"
    library: Library
    compatibility: Compatibility | None = None
    distribution: Distribution | None = None
    license: str | None = None
    changelog: Changelog | None = None
    generation: Generation | None = None
    symbol_resolution: str = "fully-qualified"

    model_config = ConfigDict(extra="allow")


class LCPDocument(BaseModel):
    """Complete LCP document."""

    manifest: Manifest
    symbols: dict[str, Symbol]
    deprecations: dict[str, Deprecation] | None = None
    detailed_index: dict[str, DetailedIndexEntry] | None = None

    model_config = ConfigDict(extra="allow")

    def to_dict(self) -> dict:
        """Convert to dictionary, suitable for JSON serialization."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent)

    def to_file(self, path: str, indent: int = 2) -> None:
        """Write LCP document to a file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=indent))
