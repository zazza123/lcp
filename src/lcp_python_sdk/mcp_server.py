"""MCP server that exposes LCP manifest data to AI agents."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .models import LCPDocument, Symbol, SymbolKind


class LCPIndex:
    """In-memory index of LCP document for fast lookups."""

    def __init__(self, doc: LCPDocument):
        self.doc = doc
        self.symbols_by_id: dict[str, Symbol] = doc.symbols
        self.symbols_by_module: dict[str, list[str]] = defaultdict(list)
        self.symbols_by_kind: dict[str, list[str]] = defaultdict(list)
        self.class_members: dict[str, list[str]] = defaultdict(list)
        self.modules: set[str] = set()

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build lookup indexes from the LCP document."""
        for symbol_id, symbol in self.symbols_by_id.items():
            # Index by module
            if symbol.module:
                self.symbols_by_module[symbol.module].append(symbol_id)
                self.modules.add(symbol.module)

            # Index by kind
            self.symbols_by_kind[symbol.kind.value].append(symbol_id)

            # Index class members (symbols with # in ID belong to a class)
            if "#" in symbol_id:
                class_id = symbol_id.split("#")[0]
                self.class_members[class_id].append(symbol_id)


def load_lcp_document(path: str | Path) -> LCPDocument:
    """Load and validate an LCP document from a file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"LCP file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return LCPDocument.model_validate(data)


def create_server(
    manifest_path: str | Path,
    name: str | None = None,
) -> FastMCP:
    """Create an MCP server for the given LCP manifest.

    Args:
        manifest_path: Path to the .lcp.json file
        name: Server name (default: lcp-{library-name})

    Returns:
        Configured FastMCP server instance
    """
    doc = load_lcp_document(manifest_path)
    index = LCPIndex(doc)

    if name is None:
        name = f"lcp-{doc.manifest.library.name}"

    mcp = FastMCP(name)

    def _symbol_summary(symbol_id: str, symbol: Symbol) -> dict[str, Any]:
        """Create a lightweight summary of a symbol."""
        return {
            "id": symbol_id,
            "kind": symbol.kind.value,
            "summary": symbol.semantics.summary,
        }

    @mcp.tool()
    def get_manifest() -> dict[str, Any]:
        """Get library metadata including name, version, and compatibility info."""
        manifest = doc.manifest
        result: dict[str, Any] = {
            "name": manifest.library.name,
            "version": manifest.library.version,
            "language": manifest.library.language,
            "schema_version": manifest.schema_version,
        }
        if manifest.compatibility:
            result["compatibility"] = manifest.compatibility.model_dump(
                exclude_none=True
            )
        return result

    @mcp.tool()
    def list_modules() -> list[str]:
        """Get all unique module paths in the library."""
        return sorted(index.modules)

    @mcp.tool()
    def list_symbols(
        module: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Browse symbols with optional filtering.

        Args:
            module: Filter by module path (e.g., "json.decoder")
            kind: Filter by symbol kind (function, class, method, attribute, module, constant)

        Returns:
            List of symbol summaries with id, kind, and summary
        """
        # Validate kind if provided
        valid_kinds = [k.value for k in SymbolKind]
        if kind and kind not in valid_kinds:
            return [{"error": f"Invalid kind '{kind}'. Valid options: {valid_kinds}"}]

        # Get candidate symbol IDs
        if module is not None:
            candidates = set(index.symbols_by_module.get(module, []))
        else:
            candidates = set(index.symbols_by_id.keys())

        # Filter by kind if provided
        if kind is not None:
            kind_candidates = set(index.symbols_by_kind.get(kind, []))
            candidates = candidates & kind_candidates

        # Build results
        results = []
        for symbol_id in sorted(candidates):
            symbol = index.symbols_by_id[symbol_id]
            results.append(_symbol_summary(symbol_id, symbol))

        return results

    @mcp.tool()
    def get_symbol(symbol_id: str) -> dict[str, Any]:
        """Get full details for a specific symbol.

        Args:
            symbol_id: Symbol identifier (e.g., "json:loads", "pathlib:Path#resolve")

        Returns:
            Complete symbol information including signatures, parameters, and semantics
        """
        symbol = index.symbols_by_id.get(symbol_id)
        if symbol is None:
            return {"error": f"Symbol not found: {symbol_id}"}

        result = symbol.model_dump(exclude_none=True)
        result["id"] = symbol_id
        return result

    @mcp.tool()
    def search_symbols(
        query: str,
        fields: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find symbols by text search.

        Args:
            query: Search text (case-insensitive)
            fields: Comma-separated fields to search: name, summary, description (default: all)

        Returns:
            List of matching symbol summaries
        """
        query_lower = query.lower()

        # Parse fields
        if fields:
            search_fields = [f.strip() for f in fields.split(",")]
        else:
            search_fields = ["name", "summary", "description"]

        results = []
        for symbol_id, symbol in index.symbols_by_id.items():
            matched = False

            # Search in name (extracted from symbol_id)
            if "name" in search_fields:
                # Extract name from ID: "module:name" or "module:Class#method"
                name_part = symbol_id.split(":")[-1] if ":" in symbol_id else symbol_id
                if query_lower in name_part.lower():
                    matched = True

            # Search in summary
            if not matched and "summary" in search_fields:
                if query_lower in symbol.semantics.summary.lower():
                    matched = True

            # Search in description
            if not matched and "description" in search_fields:
                if symbol.semantics.description:
                    if query_lower in symbol.semantics.description.lower():
                        matched = True

            if matched:
                results.append(_symbol_summary(symbol_id, symbol))

        return sorted(results, key=lambda x: x["id"])

    @mcp.tool()
    def get_class_members(class_id: str) -> list[dict[str, Any]]:
        """Get all methods and attributes of a class.

        Args:
            class_id: Class identifier (e.g., "pathlib:Path")

        Returns:
            List of member summaries (methods, attributes) belonging to the class
        """
        # Check if the class exists
        if class_id not in index.symbols_by_id:
            return [{"error": f"Class not found: {class_id}"}]

        # Check if it's actually a class
        class_symbol = index.symbols_by_id[class_id]
        if class_symbol.kind != SymbolKind.CLASS:
            return [{"error": f"Symbol '{class_id}' is not a class (kind: {class_symbol.kind.value})"}]

        # Get members
        member_ids = index.class_members.get(class_id, [])
        results = []
        for member_id in sorted(member_ids):
            symbol = index.symbols_by_id[member_id]
            results.append(_symbol_summary(member_id, symbol))

        return results

    return mcp


def run_server(manifest_path: str | Path, name: str | None = None) -> None:
    """Create and run an MCP server for the given LCP manifest.

    Args:
        manifest_path: Path to the .lcp.json file
        name: Server name (default: lcp-{library-name})
    """
    server = create_server(manifest_path, name=name)
    server.run()
