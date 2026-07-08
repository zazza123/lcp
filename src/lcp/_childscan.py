"""Isolated child entry point for cross-environment subprocess scans.

Loaded **by file path** in the target interpreter (never imported as
``lcp._childscan``), so it must stay stdlib-only and must not import the
``lcp`` package or ``pydantic``. It runs raw introspection via a ``scanner``
module handed in by the bootstrap and prints the ``ScannedModule`` tree as
JSON on stdout.

Mirrors the exit-code contract of :mod:`lcp.scanjson` (0 ok / 3 import failure
/ 4 scan failure) but emits the raw scanned tree, not an LCP document —
generation runs host-side, so the child never needs ``pydantic``.
"""

from __future__ import annotations

import argparse
import json
import sys


def _fail(code: int, err_type: str, message: str) -> None:
    """Emit the structured stderr error object and exit with *code*."""
    print(json.dumps({"type": err_type, "message": message}), file=sys.stderr)
    sys.exit(code)


def main(scanner, argv: list[str] | None = None) -> None:
    """Scan a package and write its raw ``ScannedModule`` JSON to stdout.

    Args:
        scanner: The self-contained ``lcp.scanner`` module (loaded by path),
            exposing ``scan_package`` and ``scanned_to_dict``.
        argv: Arguments (default ``sys.argv[1:]``): the package name plus
            optional ``--include-private`` / ``--no-recursive`` /
            ``--include-tests`` flags.
    """
    parser = argparse.ArgumentParser(prog="lcp-childscan")
    parser.add_argument("package")
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--include-tests", action="store_true")
    args = parser.parse_args(argv)

    # Import-time prints from the scanned package must not corrupt the stdout
    # protocol: park stdout on stderr while scanning, restore it at the end.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        try:
            scanned = scanner.scan_package(
                args.package,
                include_private=args.include_private,
                recursive=not args.no_recursive,
                include_tests=args.include_tests,
            )
        except ImportError as exc:
            _fail(3, "import_failure", str(exc))
        except (SystemExit, KeyboardInterrupt, Exception) as exc:
            _fail(
                4,
                "scan_failure",
                f"{type(exc).__name__} raised while importing "
                f"'{args.package}': {exc}",
            )
        try:
            payload = json.dumps(scanner.scanned_to_dict(scanned))
        except Exception as exc:
            _fail(4, "scan_failure", f"{type(exc).__name__}: {exc}")
    finally:
        sys.stdout = real_stdout

    print(payload)
