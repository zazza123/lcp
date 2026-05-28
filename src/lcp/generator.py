"""Generator module for converting scanned data to LCP format."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import (
    Artifact,
    DetailedIndexEntry,
    Distribution,
    Generation,
    LCPDocument,
    Library,
    Manifest,
    Param,
    ParamKind,
    Semantics,
    Signature,
    Symbol,
    SymbolKind,
)
from .scanner import ScannedModule, ScannedParam, ScannedSignature, ScannedSymbol


def _param_kind_to_lcp(kind: str) -> ParamKind | None:
    """Convert scanner param kind to LCP ParamKind."""
    kind_map = {
        "positional": ParamKind.POSITIONAL,
        "keyword": ParamKind.KEYWORD,
        "positional_only": ParamKind.POSITIONAL_ONLY,
        "keyword_only": ParamKind.KEYWORD_ONLY,
        "rest": ParamKind.REST,
    }
    return kind_map.get(kind)


def _symbol_kind_to_lcp(kind: str) -> SymbolKind:
    """Convert scanner symbol kind to LCP SymbolKind."""
    kind_map = {
        "function": SymbolKind.FUNCTION,
        "class": SymbolKind.CLASS,
        "method": SymbolKind.METHOD,
        "attribute": SymbolKind.ATTRIBUTE,
        "module": SymbolKind.MODULE,
        "constant": SymbolKind.CONSTANT,
    }
    return kind_map.get(kind, SymbolKind.FUNCTION)


def _build_symbol_id(scanned: ScannedSymbol) -> str:
    """Build LCP symbol ID from scanned symbol.

    Format: <module_path>:<entity_path>
    - Module: "collections:"
    - Function: "json:loads"
    - Class: "pathlib:Path"
    - Method: "collections:Counter#update"
    """
    module_path = scanned.module_path
    entity_path = scanned.qualified_name

    return f"{module_path}:{entity_path}"


def _convert_param(param: ScannedParam) -> Param:
    """Convert a scanned parameter to LCP Param."""
    default_value: Any = None
    if param.has_default:
        # Try to represent the default value
        if param.default is None:
            default_value = None
        elif isinstance(param.default, (str, int, float, bool)):
            default_value = param.default
        else:
            # For complex defaults, just note that there is one
            default_value = "..."

    return Param(
        name=param.name,
        type=param.type_hint or "Any",
        required=not param.has_default,
        default=default_value if param.has_default else None,
        variadic=param.is_variadic,
        kind=_param_kind_to_lcp(param.kind),
        description=param.description,
    )


def _convert_signature(sig: ScannedSignature) -> Signature:
    """Convert a scanned signature to LCP Signature."""
    params = [_convert_param(p) for p in sig.params] if sig.params else None

    return Signature(
        async_=sig.is_async,
        params=params,
        returns=sig.return_type,
        raises=None,  # Could be extracted from docstrings in future
    )


def _convert_symbol(scanned: ScannedSymbol) -> tuple[str, Symbol]:
    """Convert a scanned symbol to LCP Symbol with its ID."""
    symbol_id = _build_symbol_id(scanned)

    # Build semantics
    semantics = Semantics(
        summary=scanned.summary or f"{scanned.kind.capitalize()} {scanned.name}",
        description=scanned.description,
        examples=None,
    )

    # Build signatures for callables
    signatures = None
    if scanned.signature and scanned.kind in ("function", "method", "class"):
        signatures = [_convert_signature(scanned.signature)]

    symbol = Symbol(
        kind=_symbol_kind_to_lcp(scanned.kind),
        module=scanned.module_path,
        signatures=signatures,
        semantics=semantics,
        effects=None,
        stability=None,
        requires=None,
    )

    return symbol_id, symbol


def _build_detailed_index_entry(scanned: ScannedSymbol) -> DetailedIndexEntry | None:
    """Build detailed index entry for source location."""
    if not scanned.source_file:
        return None

    lines = list(scanned.source_lines) if scanned.source_lines else None

    return DetailedIndexEntry(
        implementation=Artifact(
            path=scanned.source_file,
            lines=lines,
            availability="full",
        )
    )


def generate_lcp(scanned_module: ScannedModule) -> LCPDocument:
    """Generate an LCP document from scanned module data."""
    # Build manifest
    manifest = Manifest(
        schema_version="1.0",
        library=Library(
            name=scanned_module.name,
            version=scanned_module.version,
            language="python",
        ),
        distribution=Distribution.PYPI,
        generation=Generation(
            tool="lcp",
            version="0.1.0",
            date=datetime.now(timezone.utc),
        ),
        symbol_resolution="fully-qualified",
    )

    # Convert all symbols
    symbols: dict[str, Symbol] = {}
    detailed_index: dict[str, DetailedIndexEntry] = {}

    for scanned in scanned_module.symbols:
        symbol_id, symbol = _convert_symbol(scanned)
        symbols[symbol_id] = symbol

        # Add detailed index if source info available
        index_entry = _build_detailed_index_entry(scanned)
        if index_entry:
            detailed_index[symbol_id] = index_entry

        # Process class members
        for member in scanned.members:
            member_id, member_symbol = _convert_symbol(member)
            symbols[member_id] = member_symbol

    return LCPDocument(
        manifest=manifest,
        symbols=symbols,
        deprecations=None,
        detailed_index=detailed_index if detailed_index else None,
    )
