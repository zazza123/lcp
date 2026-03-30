"""Diff module for comparing two LCP documents and detecting deprecated symbols."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .models import Deprecation, LCPDocument, Symbol


@dataclass
class SymbolDiff:
    """Description of a single symbol difference between two LCP documents."""

    symbol_id: str
    kind: str
    module: str | None = None
    summary: str | None = None


@dataclass
class DiffResult:
    """Result of comparing two LCP documents.

    Attributes:
        old_version: Version string of the old library.
        new_version: Version string of the new library.
        library_name: Name of the library.
        removed: Symbols present in old but absent in new (potential deprecations).
        added: Symbols present in new but absent in old.
        deprecated: Deprecation entries for removed symbols, keyed by symbol ID.
    """

    old_version: str
    new_version: str
    library_name: str
    removed: list[SymbolDiff] = field(default_factory=list)
    added: list[SymbolDiff] = field(default_factory=list)
    deprecated: dict[str, Deprecation] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        return {
            "library": self.library_name,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "summary": {
                "removed": len(self.removed),
                "added": len(self.added),
            },
            "removed": [
                {
                    "symbol_id": s.symbol_id,
                    "kind": s.kind,
                    "module": s.module,
                    "summary": s.summary,
                }
                for s in self.removed
            ],
            "added": [
                {
                    "symbol_id": s.symbol_id,
                    "kind": s.kind,
                    "module": s.module,
                    "summary": s.summary,
                }
                for s in self.added
            ],
            "deprecations": {
                sid: dep.model_dump(mode="json", exclude_none=True)
                for sid, dep in self.deprecated.items()
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def _symbol_diff_from(symbol_id: str, symbol: Symbol) -> SymbolDiff:
    """Create a SymbolDiff from a Symbol."""
    return SymbolDiff(
        symbol_id=symbol_id,
        kind=symbol.kind.value,
        module=symbol.module,
        summary=symbol.semantics.summary if symbol.semantics else None,
    )


def diff_documents(old: LCPDocument, new: LCPDocument) -> DiffResult:
    """Compare two LCP documents and detect differences.

    Symbols present in *old* but missing from *new* are treated as removed
    (deprecated).  For each removed symbol a ``Deprecation`` entry is
    created with ``deprecated_in`` set to the *new* document's version.

    Args:
        old: The earlier LCP document.
        new: The later LCP document.

    Returns:
        A DiffResult containing removed and added symbols together with
        generated deprecation entries.
    """
    old_ids = set(old.symbols.keys())
    new_ids = set(new.symbols.keys())

    removed_ids = sorted(old_ids - new_ids)
    added_ids = sorted(new_ids - old_ids)

    new_version = new.manifest.library.version
    library_name = new.manifest.library.name

    removed = [_symbol_diff_from(sid, old.symbols[sid]) for sid in removed_ids]
    added = [_symbol_diff_from(sid, new.symbols[sid]) for sid in added_ids]

    # Build deprecation entries for removed symbols
    deprecated: dict[str, Deprecation] = {}
    for sid in removed_ids:
        deprecated[sid] = Deprecation(deprecated_in=new_version)

    return DiffResult(
        old_version=old.manifest.library.version,
        new_version=new_version,
        library_name=library_name,
        removed=removed,
        added=added,
        deprecated=deprecated,
    )


def update_document(document: LCPDocument, diff_result: DiffResult) -> LCPDocument:
    """Return a copy of *document* with deprecation entries from *diff_result* merged in.

    Existing deprecation entries in the document are preserved.  New entries
    from the diff result are added for symbols that were removed between
    versions.

    Args:
        document: The LCP document to update (typically the *new* version).
        diff_result: The result of :func:`diff_documents`.

    Returns:
        A new LCPDocument with merged deprecation entries.
    """
    existing = dict(document.deprecations) if document.deprecations else {}
    merged = {**existing, **{
        sid: dep for sid, dep in diff_result.deprecated.items()
        if sid not in existing
    }}

    return document.model_copy(update={
        "deprecations": merged if merged else None,
    })


def load_lcp_document(path: str) -> LCPDocument:
    """Load an LCP document from a JSON file.

    Args:
        path: File path to an LCP JSON file.

    Returns:
        A parsed LCPDocument.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        pydantic.ValidationError: If the JSON does not match the LCP schema.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return LCPDocument.model_validate(data)
