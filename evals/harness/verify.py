"""Verify symbol usage against the live (pinned) environment via introspection."""

import importlib


def resolve_dotted(path: str) -> bool:
    """Return True if a dotted path like 'polars.DataFrame.group_by' resolves.

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
            return False
        return True
    return False


def resolve_symbol(symbol_id: str) -> bool:
    """Return True if an LCP symbol id resolves.

    Formats: 'module:entity' (e.g. 'json:loads') and 'module:Class#method'
    (e.g. 'pathlib:Path#resolve'). A bare 'module' (no colon) is also accepted.
    """
    module, _, entity = symbol_id.partition(":")
    if not entity:
        return resolve_dotted(module)
    return resolve_dotted(f"{module}.{entity.replace('#', '.')}")
