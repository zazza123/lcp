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

    def _normalize_return_type(returns: Any) -> str | None:
        """Convert returns field (TypeRef or str) to a string representation."""
        if returns is None:
            return None
        if isinstance(returns, str):
            return returns
        # It's a TypeRef object
        if hasattr(returns, 'name') and returns.name:
            return returns.name
        if hasattr(returns, 'kind') and returns.kind:
            return returns.kind
        return str(returns)

    @mcp.tool()
    def get_usage_guide() -> dict[str, Any]:
        """Get strategic guidance on how to efficiently use this LCP manifest.

        CALL THIS FIRST to understand the recommended workflow for exploring
        this library and avoiding common mistakes.

        Returns:
            Recommended workflow, cost optimization tips, and common mistakes to avoid
        """
        return {
            "recommended_workflow": [
                {
                    "step": 1,
                    "action": "get_manifest",
                    "purpose": "Check if this library can help with your task",
                    "description": "Start by understanding what this library does and its version",
                },
                {
                    "step": 2,
                    "action": "list_modules",
                    "purpose": "Identify relevant modules for your use case",
                    "description": "Browse module structure to find areas that match your needs",
                },
                {
                    "step": 3,
                    "action": "list_symbols",
                    "purpose": "Browse symbols in promising modules",
                    "description": "Use module and kind filters to narrow down to relevant symbols",
                },
                {
                    "step": 4,
                    "action": "get_symbol",
                    "purpose": "Get complete details before implementation",
                    "description": "Always check full signature, required parameters, and return types",
                },
                {
                    "step": 5,
                    "action": "get_class_members",
                    "purpose": "Explore class methods and attributes",
                    "description": "When working with classes, check all available methods",
                },
                {
                    "step": 6,
                    "action": "explore_return_type",
                    "purpose": "Understand what methods are available on returned objects",
                    "description": "Check return type classes to avoid inventing non-existent methods",
                },
            ],
            "cost_optimization": {
                "prefer_browsing": "Use list_modules + list_symbols instead of search_symbols when possible",
                "filter_early": "Always use module and kind parameters in list_symbols to reduce results",
                "validate_before_use": "Always call get_symbol to verify required parameters and return types",
                "check_return_types": "Use explore_return_type or get_class_members on return type classes",
            },
            "common_mistakes": [
                "Starting with search_symbols without first exploring modules (expensive!)",
                "Using symbols without checking required parameters via get_symbol",
                "Assuming return types instead of verifying with get_symbol",
                "Inventing methods on returned objects without checking get_class_members",
                "Not exploring class members with get_class_members before using a class",
            ],
        }

    @mcp.tool()
    def get_manifest() -> dict[str, Any]:
        """Get library metadata including name, version, and compatibility info.

        Use this early to confirm the library matches your needs before exploring further.
        """
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

        IMPORTANT: Always call this before using a symbol to verify:
        - Required parameters and their types
        - Return type (use explore_return_type for complex types)
        - Whether the function is async

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

        # Add usage hints to help agents use the symbol correctly
        if symbol.signatures:
            sig = symbol.signatures[0]
            required_params = [
                {"name": p.name, "type": p.type}
                for p in (sig.params or [])
                if p.required
            ]
            optional_params = [
                {"name": p.name, "type": p.type, "default": p.default}
                for p in (sig.params or [])
                if not p.required
            ]
            return_type_str = _normalize_return_type(sig.returns)
            result["usage_hints"] = {
                "required_parameters": required_params,
                "optional_parameters": optional_params,
                "is_async": sig.async_ if sig.async_ is not None else False,
                "return_type": return_type_str,
            }
            # Add suggestion to explore return type if it looks like a class
            if return_type_str and not return_type_str.startswith(("str", "int", "float", "bool", "None", "list", "dict", "tuple", "set")):
                result["usage_hints"]["suggestion"] = f"Consider using explore_return_type('{symbol_id}') to see available methods on the returned object"

        return result

    @mcp.tool()
    def search_symbols(
        query: str,
        fields: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find symbols by text search.

        ⚠️  EXPENSIVE OPERATION: This searches ALL symbols and can return large results.

        💡 RECOMMENDED: Try this more efficient workflow first:
           1. list_modules() - find relevant modules
           2. list_symbols(module="...", kind="...") - browse with filters
           3. get_symbol() - get full details

        Only use search_symbols when you need fuzzy text matching across the entire library.

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

    @mcp.tool()
    def explore_return_type(symbol_id: str) -> dict[str, Any]:
        """Analyze the return type of a function/method and find related classes.

        Use this to avoid inventing methods on returned objects - check what's actually available.

        Args:
            symbol_id: Function or method identifier (e.g., "module:func", "module:Class#method")

        Returns:
            Return type information and suggested classes to explore with get_class_members
        """
        symbol = index.symbols_by_id.get(symbol_id)
        if symbol is None:
            return {"error": f"Symbol not found: {symbol_id}"}

        if not symbol.signatures:
            return {"error": f"No signature information available for {symbol_id}"}

        sig = symbol.signatures[0]
        return_type_str = _normalize_return_type(sig.returns)
        if not return_type_str:
            return {"message": "No return type information available", "symbol_id": symbol_id}

        result: dict[str, Any] = {
            "symbol_id": symbol_id,
            "return_type": return_type_str,
            "matching_classes": [],
            "suggestions": [],
        }

        # Look for classes that match the return type
        # Handle generic types like List[SomeClass] or Optional[SomeClass]
        type_parts = return_type_str.replace("[", " ").replace("]", " ").replace(",", " ").split()

        for type_part in type_parts:
            # Skip common built-in types
            if type_part.lower() in ("str", "int", "float", "bool", "none", "list", "dict", "tuple", "set", "optional", "any", "union"):
                continue

            # Find matching classes in the index
            for sid, sym in index.symbols_by_id.items():
                if sym.kind == SymbolKind.CLASS:
                    # Match by class name (last part of the ID)
                    class_name = sid.split(":")[-1] if ":" in sid else sid
                    if type_part == class_name or type_part.endswith(class_name):
                        result["matching_classes"].append({
                            "class_id": sid,
                            "summary": sym.semantics.summary,
                        })

        if result["matching_classes"]:
            result["suggestions"].append({
                "action": "get_class_members",
                "targets": [c["class_id"] for c in result["matching_classes"][:3]],
                "reason": f"Explore methods available on {return_type_str} objects",
            })
        else:
            result["suggestions"].append({
                "action": "search_symbols",
                "query": type_parts[0] if type_parts else return_type_str,
                "reason": f"Could not find exact class match for {return_type_str}, try searching",
            })

        return result

    @mcp.tool()
    def get_suggestions(task_description: str) -> dict[str, Any]:
        """Get smart suggestions for exploring this library based on your task.

        Provide a brief description of what you're trying to accomplish,
        and get suggestions for which modules and symbols to explore first.

        Args:
            task_description: Brief description of what you're trying to accomplish

        Returns:
            Suggested modules, symbols, and next exploration steps
        """
        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        suggestions: dict[str, Any] = {
            "task": task_description,
            "suggested_modules": [],
            "suggested_symbols": [],
            "next_steps": [],
        }

        # Find modules with matching names
        for module_name in sorted(index.modules):
            module_lower = module_name.lower()
            # Check if any task word appears in the module name
            if any(word in module_lower for word in task_words if len(word) > 2):
                suggestions["suggested_modules"].append(module_name)

        # Find symbols with matching summaries or names
        for symbol_id, symbol in index.symbols_by_id.items():
            name_part = symbol_id.split(":")[-1] if ":" in symbol_id else symbol_id
            name_lower = name_part.lower()
            summary_lower = symbol.semantics.summary.lower()

            # Check matches in name or summary
            if any(word in name_lower or word in summary_lower for word in task_words if len(word) > 2):
                # Prefer classes and functions over methods
                if symbol.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION):
                    suggestions["suggested_symbols"].append({
                        "id": symbol_id,
                        "kind": symbol.kind.value,
                        "summary": symbol.semantics.summary,
                    })

        # Limit results
        suggestions["suggested_modules"] = suggestions["suggested_modules"][:5]
        suggestions["suggested_symbols"] = suggestions["suggested_symbols"][:10]

        # Generate next steps
        if suggestions["suggested_modules"]:
            for module in suggestions["suggested_modules"][:2]:
                suggestions["next_steps"].append(
                    f"Explore module with: list_symbols(module='{module}')"
                )
        elif suggestions["suggested_symbols"]:
            for sym in suggestions["suggested_symbols"][:2]:
                suggestions["next_steps"].append(
                    f"Get details with: get_symbol('{sym['id']}')"
                )
        else:
            suggestions["next_steps"] = [
                "No direct matches found. Try:",
                "1. list_modules() - browse all available modules",
                "2. list_symbols(kind='class') - see all classes",
                "3. list_symbols(kind='function') - see all functions",
            ]

        return suggestions

    return mcp


def run_server(manifest_path: str | Path, name: str | None = None) -> None:
    """Create and run an MCP server for the given LCP manifest.

    Args:
        manifest_path: Path to the .lcp.json file
        name: Server name (default: lcp-{library-name})
    """
    server = create_server(manifest_path, name=name)
    server.run()
