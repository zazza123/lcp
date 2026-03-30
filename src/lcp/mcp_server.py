"""MCP server that exposes LCP manifest data to AI agents."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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


class MultiLibraryIndex:
    """Manages multiple LCPIndex instances for a universal MCP server.

    Holds one LCPIndex per loaded library, keyed by library name.
    Tracks the most recently resolved library as the implicit default.
    """

    def __init__(self) -> None:
        self._indexes: dict[str, LCPIndex] = {}
        self._default: str | None = None

    @property
    def default_library(self) -> str | None:
        """Most recently resolved library name (used as implicit default)."""
        return self._default

    def add(self, name: str, index: LCPIndex) -> None:
        """Register a library index."""
        self._indexes[name] = index
        self._default = name

    def get(self, name: str | None = None) -> LCPIndex | None:
        """Return the index for *name*, or the default index if *name* is None."""
        key = name if name is not None else self._default
        if key is None:
            return None
        return self._indexes.get(key)

    def list_libraries(self) -> list[dict[str, Any]]:
        """Return summary info for all loaded libraries."""
        result = []
        for name, idx in self._indexes.items():
            lib = idx.doc.manifest.library
            result.append(
                {
                    "name": name,
                    "version": lib.version,
                    "language": lib.language,
                    "symbol_count": len(idx.symbols_by_id),
                    "is_default": name == self._default,
                }
            )
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._indexes


def load_lcp_document(path: str | Path) -> LCPDocument:
    """Load and validate an LCP document from a file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"LCP file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return LCPDocument.model_validate(data)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path.home() / ".lcp" / "cache"


def _cache_path(cache_dir: Path, name: str, version: str) -> Path:
    """Return the cache file path for a library version."""
    return cache_dir / name / f"{version}.lcp.json"


def _load_from_cache(cache_dir: Path, name: str, version: str) -> LCPDocument | None:
    """Load a cached LCP document if it exists."""
    path = _cache_path(cache_dir, name, version)
    if path.exists():
        try:
            return load_lcp_document(path)
        except Exception:
            return None
    return None


def _find_any_cached(cache_dir: Path, name: str) -> LCPDocument | None:
    """Return the first valid cached document found for *name*, regardless of version."""
    lib_dir = cache_dir / name
    if not lib_dir.is_dir():
        return None
    for path in sorted(lib_dir.glob("*.lcp.json")):
        try:
            return load_lcp_document(path)
        except Exception:
            continue
    return None


def _save_to_cache(cache_dir: Path, doc: LCPDocument) -> None:
    """Persist an LCP document to the cache directory."""
    name = doc.manifest.library.name
    version = doc.manifest.library.version or "unknown"
    path = _cache_path(cache_dir, name, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.to_file(str(path))


def _installed_version(package_name: str) -> str | None:
    """Return the installed version of *package_name*, or None if not found."""
    try:
        from importlib.metadata import version

        return version(package_name)
    except Exception:
        return None


_REGISTRY_FETCH_TIMEOUT = 10  # seconds
_ALLOWED_REGISTRY_SCHEMES = {"http", "https"}
_DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main"
)


def _fetch_from_registry(
    name: str,
    registry_url: str,
    language: str = "python",
    version: str | None = None,
    timeout: int = _REGISTRY_FETCH_TIMEOUT,
) -> LCPDocument:
    """Fetch an LCP manifest from a remote registry.

    Constructs the request URL using the registry's standard path layout:
    ``{registry_url}/manifests/{language}/{name}/{version}.lcp.json``.
    When *version* is not supplied, ``"latest"`` is used as the version segment.

    Args:
        name: Python package name (e.g. ``"requests"``).
        registry_url: Base URL of the LCP registry
            (e.g. ``"https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main"``).
            Must use ``http`` or ``https`` scheme.
        language: Programming language of the package (default: ``"python"``).
        version: Package version string (e.g. ``"2.31.0"``).  When *None*,
            the segment ``"latest"`` is used so registries can expose a
            canonical latest entry.
        timeout: Request timeout in seconds (default: 10).

    Returns:
        Validated :class:`LCPDocument` fetched from the registry.

    Raises:
        ImportError: If the registry URL has an unsupported scheme, the
            package name contains path-traversal characters, the registry
            returns a non-200 response, the request times out, or the
            response body cannot be parsed as a valid LCP document.
    """
    # Validate the registry URL scheme
    scheme = registry_url.split("://")[0].lower() if "://" in registry_url else ""
    if scheme not in _ALLOWED_REGISTRY_SCHEMES:
        raise ImportError(
            f"Registry URL must use http or https scheme, got: '{registry_url}'"
        )

    # Prevent path traversal in the package name
    if ".." in name or "/" in name or "\\" in name:
        raise ImportError(
            f"Invalid package name for registry lookup: '{name}'"
        )

    effective_version = version or "latest"
    url = (
        f"{registry_url.rstrip('/')}/manifests/{language}/{name}/{effective_version}.lcp.json"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise ImportError(
            f"Registry returned HTTP {exc.code} for '{name}' at {url}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ImportError(
            f"Registry fetch failed for '{name}' at {url}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise ImportError(
            f"Registry fetch timed out for '{name}' at {url}"
        ) from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ImportError(
            f"Registry response for '{name}' is not a valid LCP document: {exc}"
        ) from exc

    try:
        return LCPDocument.model_validate(data)
    except Exception as exc:
        raise ImportError(
            f"Registry response for '{name}' is not a valid LCP document: {exc}"
        ) from exc


def resolve_library_document(
    name: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    no_cache: bool = False,
    registry_url: str | None = None,
) -> tuple[LCPDocument, str]:
    """Resolve an LCP document for *name* using the standard resolution order.

    Resolution order:
      1. Local cache  (~/.lcp/cache/{name}/{version}.lcp.json)
      2. Live scan    (package is pip-installed)
      3. Registry     (HTTP GET from *registry_url* if provided)
      4. Error

    Registry manifests are fetched from the path
    ``{registry_url}/manifests/python/{name}/{version}.lcp.json``.
    When the installed version is unknown, ``"latest"`` is used as the
    version segment so registries can expose a canonical latest entry.

    Args:
        name: Python package name to resolve.
        cache_dir: Cache root directory (default: ~/.lcp/cache/).
        no_cache: Skip cache read/write entirely.
        registry_url: Optional base URL of an LCP registry to try when local
            scanning fails.  The default official registry is at
            ``https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main``.

    Returns:
        Tuple of (LCPDocument, source) where source is ``"cache"``,
        ``"scan"``, or ``"registry"``.

    Raises:
        ImportError: If the package cannot be resolved via any available
            source (cache, scan, or registry).
    """
    from .scanner import scan_package
    from .generator import generate_lcp

    # Resolve the installed version once; used for both cache lookup and registry fetch
    installed_ver = _installed_version(name)

    # 1. Cache lookup
    if not no_cache:
        if installed_ver:
            # If the package has a known installed version, look for an exact match
            cached = _load_from_cache(cache_dir, name, installed_ver)
            if cached is not None:
                return cached, "cache"
        else:
            # No installed version metadata: return any cached entry for this package
            cached = _find_any_cached(cache_dir, name)
            if cached is not None:
                return cached, "cache"

    # 2. Live scan
    scan_error: Exception | None = None
    try:
        scanned = scan_package(name, include_private=False, recursive=True)
        doc = generate_lcp(scanned)
        if not no_cache:
            try:
                _save_to_cache(cache_dir, doc)
            except Exception:
                pass  # cache write failure is non-fatal
        return doc, "scan"
    except Exception as exc:
        scan_error = exc

    # 3. Registry fallback
    if registry_url:
        try:
            doc = _fetch_from_registry(name, registry_url, version=installed_ver)
            if not no_cache:
                try:
                    _save_to_cache(cache_dir, doc)
                except Exception:
                    pass  # cache write failure is non-fatal
            return doc, "registry"
        except ImportError:
            pass  # fall through to final error

    raise ImportError(
        f"Cannot resolve library '{name}': not installed or scan failed. "
        f"Install it first with: pip install {name}"
        + (f" (registry fetch also failed: {registry_url})" if registry_url else "")
    ) from scan_error


def _symbol_summary(symbol_id: str, symbol: Symbol) -> dict[str, Any]:
    """Create a lightweight summary of a symbol."""
    return {
        "id": symbol_id,
        "kind": symbol.kind.value,
        "summary": symbol.semantics.summary,
    }


def _normalize_return_type(returns: Any) -> str | None:
    """Convert a returns field (TypeRef or str) to a plain string."""
    if returns is None:
        return None
    if isinstance(returns, str):
        return returns
    # It's a TypeRef object
    if hasattr(returns, "name") and returns.name:
        return returns.name
    if hasattr(returns, "kind") and returns.kind:
        return returns.kind
    return str(returns)


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


# ---------------------------------------------------------------------------
# Universal multi-library server
# ---------------------------------------------------------------------------


def create_universal_server(
    name: str = "lcp-universal",
    cache_dir: Path | str | None = None,
    no_cache: bool = False,
    registry_url: str | None = None,
) -> FastMCP:
    """Create a universal MCP server that resolves any installed Python library.

    Unlike ``create_server`` (which requires a pre-built manifest), the
    universal server exposes a ``resolve_library`` tool that scans a package
    on-the-fly and caches the result.  All standard exploration tools
    (``list_modules``, ``list_symbols``, ``get_symbol``, …) accept an optional
    ``library`` parameter so agents can work with multiple libraries at once.

    Args:
        name: Server name shown to MCP clients (default: ``lcp-universal``).
        cache_dir: Root directory for cached manifests
            (default: ``~/.lcp/cache/``).
        no_cache: Disable reading from and writing to the cache.
        registry_url: Optional base URL of an LCP registry used as a fallback
            when local scanning fails
            (e.g. ``"https://registry.example.com"``).

    Returns:
        Configured FastMCP server instance.
    """
    resolved_cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    multi_index = MultiLibraryIndex()

    mcp = FastMCP(name)

    # ------------------------------------------------------------------
    # Local helpers
    # ------------------------------------------------------------------

    def _get_index(library: str | None) -> LCPIndex | None:
        return multi_index.get(library)

    def _no_library_error(library: str | None) -> dict[str, Any]:
        if library:
            return {
                "error": f"Library '{library}' is not loaded. "
                f"Call resolve_library('{library}') first."
            }
        return {
            "error": "No library loaded. Call resolve_library(name) first."
        }

    # ------------------------------------------------------------------
    # New tools: resolve_library, list_libraries
    # ------------------------------------------------------------------

    @mcp.tool()
    def resolve_library(name: str) -> dict[str, Any]:
        """Load a Python library's documentation. Call this before using other tools.

        Resolves the library in order:
          1. Local cache  (~/.lcp/cache/{name}/{version}.lcp.json)
          2. Live scan    (pip-installed package)
          3. Registry     (HTTP fetch from the configured registry URL, if set)

        After resolving, this library becomes the implicit default for all
        other tools when no ``library`` parameter is given.

        Args:
            name: Python package name (e.g. "requests", "fastapi").

        Returns:
            Manifest summary with name, version, symbol count, and source.
        """
        try:
            doc, source = resolve_library_document(
                name,
                cache_dir=resolved_cache_dir,
                no_cache=no_cache,
                registry_url=registry_url,
            )
        except ImportError as exc:
            return {"error": str(exc)}

        index = LCPIndex(doc)
        multi_index.add(name, index)

        lib = doc.manifest.library
        return {
            "status": "loaded",
            "name": lib.name,
            "version": lib.version,
            "language": lib.language,
            "symbol_count": len(index.symbols_by_id),
            "module_count": len(index.modules),
            "source": source,
            "next_step": "Use list_modules() or list_symbols() to start exploring.",
        }

    @mcp.tool()
    def list_libraries() -> list[dict[str, Any]]:
        """List all currently loaded libraries.

        Returns:
            Summary of each loaded library (name, version, symbol count).
        """
        return multi_index.list_libraries()

    # ------------------------------------------------------------------
    # Standard exploration tools (library-aware)
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_usage_guide() -> dict[str, Any]:
        """Get strategic guidance on how to efficiently use this universal LCP server.

        CALL THIS FIRST to understand the recommended workflow.

        Returns:
            Recommended workflow, cost optimization tips, and common mistakes to avoid.
        """
        return {
            "recommended_workflow": [
                {
                    "step": 1,
                    "action": "resolve_library",
                    "purpose": "Load a library's documentation",
                    "description": "Call resolve_library('package_name') to scan/load a library",
                },
                {
                    "step": 2,
                    "action": "get_manifest",
                    "purpose": "Check if this library can help with your task",
                    "description": "Confirm library name, version, and language",
                },
                {
                    "step": 3,
                    "action": "list_modules",
                    "purpose": "Identify relevant modules for your use case",
                    "description": "Browse module structure to find areas that match your needs",
                },
                {
                    "step": 4,
                    "action": "list_symbols",
                    "purpose": "Browse symbols in promising modules",
                    "description": "Use module and kind filters to narrow down to relevant symbols",
                },
                {
                    "step": 5,
                    "action": "get_symbol",
                    "purpose": "Get complete details before implementation",
                    "description": "Always check full signature, required parameters, and return types",
                },
                {
                    "step": 6,
                    "action": "get_class_members",
                    "purpose": "Explore class methods and attributes",
                    "description": "When working with classes, check all available methods",
                },
                {
                    "step": 7,
                    "action": "explore_return_type",
                    "purpose": "Understand what methods are available on returned objects",
                    "description": "Check return type classes to avoid inventing non-existent methods",
                },
            ],
            "multi_library_tips": [
                "Call resolve_library('name') for each library you need",
                "Pass library='name' to any tool to target a specific library",
                "The last resolved library is used as the implicit default",
                "Use list_libraries() to see all currently loaded libraries",
            ],
            "cost_optimization": {
                "prefer_browsing": "Use list_modules + list_symbols instead of search_symbols when possible",
                "filter_early": "Always use module and kind parameters in list_symbols to reduce results",
                "validate_before_use": "Always call get_symbol to verify required parameters and return types",
                "check_return_types": "Use explore_return_type or get_class_members on return type classes",
            },
            "common_mistakes": [
                "Forgetting to call resolve_library before using other tools",
                "Starting with search_symbols without first exploring modules (expensive!)",
                "Using symbols without checking required parameters via get_symbol",
                "Assuming return types instead of verifying with get_symbol",
                "Inventing methods on returned objects without checking get_class_members",
            ],
        }

    @mcp.tool()
    def get_manifest(library: str | None = None) -> dict[str, Any]:
        """Get library metadata including name, version, and compatibility info.

        Args:
            library: Library name (default: last resolved library).

        Returns:
            Library metadata dict.
        """
        index = _get_index(library)
        if index is None:
            return _no_library_error(library)

        doc = index.doc
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
    def list_modules(library: str | None = None) -> list[str] | dict[str, Any]:
        """Get all unique module paths in the library.

        Args:
            library: Library name (default: last resolved library).

        Returns:
            Sorted list of module paths, or an error dict if library not loaded.
        """
        index = _get_index(library)
        if index is None:
            return _no_library_error(library)
        return sorted(index.modules)

    @mcp.tool()
    def list_symbols(
        module: str | None = None,
        kind: str | None = None,
        library: str | None = None,
    ) -> list[dict[str, Any]]:
        """Browse symbols with optional filtering.

        Args:
            module: Filter by module path (e.g. "json.decoder").
            kind: Filter by symbol kind (function, class, method, attribute, module, constant).
            library: Library name (default: last resolved library).

        Returns:
            List of symbol summaries with id, kind, and summary.
        """
        index = _get_index(library)
        if index is None:
            return [_no_library_error(library)]

        valid_kinds = [k.value for k in SymbolKind]
        if kind and kind not in valid_kinds:
            return [{"error": f"Invalid kind '{kind}'. Valid options: {valid_kinds}"}]

        if module is not None:
            candidates = set(index.symbols_by_module.get(module, []))
        else:
            candidates = set(index.symbols_by_id.keys())

        if kind is not None:
            kind_candidates = set(index.symbols_by_kind.get(kind, []))
            candidates = candidates & kind_candidates

        results = []
        for symbol_id in sorted(candidates):
            symbol = index.symbols_by_id[symbol_id]
            results.append(_symbol_summary(symbol_id, symbol))

        return results

    @mcp.tool()
    def get_symbol(
        symbol_id: str,
        library: str | None = None,
    ) -> dict[str, Any]:
        """Get full details for a specific symbol.

        IMPORTANT: Always call this before using a symbol to verify:
        - Required parameters and their types
        - Return type (use explore_return_type for complex types)
        - Whether the function is async

        Args:
            symbol_id: Symbol identifier (e.g. "json:loads", "pathlib:Path#resolve").
            library: Library name (default: last resolved library).

        Returns:
            Complete symbol information including signatures, parameters, and semantics.
        """
        index = _get_index(library)
        if index is None:
            return _no_library_error(library)

        symbol = index.symbols_by_id.get(symbol_id)
        if symbol is None:
            return {"error": f"Symbol not found: {symbol_id}"}

        result = symbol.model_dump(exclude_none=True)
        result["id"] = symbol_id

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
            if return_type_str and not return_type_str.startswith(
                ("str", "int", "float", "bool", "None", "list", "dict", "tuple", "set")
            ):
                result["usage_hints"]["suggestion"] = (
                    f"Consider using explore_return_type('{symbol_id}') "
                    f"to see available methods on the returned object"
                )

        return result

    @mcp.tool()
    def search_symbols(
        query: str,
        fields: str | None = None,
        library: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find symbols by text search.

        ⚠️  EXPENSIVE OPERATION: This searches ALL symbols and can return large results.

        💡 RECOMMENDED: Try this more efficient workflow first:
           1. list_modules() - find relevant modules
           2. list_symbols(module="...", kind="...") - browse with filters
           3. get_symbol() - get full details

        Only use search_symbols when you need fuzzy text matching across the entire library.

        Args:
            query: Search text (case-insensitive).
            fields: Comma-separated fields to search: name, summary, description (default: all).
            library: Library name (default: last resolved library).

        Returns:
            List of matching symbol summaries.
        """
        index = _get_index(library)
        if index is None:
            return [_no_library_error(library)]

        query_lower = query.lower()

        if fields:
            search_fields = [f.strip() for f in fields.split(",")]
        else:
            search_fields = ["name", "summary", "description"]

        results = []
        for symbol_id, symbol in index.symbols_by_id.items():
            matched = False

            if "name" in search_fields:
                name_part = symbol_id.split(":")[-1] if ":" in symbol_id else symbol_id
                if query_lower in name_part.lower():
                    matched = True

            if not matched and "summary" in search_fields:
                if query_lower in symbol.semantics.summary.lower():
                    matched = True

            if not matched and "description" in search_fields:
                if symbol.semantics.description:
                    if query_lower in symbol.semantics.description.lower():
                        matched = True

            if matched:
                results.append(_symbol_summary(symbol_id, symbol))

        return sorted(results, key=lambda x: x["id"])

    @mcp.tool()
    def get_class_members(
        class_id: str,
        library: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all methods and attributes of a class.

        Args:
            class_id: Class identifier (e.g. "pathlib:Path").
            library: Library name (default: last resolved library).

        Returns:
            List of member summaries (methods, attributes) belonging to the class.
        """
        index = _get_index(library)
        if index is None:
            return [_no_library_error(library)]

        if class_id not in index.symbols_by_id:
            return [{"error": f"Class not found: {class_id}"}]

        class_symbol = index.symbols_by_id[class_id]
        if class_symbol.kind != SymbolKind.CLASS:
            return [
                {
                    "error": f"Symbol '{class_id}' is not a class "
                    f"(kind: {class_symbol.kind.value})"
                }
            ]

        member_ids = index.class_members.get(class_id, [])
        results = []
        for member_id in sorted(member_ids):
            symbol = index.symbols_by_id[member_id]
            results.append(_symbol_summary(member_id, symbol))

        return results

    @mcp.tool()
    def explore_return_type(
        symbol_id: str,
        library: str | None = None,
    ) -> dict[str, Any]:
        """Analyze the return type of a function/method and find related classes.

        Use this to avoid inventing methods on returned objects.

        Args:
            symbol_id: Function or method identifier.
            library: Library name (default: last resolved library).

        Returns:
            Return type information and suggested classes to explore.
        """
        index = _get_index(library)
        if index is None:
            return _no_library_error(library)

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

        type_parts = (
            return_type_str.replace("[", " ").replace("]", " ").replace(",", " ").split()
        )

        for type_part in type_parts:
            if type_part.lower() in (
                "str", "int", "float", "bool", "none", "list", "dict",
                "tuple", "set", "optional", "any", "union",
            ):
                continue

            for sid, sym in index.symbols_by_id.items():
                if sym.kind == SymbolKind.CLASS:
                    class_name = sid.split(":")[-1] if ":" in sid else sid
                    if type_part == class_name or type_part.endswith(class_name):
                        result["matching_classes"].append(
                            {"class_id": sid, "summary": sym.semantics.summary}
                        )

        if result["matching_classes"]:
            result["suggestions"].append(
                {
                    "action": "get_class_members",
                    "targets": [c["class_id"] for c in result["matching_classes"][:3]],
                    "reason": f"Explore methods available on {return_type_str} objects",
                }
            )
        else:
            result["suggestions"].append(
                {
                    "action": "search_symbols",
                    "query": type_parts[0] if type_parts else return_type_str,
                    "reason": f"Could not find exact class match for {return_type_str}, try searching",
                }
            )

        return result

    @mcp.tool()
    def get_suggestions(
        task_description: str,
        library: str | None = None,
    ) -> dict[str, Any]:
        """Get smart suggestions for exploring a library based on your task.

        Args:
            task_description: Brief description of what you're trying to accomplish.
            library: Library name (default: last resolved library).

        Returns:
            Suggested modules, symbols, and next exploration steps.
        """
        index = _get_index(library)
        if index is None:
            return _no_library_error(library)

        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        suggestions: dict[str, Any] = {
            "task": task_description,
            "suggested_modules": [],
            "suggested_symbols": [],
            "next_steps": [],
        }

        for module_name in sorted(index.modules):
            module_lower = module_name.lower()
            if any(word in module_lower for word in task_words if len(word) > 2):
                suggestions["suggested_modules"].append(module_name)

        for symbol_id, symbol in index.symbols_by_id.items():
            name_part = symbol_id.split(":")[-1] if ":" in symbol_id else symbol_id
            name_lower = name_part.lower()
            summary_lower = symbol.semantics.summary.lower()

            if any(
                word in name_lower or word in summary_lower
                for word in task_words
                if len(word) > 2
            ):
                if symbol.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION):
                    suggestions["suggested_symbols"].append(
                        {
                            "id": symbol_id,
                            "kind": symbol.kind.value,
                            "summary": symbol.semantics.summary,
                        }
                    )

        suggestions["suggested_modules"] = suggestions["suggested_modules"][:5]
        suggestions["suggested_symbols"] = suggestions["suggested_symbols"][:10]

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


def run_universal_server(
    name: str = "lcp-universal",
    cache_dir: Path | str | None = None,
    no_cache: bool = False,
    registry_url: str | None = None,
) -> None:
    """Create and run a universal MCP server that resolves any installed Python library.

    Args:
        name: Server name (default: lcp-universal).
        cache_dir: Root directory for cached manifests (default: ~/.lcp/cache/).
        no_cache: Disable reading from and writing to the cache.
        registry_url: Optional base URL of an LCP registry used as a fallback
            when local scanning fails.
    """
    server = create_universal_server(
        name=name, cache_dir=cache_dir, no_cache=no_cache, registry_url=registry_url
    )
    server.run()
