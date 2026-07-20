#!/usr/bin/env python3
"""Snapshot every corpus library's manifest through a given lcp checkout.

This is a measurement tool, not a test. It never fails a build: a library
that cannot be imported or scanned is recorded as an error and the run
continues, because one broken library must not hide the other twenty-four.

lcp is deliberately NOT installed into the corpus venv. Pointing ``--src``
at any checkout's ``src`` directory is what lets the same tool measure two
different versions of the scanner without reinstalling anything.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

TIERS = ("core", "full")


def read_libraries(path: Path, tier: str) -> list[tuple[str, str]]:
    """Read the corpus definition, keeping entries at or below *tier*.

    The file is tab-separated with three columns — tier, pip name, import
    name — because a distribution's name and its import path routinely
    differ (``attrs`` imports as ``attr``, ``pillow`` as ``PIL``). Blank
    lines and lines starting with ``#`` are ignored.

    Args:
        path: Path to ``libraries.txt``.
        tier: ``"core"`` for the light set, ``"full"`` for everything.

    Returns:
        ``(pip_name, import_name)`` pairs, in file order.

    Raises:
        ValueError: If a line has the wrong number of columns, a line has an
            unknown tier, or *tier* itself is not one of ``TIERS``.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")
    wanted = {"core"} if tier == "core" else {"core", "full"}
    entries: list[tuple[str, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ValueError(f"{path}:{lineno}: expected 3 columns, got {len(parts)}")
        entry_tier, pip_name, import_name = parts
        if entry_tier not in TIERS:
            raise ValueError(f"{path}:{lineno}: unknown tier {entry_tier!r}")
        if entry_tier in wanted:
            entries.append((pip_name, import_name))
    return entries


def _installed_version(pip_name: str) -> str | None:
    """Resolved version of *pip_name*, or ``None`` when it is not installed."""
    try:
        return importlib.metadata.version(pip_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _lcp_sha(src: str) -> str:
    """Short git SHA of the checkout that *src* belongs to.

    Returns ``"unknown"`` when the path is not inside a git work tree, so a
    snapshot taken from an exported tree still records something rather than
    crashing.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(src).parent), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def scan_one(import_name: str) -> dict[str, Any]:
    """Scan a single library into its snapshot entry.

    Args:
        import_name: Import path to scan, e.g. ``google.cloud.firestore``.

    Returns:
        ``{"symbols": {...}}`` on success, ``{"error": "..."}`` on any
        failure. Never raises: a corpus run must survive one bad library.
    """
    from lcp.generator import generate_lcp
    from lcp.scanner import scan_package

    try:
        document = generate_lcp(scan_package(import_name))
    except BaseException as exc:  # noqa: BLE001 - a scan may raise SystemExit
        return {"error": f"{type(exc).__name__}: {exc}"}

    symbols = {
        symbol_id: {
            "kind": symbol.kind.value,
            "module": symbol.module,
            "summary": symbol.semantics.summary,
        }
        for symbol_id, symbol in document.symbols.items()
    }
    return {"symbols": dict(sorted(symbols.items()))}


def build_snapshot(src: str, libraries_path: Path, tier: str) -> dict[str, Any]:
    """Build the full snapshot for *tier* using the lcp checkout at *src*.

    Every call re-resolves ``lcp`` (and thus ``lcp.scanner``/``lcp.generator``)
    against *src*, even if a previous call in the same process already
    imported ``lcp`` from a different checkout. Python only consults
    ``sys.path`` the first time a module is imported; once ``lcp.scanner`` is
    cached in ``sys.modules``, a later ``sys.path`` change is silently
    ignored by the import system. Without evicting the cache, a second call
    with a different *src* would keep measuring the first checkout while
    reporting the second one's provenance — a measurement tool's worst
    failure mode, since nothing raises or errors.

    The eviction is scoped to this call: whatever ``lcp``/``lcp.*`` entries
    (and ``sys.path`` state) existed on entry are restored again before
    returning, in a ``finally`` block that runs even if a scan raises. This
    keeps the swap invisible outside a single ``build_snapshot()`` call — a
    caller that also imports the real ``lcp`` package (as this project's own
    test suite does) is unaffected, since nothing observes the substitute
    modules except the scans running inside this function.

    Args:
        src: Path to a checkout's ``src`` directory. Prepended to ``sys.path``
            for the duration of this call only.
        libraries_path: Path to ``libraries.txt``.
        tier: ``"core"`` or ``"full"``.

    Returns:
        The snapshot document, ready to serialize.

    Raises:
        ValueError: If *tier* is not one of ``TIERS``.
    """
    src = str(Path(src).resolve())

    inserted_path = src not in sys.path
    if inserted_path:
        sys.path.insert(0, src)

    saved_modules = {
        name: sys.modules[name]
        for name in sys.modules
        if name == "lcp" or name.startswith("lcp.")
    }
    for name in saved_modules:
        del sys.modules[name]

    try:
        entries = read_libraries(Path(libraries_path), tier)
        libraries: dict[str, Any] = {}
        versions: dict[str, str] = {}

        for pip_name, import_name in entries:
            version = _installed_version(pip_name)
            if version is not None:
                versions[pip_name] = version
            libraries[pip_name] = scan_one(import_name)

        return {
            "provenance": {
                "lcp_sha": _lcp_sha(src),
                "python": platform.python_version(),
                "tier": tier,
                "versions": dict(sorted(versions.items())),
            },
            "libraries": dict(sorted(libraries.items())),
        }
    finally:
        for name in [n for n in sys.modules if n == "lcp" or n.startswith("lcp.")]:
            del sys.modules[name]
        sys.modules.update(saved_modules)
        if inserted_path:
            sys.path.remove(src)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True, help="Path to a checkout's src/ directory")
    parser.add_argument("-o", "--output", required=True, help="Snapshot JSON to write")
    parser.add_argument("--tier", choices=TIERS, default="core")
    parser.add_argument("--libraries", default=str(here / "libraries.txt"))
    args = parser.parse_args(argv)

    snapshot = build_snapshot(args.src, Path(args.libraries), args.tier)

    Path(args.output).write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    scanned = sum(1 for e in snapshot["libraries"].values() if "symbols" in e)
    failed = len(snapshot["libraries"]) - scanned
    total = sum(len(e["symbols"]) for e in snapshot["libraries"].values() if "symbols" in e)
    print(
        f"{scanned} libraries scanned, {failed} failed, {total} symbols "
        f"-> {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
