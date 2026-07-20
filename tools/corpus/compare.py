#!/usr/bin/env python3
"""Diff two corpus snapshots into a report ordered by likely significance.

Sections are printed removals first, then kind changes, then additions.
That ordering is the whole point: a scanner change that removes symbols is
almost always a regression, while additions usually need reading rather
than alarm. In #61 a regression appeared as removals and a mislabelling
risk appeared as additions of one specific object type.

This tool never fails a build. It always exits 0 unless it could not read
its inputs.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _object_type(summary: str | None) -> str | None:
    """Extract the object type a constant's summary leads with.

    ``"ufunc constant."`` and ``"int constant: 100"`` both yield their first
    word. Returns ``None`` for anything that is not shaped that way, so a
    function or class summary is not mistaken for a type name.
    """
    if not summary:
        return None
    first, _, rest = summary.partition(" ")
    if rest.startswith("constant"):
        return first
    return None


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshot documents.

    A library that is missing from one side, or that failed to scan on
    either side, is reported under ``coverage`` and contributes no symbol
    deltas at all. Conflating a crashed scan with a total loss of symbols
    is the fastest way to read a crash as a regression.

    Args:
        before: Snapshot taken before the change.
        after: Snapshot taken after the change.

    Returns:
        A dict with ``removed``, ``kind_changed``, ``added`` and ``coverage``.
    """
    before_libs = before.get("libraries", {})
    after_libs = after.get("libraries", {})

    removed: list[dict[str, Any]] = []
    kind_changed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    coverage: list[dict[str, str]] = []

    for library in sorted(set(before_libs) | set(after_libs)):
        b = before_libs.get(library)
        a = after_libs.get(library)

        if b is None:
            coverage.append({"library": library, "state": "only_in_after"})
            continue
        if a is None:
            coverage.append({"library": library, "state": "only_in_before"})
            continue
        if "error" in b and "error" in a:
            coverage.append({"library": library, "state": "failed_in_both"})
            continue
        if "error" in a:
            coverage.append({"library": library, "state": "failed_in_after"})
            continue
        if "error" in b:
            coverage.append({"library": library, "state": "failed_in_before"})
            continue

        b_syms = b.get("symbols", {})
        a_syms = a.get("symbols", {})

        for symbol_id in sorted(set(b_syms) - set(a_syms)):
            removed.append(
                {"library": library, "id": symbol_id, "kind": b_syms[symbol_id]["kind"]}
            )
        for symbol_id in sorted(set(a_syms) - set(b_syms)):
            entry = a_syms[symbol_id]
            added.append(
                {
                    "library": library,
                    "id": symbol_id,
                    "kind": entry["kind"],
                    "type": _object_type(entry.get("summary")),
                }
            )
        for symbol_id in sorted(set(a_syms) & set(b_syms)):
            if b_syms[symbol_id]["kind"] != a_syms[symbol_id]["kind"]:
                kind_changed.append(
                    {
                        "library": library,
                        "id": symbol_id,
                        "before": b_syms[symbol_id]["kind"],
                        "after": a_syms[symbol_id]["kind"],
                    }
                )

    return {
        "removed": removed,
        "kind_changed": kind_changed,
        "added": added,
        "coverage": coverage,
    }


def render(diff: dict[str, Any]) -> str:
    """Render *diff* as a report, most suspicious section first."""
    lines: list[str] = []

    lines.append(f"REMOVED ({len(diff['removed'])})")
    for entry in diff["removed"]:
        lines.append(f"  {entry['library']:20} {entry['id']}  [{entry['kind']}]")
    lines.append("")

    lines.append(f"KIND CHANGED ({len(diff['kind_changed'])})")
    for entry in diff["kind_changed"]:
        lines.append(
            f"  {entry['library']:20} {entry['id']}  "
            f"{entry['before']} -> {entry['after']}"
        )
    lines.append("")

    lines.append(f"ADDED ({len(diff['added'])})")
    by_library: dict[str, Counter] = {}
    for entry in diff["added"]:
        label = entry["type"] or entry["kind"]
        by_library.setdefault(entry["library"], Counter())[label] += 1
    for library in sorted(by_library):
        breakdown = ", ".join(
            f"{label} x{count}"
            for label, count in sorted(
                by_library[library].items(), key=lambda kv: (-kv[1], kv[0])
            )
        )
        total = sum(by_library[library].values())
        lines.append(f"  {library:20} +{total:<6} {breakdown}")
    lines.append("")

    if diff["coverage"]:
        lines.append(f"COVERAGE DIFFERENCES ({len(diff['coverage'])})")
        for entry in diff["coverage"]:
            lines.append(f"  {entry['library']:20} {entry['state']}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. Always returns 0 on a successful comparison."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before", help="Snapshot taken before the change")
    parser.add_argument("after", help="Snapshot taken after the change")
    args = parser.parse_args(argv)

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))

    print(f"before: lcp {before['provenance']['lcp_sha']}  "
          f"after: lcp {after['provenance']['lcp_sha']}")
    print()
    print(render(diff_snapshots(before, after)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
