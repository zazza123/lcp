"""Verify symbol usage against the live (pinned) environment via introspection."""

import importlib
from dataclasses import dataclass, field

from harness import extract


_UNRESOLVED = object()


def _resolve_object(path: str):
    """Resolve a dotted path to the live object, or ``_UNRESOLVED``.

    Tries the longest importable module prefix, then getattr-walks the rest.
    Any exception during import or attribute access counts as unresolved.
    """
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except Exception:
            continue
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except Exception:
            return _UNRESOLVED
        return obj
    return _UNRESOLVED


def resolve_dotted(path: str) -> bool:
    """Return True if a dotted path like 'polars.DataFrame.group_by' resolves."""
    return _resolve_object(path) is not _UNRESOLVED


def resolve_symbol(symbol_id: str) -> bool:
    """Return True if an LCP symbol id resolves.

    Formats: 'module:entity' (e.g. 'json:loads') and 'module:Class#method'
    (e.g. 'pathlib:Path#resolve'). A bare 'module' (no colon) is also accepted.
    """
    module, _, entity = symbol_id.partition(":")
    if not entity:
        return resolve_dotted(module)
    return resolve_dotted(f"{module}.{entity.replace('#', '.')}")


def symbol_used(symbol_id: str, usage: "extract.CodeUsage") -> bool:
    """Return True if the generated code uses this symbol.

    'module:Class#method' matches by method name on any receiver (static
    analysis cannot type the receiver) or by full dotted path.
    'module:entity' matches the canonical dotted path, or ANY used dotted
    path that resolves to the same live object — so valid re-export
    aliases (e.g. ``from cyhole.jupiter import Jupiter`` for
    cyhole.jupiter.interaction:Jupiter) count as usage.
    """
    module, _, entity = symbol_id.partition(":")
    if "#" in entity:
        cls, _, method = entity.partition("#")
        if method in usage.method_names:
            return True
        canonical = f"{module}.{cls}.{method}"
    else:
        canonical = f"{module}.{entity}" if entity else module
    if canonical in usage.dotted_paths:
        return True
    target = _resolve_object(canonical)
    if target is _UNRESOLVED:
        return False
    return any(_resolve_object(p) is target for p in usage.dotted_paths)


@dataclass
class Verification:
    passed: bool
    misuse_count: int
    required_missing: list[str] = field(default_factory=list)
    forbidden_used: list[str] = field(default_factory=list)
    unresolved_usages: list[str] = field(default_factory=list)
    error: str | None = None


def verify_code(code: str | None, case) -> Verification:
    """Statically verify generated code against a case's checks.

    misuse_count = forbidden symbols used + library-rooted attribute chains
    that do not resolve via live introspection.
    """
    if not code:
        return Verification(
            passed=False, misuse_count=0,
            required_missing=list(case.required_symbols), error="no code block",
        )
    try:
        usage = extract.extract_usage(code, case.import_name)
    except SyntaxError as exc:
        return Verification(
            passed=False, misuse_count=0,
            required_missing=list(case.required_symbols),
            error=f"syntax error in generated code: {exc}",
        )
    required_missing = [s for s in case.required_symbols if not symbol_used(s, usage)]
    forbidden_used = [s for s in case.forbidden_symbols if symbol_used(s, usage)]
    unresolved = sorted(p for p in usage.dotted_paths if not resolve_dotted(p))
    return Verification(
        passed=not (required_missing or forbidden_used or unresolved),
        misuse_count=len(forbidden_used) + len(unresolved),
        required_missing=required_missing,
        forbidden_used=forbidden_used,
        unresolved_usages=unresolved,
    )
