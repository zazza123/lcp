#!/usr/bin/env python3
"""Diff two corpus snapshots into a report ordered by likely significance.

Sections are printed removals first, then kind changes, then module
changes, then summary changes, then additions. That ordering is the whole
point: a scanner change that removes symbols is almost always a
regression, while additions usually need reading rather than alarm. In
#61 a regression appeared as removals and a mislabelling risk appeared as
additions of one specific object type. Module and summary changes sit
between kind changes and additions because a silent attribution or
docstring-extraction regression is more suspicious than a new symbol but
less than a recategorisation or a removal.

A PROVENANCE DIFFERENCES banner, when the two snapshots' library or Python
versions differ, prints above the whole report — that drift is often the
real explanation for a diff and needs to be seen first.

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

    Every symbol present on both sides is checked for all three recorded
    fields — ``kind``, ``module`` and ``summary`` — independently. A symbol
    whose kind *and* summary both changed appears in both ``kind_changed``
    and ``summary_changed``; the checks are not exclusive of one another,
    because a change to the docstring extractor and a change to kind
    classification are different bugs even when they land on the same
    symbol in the same run.

    Args:
        before: Snapshot taken before the change.
        after: Snapshot taken after the change.

    Returns:
        A dict with ``removed``, ``kind_changed``, ``module_changed``,
        ``summary_changed``, ``added`` and ``coverage``.
    """
    before_libs = before.get("libraries", {})
    after_libs = after.get("libraries", {})

    removed: list[dict[str, Any]] = []
    kind_changed: list[dict[str, Any]] = []
    module_changed: list[dict[str, Any]] = []
    summary_changed: list[dict[str, Any]] = []
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
            b_entry = b_syms[symbol_id]
            a_entry = a_syms[symbol_id]
            if b_entry["kind"] != a_entry["kind"]:
                kind_changed.append(
                    {
                        "library": library,
                        "id": symbol_id,
                        "before": b_entry["kind"],
                        "after": a_entry["kind"],
                    }
                )
            if b_entry.get("module") != a_entry.get("module"):
                module_changed.append(
                    {
                        "library": library,
                        "id": symbol_id,
                        "before": b_entry.get("module"),
                        "after": a_entry.get("module"),
                    }
                )
            if b_entry.get("summary") != a_entry.get("summary"):
                summary_changed.append(
                    {
                        "library": library,
                        "id": symbol_id,
                        "before": b_entry.get("summary"),
                        "after": a_entry.get("summary"),
                    }
                )

    return {
        "removed": removed,
        "kind_changed": kind_changed,
        "module_changed": module_changed,
        "summary_changed": summary_changed,
        "added": added,
        "coverage": coverage,
    }


def _render_changed_field(label: str, entries: list[dict[str, Any]]) -> list[str]:
    """Render a per-symbol-field change list as a per-library summary.

    Full listings of every changed symbol would be unreadable at corpus
    scale (tens of thousands of symbols in the full tier), so this groups
    by library and shows a count plus up to three sample symbol ids —
    enough to spot-check without printing every line.
    """
    lines = [f"{label} ({len(entries)})"]
    by_library: dict[str, list[str]] = {}
    for entry in entries:
        by_library.setdefault(entry["library"], []).append(entry["id"])
    for library in sorted(by_library):
        ids = by_library[library]
        sample = ", ".join(ids[:3])
        if len(ids) > 3:
            sample += ", ..."
        lines.append(f"  {library:20} +{len(ids):<6} {sample}")
    lines.append("")
    return lines


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

    lines.extend(_render_changed_field("MODULE CHANGED", diff["module_changed"]))
    lines.extend(_render_changed_field("SUMMARY CHANGED", diff["summary_changed"]))

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


def diff_provenance(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare the provenance blocks of two snapshots.

    ``provenance.versions`` and ``provenance.python`` exist so a version
    drift explanation is available when the corpus itself moved between the
    two snapshots — a library upgraded in between makes a symbol diff look
    like a scanner regression when it is really just a new release. This
    surfaces that drift explicitly instead of leaving it implicit in two
    JSON files nobody diffs by hand.

    Args:
        before: Snapshot taken before the change.
        after: Snapshot taken after the change.

    Returns:
        A list of ``{"item", "before", "after"}`` dicts, one per Python or
        library version that differs. Empty when provenance matches.
    """
    diffs: list[dict[str, Any]] = []

    b_prov = before.get("provenance", {})
    a_prov = after.get("provenance", {})

    if b_prov.get("python") != a_prov.get("python"):
        diffs.append({"item": "python", "before": b_prov.get("python"), "after": a_prov.get("python")})

    b_versions = b_prov.get("versions", {})
    a_versions = a_prov.get("versions", {})
    for name in sorted(set(b_versions) | set(a_versions)):
        b_version = b_versions.get(name)
        a_version = a_versions.get(name)
        if b_version != a_version:
            diffs.append({"item": name, "before": b_version, "after": a_version})

    return diffs


def render_provenance(diffs: list[dict[str, Any]]) -> str:
    """Render provenance drift as a banner, or an empty string when there is none."""
    if not diffs:
        return ""
    lines = [f"PROVENANCE DIFFERENCES ({len(diffs)})"]
    for entry in diffs:
        lines.append(f"  {entry['item']:20} {entry['before']} -> {entry['after']}")
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

    provenance_report = render_provenance(diff_provenance(before, after))
    if provenance_report:
        print(provenance_report)

    print(f"before: lcp {before['provenance']['lcp_sha']}  "
          f"after: lcp {after['provenance']['lcp_sha']}")
    print()
    print(render(diff_snapshots(before, after)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
