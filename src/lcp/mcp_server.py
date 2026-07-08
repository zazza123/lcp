"""MCP server that exposes LCP manifest data to AI agents."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP

from .models import LCPDocument, Symbol, SymbolKind
from .naming import normalize_package_name
from .subprocess_scan import (
    DEFAULT_SCAN_TIMEOUT,
    ScanImportError,
    ScanInterpreterNotFoundError,
    ScanSpawnError,
    ScanTimeoutError,
    scan_package_subprocess,
)

DEFAULT_MAX_RESPONSE_BYTES = 25_000
"""Default byte budget for any list-returning tool payload (spec D6).

Calibrated against polars 1.42.1: DataFrame's 159 member summaries alone are
~30 KB, so heavy classes are expected to truncate; 25 KB is ~6k tokens.
"""


def _symbol_name(symbol_id: str) -> str:
    """Return the bare symbol name (last segment after ':' and '#')."""
    return symbol_id.split(":")[-1].split("#")[-1]


def _alias_rank(alias_id: str) -> tuple[int, int, str]:
    """Order alias ids: fewest module dots, then shortest, then lexicographic.

    The package-root re-export (``requests:get``) is the path users see in
    documentation, so it wins the "preferred alias" slot.
    """
    return (alias_id.split(":")[0].count("."), len(alias_id), alias_id)


def _import_statement(symbol_id: str, kind: SymbolKind) -> str:
    """Return the import line an agent should write for *symbol_id*.

    Args:
        symbol_id: LCP symbol id (``module:entity`` or ``module:Class#member``).
        kind: The symbol's kind; modules render as ``import a.b``.

    Returns:
        e.g. ``"from requests.api import get"``; class members import the
        class (``pathlib:Path#resolve`` → ``"from pathlib import Path"``).
    """
    module, _, entity = symbol_id.partition(":")
    if not entity:
        return f"import {module}"
    if kind == SymbolKind.MODULE:
        return f"import {module}.{entity}"
    top_level = entity.split("#")[0]
    return f"from {module} import {top_level}"


def _fit_list(items: list[Any], max_bytes: int) -> tuple[list[Any], bool]:
    """Keep the longest prefix of *items* whose JSON size fits *max_bytes*.

    Args:
        items: JSON-serializable payload entries, already ordered.
        max_bytes: Byte budget for the serialized list.

    Returns:
        Tuple of (kept prefix, truncated flag).
    """
    total = 2  # enclosing brackets
    kept: list[Any] = []
    for item in items:
        size = len(json.dumps(item, default=str)) + 2
        if total + size > max_bytes:
            return kept, True
        kept.append(item)
        total += size
    return kept, False


class LCPIndex:
    """In-memory index of LCP document for fast lookups."""

    def __init__(self, doc: LCPDocument):
        self.doc = doc
        self.symbols_by_id: dict[str, Symbol] = doc.symbols
        self.symbols_by_module: dict[str, list[str]] = defaultdict(list)
        self.symbols_by_kind: dict[str, list[str]] = defaultdict(list)
        self.class_members: dict[str, list[str]] = defaultdict(list)
        self.classes_by_name: dict[str, list[str]] = defaultdict(list)
        self.modules: set[str] = set()
        self.alias_to_canonical: dict[str, str] = {}
        self.preferred_alias: dict[str, str] = {}

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

            # Index classes by bare name for exact return-type resolution
            if symbol.kind == SymbolKind.CLASS:
                self.classes_by_name[_symbol_name(symbol_id)].append(symbol_id)

        for ids in self.classes_by_name.values():
            ids.sort()

        # Alias indexes (spec D10): alias ids resolve to the canonical
        # entry, and class aliases expand to member ids at build time —
        # without materializing duplicate entries in the manifest.
        for symbol_id, symbol in self.symbols_by_id.items():
            aliases = [
                a
                for a in (symbol.aliases or [])
                if a not in self.symbols_by_id
            ]
            if not aliases:
                continue
            for alias in aliases:
                self.alias_to_canonical.setdefault(alias, symbol_id)
            preferred = min(aliases, key=_alias_rank)
            self.preferred_alias[symbol_id] = preferred
            if symbol.kind == SymbolKind.CLASS:
                for member_id in self.class_members.get(symbol_id, []):
                    entity = member_id.split("#", 1)[1]
                    for alias in aliases:
                        self.alias_to_canonical.setdefault(
                            f"{alias}#{entity}", member_id
                        )
                    self.preferred_alias[member_id] = f"{preferred}#{entity}"

    def resolve_id(self, symbol_id: str) -> tuple[str | None, Symbol | None]:
        """Resolve a possibly-aliased id to ``(canonical_id, symbol)``.

        Returns ``(None, None)`` when the id matches neither a canonical
        entry nor a known alias.
        """
        symbol = self.symbols_by_id.get(symbol_id)
        if symbol is not None:
            return symbol_id, symbol
        canonical = self.alias_to_canonical.get(symbol_id)
        if canonical is not None:
            return canonical, self.symbols_by_id[canonical]
        return None, None


def _error(
    code: str, message: str, hint: str | None = None, **extra: Any
) -> dict[str, Any]:
    """Build the stable structured-error shape every tool returns on failure.

    Args:
        code: Machine-readable error code (e.g. ``"ambiguous_library"``).
        message: Human/agent-readable description of what went wrong.
        hint: Optional recovery suggestion for the calling agent.
        **extra: Additional context keys merged into the error object
            (e.g. ``loaded_libraries=[...]``).

    Returns:
        ``{"error": {"code": ..., "message": ..., "hint"?: ..., **extra}}``.
    """
    err: dict[str, Any] = {"code": code, "message": message}
    if hint is not None:
        err["hint"] = hint
    err.update(extra)
    return {"error": err}


class MultiLibraryIndex:
    """Registry of loaded LCPIndex instances for the MCP server.

    Holds one :class:`LCPIndex` per loaded library plus the source it was
    resolved from. There is deliberately **no** implicit default library:
    with one library loaded :meth:`resolve` returns it for a ``None``
    argument, with several it returns an ``ambiguous_library`` error
    (spec D7).
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[LCPIndex, str]] = {}

    def add(self, name: str, index: LCPIndex, source: str = "scan") -> None:
        """Register (or replace) a library index.

        Args:
            name: Library name used as the lookup key.
            index: Built index for the library's manifest.
            source: Where the manifest came from (``"cache"``, ``"scan"``,
                ``"registry"``, or ``"manifest"`` for a pre-loaded file).
        """
        self._entries[name] = (index, source)

    def get(self, name: str) -> LCPIndex | None:
        """Return the index registered under *name*, or None."""
        entry = self._entries.get(name)
        return entry[0] if entry else None

    def source(self, name: str) -> str | None:
        """Return the resolution source recorded for *name*, or None."""
        entry = self._entries.get(name)
        return entry[1] if entry else None

    def names(self) -> list[str]:
        """Return the sorted names of all loaded libraries."""
        return sorted(self._entries)

    def resolve(
        self, library: str | None
    ) -> tuple[str | None, LCPIndex | None, dict[str, Any] | None]:
        """Resolve a tool's ``library`` argument to an index (spec D7).

        Args:
            library: Explicit library name, or None.

        Returns:
            ``(name, index, None)`` on success, ``(None, None, error_dict)``
            on failure — the error dict follows the D5 shape.
        """
        if library is not None:
            entry = self._entries.get(library)
            if entry is not None:
                return library, entry[0], None
            return None, None, _error(
                "library_not_loaded",
                f"Library '{library}' is not loaded.",
                hint=f"Call resolve_library('{library}') first.",
                loaded_libraries=self.names(),
            )
        if not self._entries:
            return None, None, _error(
                "library_not_loaded",
                "No library is loaded.",
                hint="Call resolve_library(<package name>) first.",
            )
        if len(self._entries) == 1:
            name = next(iter(self._entries))
            return name, self._entries[name][0], None
        return None, None, _error(
            "ambiguous_library",
            "Multiple libraries are loaded; pass library=<name>.",
            hint="Pick one of loaded_libraries and retry with library=<name>.",
            loaded_libraries=self.names(),
        )

    def list_libraries(self) -> list[dict[str, Any]]:
        """Return summary info for all loaded libraries."""
        result = []
        for name in self.names():
            idx, source = self._entries[name]
            lib = idx.doc.manifest.library
            result.append(
                {
                    "name": name,
                    "version": lib.version,
                    "language": lib.language,
                    "symbol_count": len(idx.symbols_by_id),
                    "source": source,
                }
            )
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._entries


def load_lcp_document(path: str | Path) -> LCPDocument:
    """Load and validate an LCP document from a file.

    Supports both plain ``.lcp.json`` files and gzip-compressed
    ``.lcp.json.gz`` files, detected transparently by file extension.
    """
    import gzip as _gzip

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"LCP file not found: {path}")

    if path.suffix == ".gz":
        with _gzip.open(path, "rb") as f:
            data = json.loads(f.read())
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

    return LCPDocument.model_validate(data)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path.home() / ".lcp" / "cache"


def _cache_path(cache_dir: Path, name: str, version: str) -> Path:
    """Return the cache file path for a library version."""
    return cache_dir / name / f"{version}.lcp.json.gz"


def _load_from_cache(cache_dir: Path, name: str, version: str) -> LCPDocument | None:
    """Load a cached LCP document if it exists.

    Accepts both ``.lcp.json.gz`` (preferred) and legacy ``.lcp.json`` files.
    """
    gz_path = cache_dir / name / f"{version}.lcp.json.gz"
    plain_path = cache_dir / name / f"{version}.lcp.json"
    for path in (gz_path, plain_path):
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
    # Prefer .lcp.json.gz files; fall back to plain .lcp.json
    candidates = sorted(lib_dir.glob("*.lcp.json.gz")) + sorted(lib_dir.glob("*.lcp.json"))
    for path in candidates:
        try:
            return load_lcp_document(path)
        except Exception:
            continue
    return None


def _save_to_cache(cache_dir: Path, doc: LCPDocument) -> None:
    """Persist an LCP document to the cache directory (gzip-compressed)."""
    import gzip as _gzip

    name = doc.manifest.library.name
    version = doc.manifest.library.version or "unknown"
    path = _cache_path(cache_dir, name, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _gzip.open(path, "wb") as f:
        f.write(doc.to_json(indent=2).encode("utf-8"))


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

    Constructs the request URL using the registry's standard sharded path layout:
    ``{registry_url}/manifests/{language}/{first_letter}/{slug}/{version}.lcp.json.gz``,
    where *slug* is the canonical, hyphenated package name (so ``google.adk``
    resolves under ``g/google-adk/``). When *version* is not supplied, the
    package's ``latest.json`` pointer is read to discover the canonical
    manifest file. The response body is decompressed from gzip before parsing.

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
    import gzip as _gzip

    # Validate the registry URL scheme
    scheme = registry_url.split("://")[0].lower() if "://" in registry_url else ""
    if scheme not in _ALLOWED_REGISTRY_SCHEMES:
        raise ImportError(
            f"Registry URL must use http or https scheme, got: '{registry_url}'"
        )

    # Prevent path traversal in the package name; also reject empty names
    if not name:
        raise ImportError("Package name must not be empty for registry lookup")
    if ".." in name or "/" in name or "\\" in name:
        raise ImportError(
            f"Invalid package name for registry lookup: '{name}'"
        )

    # Registry paths use the canonical slug, so a dotted import name like
    # ``google.adk`` is fetched from ``.../g/google-adk/``.
    slug = normalize_package_name(name)
    first_letter = slug[0]
    base_url = f"{registry_url.rstrip('/')}/manifests/{language}/{first_letter}/{slug}"

    def _get(target_url: str) -> bytes:
        try:
            with urllib.request.urlopen(target_url, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ImportError(
                f"Registry returned HTTP {exc.code} for '{name}' at {target_url}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ImportError(
                f"Registry fetch failed for '{name}' at {target_url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise ImportError(
                f"Registry fetch timed out for '{name}' at {target_url}"
            ) from exc

    if version:
        url = f"{base_url}/{version}.lcp.json.gz"
    else:
        # No explicit version: resolve the canonical manifest through the
        # ``latest.json`` pointer the registry stores per package, e.g.
        # ``{"version": "2.2.0", "manifest": "2.2.0.lcp.json.gz"}``.
        pointer_url = f"{base_url}/latest.json"
        try:
            pointer = json.loads(_get(pointer_url))
        except json.JSONDecodeError as exc:
            raise ImportError(
                f"Registry 'latest.json' for '{name}' is not valid JSON: {exc}"
            ) from exc
        manifest_file = pointer.get("manifest") if isinstance(pointer, dict) else None
        if not manifest_file or "/" in manifest_file or "\\" in manifest_file:
            raise ImportError(
                f"Registry 'latest.json' for '{name}' is missing a valid "
                f"'manifest' field: {pointer!r}"
            )
        url = f"{base_url}/{manifest_file}"

    body = _get(url)

    try:
        body = _gzip.decompress(body)
    except (_gzip.BadGzipFile, OSError):
        pass  # Not gzip-compressed; try to parse as plain JSON

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


def _scan_inprocess(name: str) -> LCPDocument:
    """Scan *name* by importing it into this process (legacy path)."""
    from .generator import generate_lcp
    from .scanner import scan_package

    return generate_lcp(scan_package(name, include_private=False, recursive=True))


def _scan_live(
    name: str,
    scan_mode: str,
    scan_python: str | None,
    scan_timeout: float,
) -> LCPDocument:
    """Run the live scan for *name* honoring the configured scan mode.

    Falls back to in-process scanning only when the subprocess could not be
    *spawned* (no package code ran) and the scan target is this very
    environment — a spawn failure with a configured ``scan_python`` must
    error instead, because scanning in-process would read the wrong venv,
    and a scan *crash* must never re-run in-process at all.
    """
    if scan_mode == "inprocess":
        return _scan_inprocess(name)
    try:
        return scan_package_subprocess(
            name, python=scan_python, timeout=scan_timeout
        )
    except ScanSpawnError:
        if scan_python is None or scan_python == sys.executable:
            return _scan_inprocess(name)
        raise


def resolve_library_document(
    name: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    no_cache: bool = False,
    registry_url: str | None = None,
    version: str | None = None,
    scan_mode: str = "subprocess",
    scan_python: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> tuple[LCPDocument, str]:
    """Resolve an LCP document for *name* using the standard resolution order.

    Resolution order:
      1. Local cache  (~/.lcp/cache/{name}/{version}.lcp.json)
      2. Live scan    (subprocess by default; see *scan_mode*)
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
        version: Optional exact version to prefer; overrides the installed
            version for cache lookup and registry fetch.  A live scan always
            returns the installed version regardless.
        scan_mode: ``"subprocess"`` (default) runs the live scan in a child
            interpreter — import-time crashes and heavy imports stay out of
            the server process; ``"inprocess"`` imports the package into
            this process (for environments where spawning is restricted).
        scan_python: Interpreter whose environment the live scan reads
            (default: this process's interpreter). This is how packages
            installed in a different venv get resolved.
        scan_timeout: Seconds before a subprocess scan is killed.

    Returns:
        Tuple of (LCPDocument, source) where source is ``"cache"``,
        ``"scan"``, or ``"registry"``.

    Raises:
        ImportError: If the package cannot be resolved via any available
            source (cache, scan, or registry).
    """
    # Resolve the installed version once; used for both cache lookup and
    # registry fetch. An explicit *version* takes precedence over it.
    installed_ver = _installed_version(name)
    lookup_ver = version or installed_ver

    # 1. Cache lookup
    if not no_cache:
        if lookup_ver:
            # Exact-version match (requested version wins over installed)
            cached = _load_from_cache(cache_dir, name, lookup_ver)
            if cached is not None:
                return cached, "cache"
        else:
            # No version to pin: return any cached entry for this package
            cached = _find_any_cached(cache_dir, name)
            if cached is not None:
                return cached, "cache"

    # 2. Live scan
    scan_error: Exception | None = None
    try:
        doc = _scan_live(name, scan_mode, scan_python, scan_timeout)
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
            doc = _fetch_from_registry(name, registry_url, version=lookup_ver)
            if not no_cache:
                try:
                    _save_to_cache(cache_dir, doc)
                except Exception:
                    pass  # cache write failure is non-fatal
            return doc, "registry"
        except ImportError:
            pass  # fall through to final error

    scan_interpreter = scan_python or sys.executable
    if isinstance(scan_error, ScanImportError):
        if scan_python:
            remedy = (
                "Check that the package is installed in that environment, "
                "or fix 'scan_python' in .lcp-config.json"
            )
        else:
            remedy = (
                "It may be installed in a different environment — point the "
                "server at that env via .lcp-config.json ('scan_python' or 'python')"
            )
        reason = (
            f"'{name}' is not importable by the scan interpreter "
            f"({scan_interpreter}). {remedy}; the distribution name may also "
            f"differ from the import path (e.g. import 'google.adk' is "
            f"provided by 'pip install google-adk')."
        )
    elif isinstance(
        scan_error, (ScanTimeoutError, ScanInterpreterNotFoundError, ScanSpawnError)
    ):
        # The runner's messages are already agent-facing and actionable.
        reason = str(scan_error)
    elif installed_ver:
        # The package is installed in this environment but scanning failed.
        reason = (
            f"'{name}' is installed (version {installed_ver}) in this environment "
            f"but the scan failed: {type(scan_error).__name__}: {scan_error}"
        )
    elif isinstance(scan_error, ImportError):
        # In-process scan: could not import with the interpreter running lcp.
        reason = (
            f"'{name}' is not importable by the Python interpreter running lcp "
            f"({sys.executable}). It may be installed in a different environment "
            f"(point the plugin at that env via .lcp-config.json), or the distribution "
            f"name may differ from the import path "
            f"(e.g. import 'google.adk' is provided by 'pip install google-adk')."
        )
    else:
        reason = (
            f"could not resolve '{name}': {type(scan_error).__name__}: {scan_error}"
        )

    raise ImportError(
        f"Cannot resolve library '{name}': {reason}"
        + (f" (registry fetch also failed: {registry_url})" if registry_url else "")
    ) from scan_error


_VALID_KINDS = [k.value for k in SymbolKind]


def _symbol_summary(
    index: LCPIndex, symbol_id: str, symbol: Symbol
) -> dict[str, Any]:
    """Create a compact search/browse hit for a symbol (spec D4/D10).

    Presents the preferred importable id; alias hits carry
    ``resolved_via_alias`` pointing at the canonical definition site.
    """
    display_id = index.preferred_alias.get(symbol_id, symbol_id)
    hit = {
        "id": display_id,
        "kind": symbol.kind.value,
        "summary": symbol.semantics.summary,
        "import": _import_statement(display_id, symbol.kind),
    }
    if display_id != symbol_id:
        hit["resolved_via_alias"] = symbol_id
    return hit


def _search_index(
    index: LCPIndex,
    query: str,
    module: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Ranked, capped symbol search over one library index (spec D3/D4/D6).

    Ranking tiers: exact name > name prefix > name substring > summary
    substring > description substring; ties break by id. An empty *query*
    browses instead: results are ordered by ``(kind, name, id)``.

    Args:
        index: The library index to search.
        query: Case-insensitive text; empty string means "browse".
        module: Optional module-path filter.
        kind: Optional symbol-kind filter (validated).
        limit: Maximum hits to return, clamped to 1..100 (default 20).
        max_bytes: Byte budget for the results list.

    Returns:
        ``{"results": [...], "total": N, "truncated": bool}`` or a D5 error
        dict when *kind* is invalid.
    """
    if kind is not None and kind not in _VALID_KINDS:
        return _error(
            "invalid_kind",
            f"Invalid kind '{kind}'.",
            hint=f"Valid kinds: {', '.join(_VALID_KINDS)}.",
        )
    limit = max(1, min(int(limit), 100))

    if module is not None:
        candidates = list(index.symbols_by_module.get(module, []))
    else:
        candidates = list(index.symbols_by_id)
    if kind is not None:
        kind_ids = set(index.symbols_by_kind.get(kind, []))
        candidates = [sid for sid in candidates if sid in kind_ids]

    q = query.strip().lower()
    if not q:
        # Browse mode: no relevance to rank by — deterministic (kind, name, id)
        ranked = sorted(
            candidates,
            key=lambda sid: (
                index.symbols_by_id[sid].kind.value,
                _symbol_name(index.preferred_alias.get(sid, sid)).lower(),
                sid,
            ),
        )
    else:
        scored: list[tuple[int, str]] = []
        for sid in candidates:
            symbol = index.symbols_by_id[sid]
            names = {_symbol_name(sid).lower()}
            names.update(
                _symbol_name(a).lower() for a in (symbol.aliases or [])
            )
            if q in names:
                score = 0
            elif any(n.startswith(q) for n in names):
                score = 1
            elif any(q in n for n in names):
                score = 2
            elif q in symbol.semantics.summary.lower():
                score = 3
            elif (
                symbol.semantics.description
                and q in symbol.semantics.description.lower()
            ):
                score = 4
            else:
                continue
            scored.append((score, sid))
        scored.sort()
        ranked = [sid for _, sid in scored]

    total = len(ranked)
    hits = [
        _symbol_summary(index, sid, index.symbols_by_id[sid])
        for sid in ranked[:limit]
    ]
    hits, byte_truncated = _fit_list(hits, max_bytes)
    return {
        "results": hits,
        "total": total,
        "truncated": byte_truncated or total > len(hits),
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


_BUILTIN_TYPE_NAMES = {
    "str", "int", "float", "bool", "bytes", "none", "nonetype", "list",
    "dict", "tuple", "set", "frozenset", "optional", "any", "union",
    "callable", "iterator", "iterable", "sequence", "mapping", "self",
}


def _resolve_type_to_classes(index: LCPIndex, return_type: str) -> list[str]:
    """Resolve a return-type string to class ids by exact name match (D4).

    Splits generics/unions (``list[Path]``, ``Path | None``), strips dotted
    prefixes, skips builtins, and looks each token up in
    ``index.classes_by_name`` — exact matches only, never ``endswith``.

    Args:
        index: The library index to resolve against.
        return_type: Normalized return-type string.

    Returns:
        Sorted, de-duplicated list of matching class ids.
    """
    matches: set[str] = set()
    for token in re.split(r"[\[\](),|\s]+", return_type):
        bare = token.strip().split(".")[-1]
        if not bare or bare.lower() in _BUILTIN_TYPE_NAMES:
            continue
        matches.update(index.classes_by_name.get(bare, []))
    return sorted(matches)


def _symbol_detail(
    index: LCPIndex,
    symbol_id: str,
    symbol: Symbol,
    max_bytes: int,
    requested_id: str | None = None,
) -> dict[str, Any]:
    """Build the full get_symbol payload for one symbol (spec D4/D10).

    *symbol_id* is always the canonical id; *requested_id* is echoed as the
    entry's ``id`` when the caller reached the symbol through an alias, with
    ``resolved_via_alias`` naming the definition site. The ``import`` line
    always uses the preferred importable path (F2).

    The returned entry is guaranteed to fit *max_bytes*: the description is
    truncated as a last resort, and inline class members get whatever budget
    the body leaves over — so a symbol can degrade but never become
    unfetchable.
    """
    result = symbol.model_dump(exclude_none=True, mode="json")
    display_id = requested_id if requested_id is not None else symbol_id
    result["id"] = display_id
    if display_id != symbol_id:
        result["resolved_via_alias"] = symbol_id
    import_id = index.preferred_alias.get(symbol_id, display_id)
    result["import"] = _import_statement(import_id, symbol.kind)

    if symbol.signatures:
        sig = symbol.signatures[0]
        hints: dict[str, Any] = {
            "required_parameters": [
                {"name": p.name, "type": p.type}
                for p in (sig.params or [])
                if p.required
            ],
            "optional_parameters": [
                {"name": p.name, "type": p.type, "default": p.default}
                for p in (sig.params or [])
                if not p.required
            ],
            "is_async": sig.async_ if sig.async_ is not None else False,
            "return_type": _normalize_return_type(sig.returns),
        }
        if hints["return_type"]:
            returns_classes = sorted(
                index.preferred_alias.get(c, c)
                for c in _resolve_type_to_classes(index, hints["return_type"])
            )
            if returns_classes:
                hints["returns_classes"] = returns_classes
                hints["next"] = (
                    f"returns {hints['return_type']} → "
                    f"get_symbol(ids=['{returns_classes[0]}']) to see its members"
                )
        result["usage_hints"] = hints

    # Enforce the byte budget on the entry itself. Cheapest sacrifice first:
    # drop trailing examples, then truncate the description as a last resort,
    # then give members whatever the body leaves over.
    slack = 400  # headroom for the truncation-marker fields added below
    body_size = len(json.dumps(result, default=str))
    examples = result.get("semantics", {}).get("examples")
    if body_size + slack > max_bytes and examples:
        examples_size = len(json.dumps(examples, default=str))
        example_budget = max(0, max_bytes - (body_size - examples_size) - slack)
        kept_examples, examples_truncated = _fit_list(examples, example_budget)
        if examples_truncated:
            if kept_examples:
                result["semantics"]["examples"] = kept_examples
            else:
                result["semantics"].pop("examples", None)
            result["examples_truncated"] = True
        body_size = len(json.dumps(result, default=str))

    description = result.get("semantics", {}).get("description")
    if body_size + slack > max_bytes and description:
        overshoot = body_size + slack - max_bytes
        kept = max(0, len(description) - overshoot)
        result["semantics"]["description"] = description[:kept]
        result["description_truncated"] = True
        body_size = len(json.dumps(result, default=str))

    if symbol.kind == SymbolKind.CLASS:
        member_ids = sorted(index.class_members.get(symbol_id, []))
        members = [
            {
                "id": f"{display_id}#{mid.split('#', 1)[1]}",
                "kind": index.symbols_by_id[mid].kind.value,
                "summary": index.symbols_by_id[mid].semantics.summary,
            }
            for mid in member_ids
        ]
        member_budget = max(0, max_bytes - body_size - slack)
        members, truncated = _fit_list(members, member_budget)
        result["members"] = members
        if truncated:
            result["members_truncated"] = True
            result["members_hint"] = (
                "Member list truncated. Use search('<member name>', "
                f"module='{symbol.module}') or get_symbol on "
                f"'{display_id}#<member>' for the rest."
            )
    return result


def _get_symbols(
    index: LCPIndex,
    ids: list[str],
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Batch symbol lookup with per-response byte cap (spec D4/D6).

    Args:
        index: The library index to read from.
        ids: Symbol ids, returned in request order.
        max_bytes: Byte budget for the symbols list.

    Returns:
        ``{"symbols": [...], "not_found": [...]}``; adds ``truncated``,
        ``not_returned`` and ``hint`` when the byte cap cut the batch short.
    """
    details: list[dict[str, Any]] = []
    not_found: list[str] = []
    for requested in ids:
        canonical, symbol = index.resolve_id(requested)
        if symbol is None:
            not_found.append(requested)
        else:
            details.append(
                _symbol_detail(
                    index, canonical, symbol, max_bytes, requested_id=requested
                )
            )

    kept, truncated = _fit_list(details, max_bytes)
    if not kept and details:
        # Every detail entry fits max_bytes by construction; never let the
        # outer cap make a requested symbol unfetchable.
        kept, truncated = details[:1], len(details) > 1
    result: dict[str, Any] = {"symbols": kept, "not_found": not_found}
    hints: list[str] = []
    if not_found:
        hints.append(
            "Some ids were not found — take ids from search() results; the "
            "format is 'module:name' or 'module:Class#member'."
        )
    if truncated:
        result["truncated"] = True
        result["not_returned"] = [d["id"] for d in details[len(kept):]]
        hints.append(
            "Response byte cap reached; call get_symbol again with the "
            "ids in not_returned."
        )
    if hints:
        result["hint"] = " ".join(hints)
    return result


def _overview(
    index: LCPIndex,
    source: str | None = None,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Build the get_overview payload: identity + module tree (spec D4).

    Args:
        index: The library index to summarize.
        source: Resolution source recorded for the library, if known.
        max_bytes: Byte budget for the modules list.

    Returns:
        ``{"library": {...}, "modules": [...], "total_symbols": N}``.
    """
    manifest = index.doc.manifest
    library: dict[str, Any] = {
        "name": manifest.library.name,
        "version": manifest.library.version,
        "language": manifest.library.language,
        "schema_version": manifest.schema_version,
    }
    if source:
        library["source"] = source
    if manifest.compatibility:
        library["compatibility"] = manifest.compatibility.model_dump(
            exclude_none=True
        )

    modules = [
        {"module": module, "symbols": len(index.symbols_by_module[module])}
        for module in sorted(index.modules)
    ]
    modules, truncated = _fit_list(modules, max_bytes)
    result: dict[str, Any] = {
        "library": library,
        "modules": modules,
        "total_symbols": len(index.symbols_by_id),
    }
    if truncated:
        result["truncated"] = True
        result["hint"] = (
            "Module list truncated to fit the response cap; search('<name>') "
            "still finds symbols in any module, or raise --max-response-bytes."
        )
    return result


# ---------------------------------------------------------------------------
# Universal multi-library server
# ---------------------------------------------------------------------------


SERVER_INSTRUCTIONS = """\
MANDATORY: verify EVERY third-party Python library API through this server
BEFORE writing the first import or call that uses it — including libraries
you are sure you know. Your training data about library APIs is stale;
this server introspects the installed package, so it is the ground truth.
Confidently-written, plausible-looking API calls that do not exist are the
#1 failure mode this server exists to prevent — you cannot tell which of
your memories are wrong, so verify all of them. It costs 3 quick calls:

1. resolve_library(name)          — load the library (cache / scan / registry)
2. search(query, library=...)     — find symbols; empty query browses a module
3. get_symbol(ids=[...])          — exact signatures, parameters, and the
                                    correct import line; classes include all
                                    members inline

Do this even for a library whose API you would bet on: names and signatures
change between versions (e.g. renamed methods, moved classes, new required
arguments), and the installed version is what your code must run against.

get_overview(library=...) shows the module tree if you need orientation first.
Errors come back as {"error": {"code", "message", "hint", ...}} — follow the
hint to recover (e.g. pass library=<name> when several libraries are loaded).
"""


@dataclass
class LCPServer:
    """A configured LCP MCP server plus direct access to its internals.

    Attributes:
        mcp: The underlying FastMCP server (use :meth:`run` to serve stdio).
        index: The registry of loaded library indexes.
        tools: Raw tool callables by name, for in-process invocation
            (tests, preload) without the MCP protocol.
    """

    mcp: FastMCP
    index: MultiLibraryIndex
    tools: dict[str, Callable[..., Any]]

    def run(self) -> None:
        """Run the MCP server on stdio transport (blocks)."""
        self.mcp.run()


def _register_tools(
    mcp: FastMCP,
    libraries: MultiLibraryIndex,
    *,
    cache_dir: Path,
    no_cache: bool = False,
    registry_url: str | None = None,
    allow: set[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    scan_mode: str = "subprocess",
    scan_python: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> dict[str, Callable[..., Any]]:
    """Register the four V2 tools on *mcp* against *libraries* (spec D1).

    This is the single registration path shared by ``lcp serve-all`` and the
    deprecated ``lcp serve`` — the index registry (*libraries*) and the
    *allow* list are the only things that vary between them.

    Args:
        mcp: FastMCP server to register tools on.
        libraries: Index registry the tools read from and resolve into.
        cache_dir: Manifest cache root for resolve_library.
        no_cache: Disable cache read/write in resolve_library.
        registry_url: Optional registry fallback URL for resolve_library.
        allow: Optional allow-list of resolvable package names (None = all).
        max_response_bytes: Byte budget applied to list-returning payloads.
        scan_mode: Live-scan strategy for resolve_library: ``"subprocess"``
            (default) or ``"inprocess"``.
        scan_python: Interpreter whose environment live scans read
            (default: the interpreter running the server).
        scan_timeout: Seconds before a subprocess scan is killed.

    Returns:
        Dict of tool name → raw callable for in-process invocation.
    """

    def resolve_library(name: str, version: str | None = None) -> dict[str, Any]:
        """Load a Python library's ground-truth API docs. Call this for EVERY
        third-party library you are about to use — even ones you think you
        know well. Training data is stale; a plausible-looking guessed API is
        the #1 source of broken code, and verifying costs 3 quick calls.

        Resolution order: local cache → live scan of the installed package →
        registry fetch. Then use search() to find symbols and get_symbol()
        to verify exact signatures before writing code.

        Args:
            name: pip package name (e.g. "requests", "fastmcp").
            version: Optional exact version to prefer from cache/registry; a
                mismatch with what gets resolved is flagged, not fatal.

        Returns:
            {"status": "loaded", name, version, symbol_count, module_count,
            source, next_step} or {"error": {code, message, hint, ...}}.
            When the cache/registry serves a version that differs from the
            locally installed one (or the package is not installed at all),
            the result also carries "version_mismatch": true plus
            "installed_version" and "resolved_version".
        """
        if allow is not None and name not in allow:
            return _error(
                "library_not_exposed",
                f"Library '{name}' is not exposed by this server.",
                hint="Ask for one of the exposed libraries instead.",
                exposed=sorted(allow),
            )
        if name in libraries and libraries.source(name) == "manifest":
            # Manifest-pinned libraries (deprecated `lcp serve`) are the
            # ground truth for this server — never re-resolve over them.
            index = libraries.get(name)
            lib = index.doc.manifest.library
            return {
                "status": "loaded",
                "name": name,
                "version": lib.version,
                "language": lib.language,
                "symbol_count": len(index.symbols_by_id),
                "module_count": len(index.modules),
                "source": "manifest",
                "next_step": (
                    f"search(<what you need>, library='{name}') to find "
                    "symbols, then get_symbol(ids=[...]) to verify signatures."
                ),
            }
        try:
            doc, source = resolve_library_document(
                name,
                cache_dir=cache_dir,
                no_cache=no_cache,
                registry_url=registry_url,
                version=version,
                scan_mode=scan_mode,
                scan_python=scan_python,
                scan_timeout=scan_timeout,
            )
        except ImportError as exc:
            return _error(
                "resolve_failed",
                str(exc),
                hint=(
                    "Check the package name (pip distribution vs import "
                    "path) and that it is installed in this environment."
                ),
            )

        index = LCPIndex(doc)
        libraries.add(name, index, source=source)
        lib = doc.manifest.library
        # Report the registration key: it is what library= accepts.
        result: dict[str, Any] = {
            "status": "loaded",
            "name": name,
            "version": lib.version,
            "language": lib.language,
            "symbol_count": len(index.symbols_by_id),
            "module_count": len(index.modules),
            "source": source,
            "next_step": (
                f"search(<what you need>, library='{name}') to find symbols, "
                "then get_symbol(ids=[...]) to verify signatures."
            ),
        }
        if lib.name != name:
            result["manifest_name"] = lib.name
        if source in ("cache", "registry"):
            installed = _installed_version(name)
            if installed != lib.version:
                # Honesty flag: the served docs describe a version that is
                # not (or cannot be confirmed to be) the installed one.
                result["version_mismatch"] = True
                result["installed_version"] = installed
                result["resolved_version"] = lib.version
        if version and lib.version != version:
            result["warning"] = {
                "code": "version_mismatch",
                "requested": version,
                "resolved": lib.version,
                "message": (
                    f"Requested {name}=={version} but resolved "
                    f"{lib.version}; the docs describe {lib.version}."
                ),
            }
        return result

    def search(
        query: str,
        library: str | None = None,
        module: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find symbols in a loaded library, ranked by relevance. The primary
        discovery tool — one call replaces browsing module by module.

        Ranking: exact name > name prefix > name substring > summary >
        description. An EMPTY query browses: combine with module= and/or
        kind= to list contents in deterministic (kind, name) order.

        Args:
            query: Case-insensitive text to match; "" to browse.
            library: Library name — required when several libraries are loaded.
            module: Restrict to one module path (e.g. "requests.sessions").
            kind: Restrict to one kind: function, class, method, attribute,
                module, constant.
            limit: Max results (default 20, max 100).

        Returns:
            {"results": [{id, kind, summary, import}], "total", "truncated"}.
            "import" is the exact import line. Follow up with
            get_symbol(ids=[...]) before writing code.
        """
        _, index, err = libraries.resolve(library)
        if err is not None:
            return err
        return _search_index(
            index, query, module=module, kind=kind, limit=limit,
            max_bytes=max_response_bytes,
        )

    def get_symbol(
        ids: list[str], library: str | None = None
    ) -> dict[str, Any]:
        """Get full, verified details for one or more symbols in one call:
        exact signature, parameters, return type, and the correct import
        line. ALWAYS call this before writing a call site — never guess
        parameter names or defaults.

        Classes inline all members as one-line summaries, so one call usually
        answers "what can this object do"; fetch a member id (Class#member)
        for its full signature. usage_hints.returns_classes links a return
        type to its class id — verify methods on returned objects instead of
        inventing them. Re-exported symbols resolve under both their
        canonical id and their documented import path (aliases); alias
        answers carry resolved_via_alias.

        Args:
            ids: Symbol ids from search results, e.g.
                ["requests.api:get", "pathlib:Path#resolve"]. Batch related
                ids in ONE call.
            library: Library name — required when several libraries are loaded.

        Returns:
            {"symbols": [...], "not_found": [...]} plus truncated/
            not_returned when the response hits the size cap.
        """
        _, index, err = libraries.resolve(library)
        if err is not None:
            return err
        return _get_symbols(index, ids, max_bytes=max_response_bytes)

    def get_overview(library: str | None = None) -> dict[str, Any]:
        """Get a library's identity and module tree with per-module symbol
        counts. Use for orientation when you don't yet know what to search
        for; use search("", module=...) to browse a specific module.

        Args:
            library: Library name — required when several libraries are loaded.

        Returns:
            {"library": {name, version, language, source}, "modules":
            [{module, symbols}], "total_symbols"}.
        """
        name, index, err = libraries.resolve(library)
        if err is not None:
            return err
        return _overview(
            index, source=libraries.source(name), max_bytes=max_response_bytes
        )

    tools: dict[str, Callable[..., Any]] = {
        "resolve_library": resolve_library,
        "search": search,
        "get_symbol": get_symbol,
        "get_overview": get_overview,
    }
    for fn in tools.values():
        mcp.tool()(fn)
    return tools


def create_universal_server(
    name: str = "lcp-universal",
    cache_dir: Path | str | None = None,
    no_cache: bool = False,
    registry_url: str | None = None,
    expose: list[str] | None = None,
    preload: list[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    scan_mode: str = "subprocess",
    scan_python: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> LCPServer:
    """Create a universal MCP server that resolves any installed Python library.

    The server exposes exactly four tools — ``resolve_library``, ``search``,
    ``get_symbol``, ``get_overview`` — and carries adoption-focused
    ``instructions`` so agents verify APIs before writing code.

    Args:
        name: Server name shown to MCP clients.
        cache_dir: Root directory for cached manifests (default ~/.lcp/cache/).
        no_cache: Disable reading from and writing to the cache.
        registry_url: Optional LCP registry URL used when local scanning fails.
        expose: Optional allow-list of package names resolve_library may load.
        preload: Package names to resolve eagerly at startup.
        max_response_bytes: Byte budget for list-returning tool responses.
        scan_mode: Live-scan strategy: ``"subprocess"`` (default) isolates
            package imports in a child process; ``"inprocess"`` imports into
            the server process.
        scan_python: Interpreter whose environment live scans read
            (default: the interpreter running the server).
        scan_timeout: Seconds before a subprocess scan is killed.

    Returns:
        An :class:`LCPServer` bundling the FastMCP instance, the library
        index, and the raw tool callables.
    """
    resolved_cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    libraries = MultiLibraryIndex()
    mcp = FastMCP(name, instructions=SERVER_INSTRUCTIONS)
    # An expose list that is non-empty but blank after stripping must fail
    # closed (block everything), not fall back to allow-all.
    allow: set[str] | None = None
    if expose:
        allow = {n.strip() for n in expose if n.strip()}

    tools = _register_tools(
        mcp,
        libraries,
        cache_dir=resolved_cache_dir,
        no_cache=no_cache,
        registry_url=registry_url,
        allow=allow,
        max_response_bytes=max_response_bytes,
        scan_mode=scan_mode,
        scan_python=scan_python,
        scan_timeout=scan_timeout,
    )

    for pkg in preload or []:
        try:
            result = tools["resolve_library"](pkg)
            if "error" in result:
                raise RuntimeError(result["error"]["message"])
        except Exception as exc:
            print(
                f"Warning: failed to preload package '{pkg}': {exc}",
                file=sys.stderr,
            )

    return LCPServer(mcp=mcp, index=libraries, tools=tools)


def create_server(
    manifest_path: str | Path,
    name: str | None = None,
) -> LCPServer:
    """Create an MCP server pre-loaded with one LCP manifest.

    .. deprecated::
        ``lcp serve`` / ``create_server`` are deprecated; use
        ``lcp serve-all --expose <package>`` / :func:`create_universal_server`.
        This wrapper builds the same universal server with the manifest
        pre-loaded and resolution locked to its library.

    Args:
        manifest_path: Path to the ``.lcp.json`` file.
        name: Server name (default: ``lcp-{library-name}``).

    Returns:
        Configured :class:`LCPServer` instance.
    """
    warnings.warn(
        "create_server()/'lcp serve' are deprecated; use "
        "create_universal_server()/'lcp serve-all --expose <package>'.",
        DeprecationWarning,
        stacklevel=2,
    )
    doc = load_lcp_document(manifest_path)
    lib_name = doc.manifest.library.name
    server = create_universal_server(
        name=name or f"lcp-{lib_name}", expose=[lib_name]
    )
    server.index.add(lib_name, LCPIndex(doc), source="manifest")
    return server


def run_server(manifest_path: str | Path, name: str | None = None) -> None:
    """Create and run a (deprecated) single-manifest MCP server.

    Args:
        manifest_path: Path to the ``.lcp.json`` file.
        name: Server name (default: ``lcp-{library-name}``).
    """
    create_server(manifest_path, name=name).run()


def run_universal_server(
    name: str = "lcp-universal",
    cache_dir: Path | str | None = None,
    no_cache: bool = False,
    registry_url: str | None = None,
    expose: list[str] | None = None,
    preload: list[str] | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    scan_mode: str = "subprocess",
    scan_python: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> None:
    """Create and run a universal MCP server that resolves any installed Python library.

    Args:
        name: Server name (default: lcp-universal).
        cache_dir: Root directory for cached manifests (default: ~/.lcp/cache/).
        no_cache: Disable reading from and writing to the cache.
        registry_url: Optional base URL of an LCP registry used as a fallback
            when local scanning fails.
        expose: Optional allow-list of package names for ``resolve_library``.
            When ``None`` or empty, all packages are allowed.
        preload: Package names to resolve eagerly at startup.
        max_response_bytes: Byte budget for list-returning tool responses.
        scan_mode: Live-scan strategy: ``"subprocess"`` (default) or
            ``"inprocess"``.
        scan_python: Interpreter whose environment live scans read
            (default: the interpreter running the server).
        scan_timeout: Seconds before a subprocess scan is killed.
    """
    server = create_universal_server(
        name=name,
        cache_dir=cache_dir,
        no_cache=no_cache,
        registry_url=registry_url,
        expose=expose,
        preload=preload,
        max_response_bytes=max_response_bytes,
        scan_mode=scan_mode,
        scan_python=scan_python,
        scan_timeout=scan_timeout,
    )
    server.run()
