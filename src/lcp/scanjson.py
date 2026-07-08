"""Machine-mode scan entry point: ``python -m lcp.scanjson <package>``.

Runs inside the *scan interpreter* — possibly a different venv from the MCP
server — and speaks the public LCP document format on stdout, so there is no
private IPC format to version. Errors are a single JSON object
``{"type": ..., "message": ...}`` on stderr plus a distinguishing exit code.

Exit codes:
    0: success — the LCP JSON document is on stdout.
    3: import failure — the target package could not be imported.
    4: scan failure — the package imported but scanning or generation failed,
       including ``SystemExit`` raised by import-time code.

Deliberately imports only the stdlib until arguments are parsed, and never
imports ``click``: the scan environment only needs ``lcp`` and ``pydantic``
importable (the MCP server appends its own paths to the child's ``sys.path``
for exactly that — see :mod:`lcp.subprocess_scan`).
"""

from __future__ import annotations

import argparse
import json
import sys


def _fail(code: int, err_type: str, message: str) -> None:
    """Emit the structured stderr error and exit with *code*.

    Args:
        code: Process exit code (3 = import failure, 4 = scan failure).
        err_type: Machine-readable error type for the stderr JSON object.
        message: Human/agent-readable description of what went wrong.
    """
    print(json.dumps({"type": err_type, "message": message}), file=sys.stderr)
    sys.exit(code)


def main(argv: list[str] | None = None) -> None:
    """Scan a package and write its LCP document to stdout.

    Args:
        argv: Argument list (default: ``sys.argv[1:]``): the package name plus
            optional ``--include-private`` / ``--no-recursive`` /
            ``--include-tests`` flags.
    """
    parser = argparse.ArgumentParser(
        prog="python -m lcp.scanjson",
        description="Scan an installed package and write its LCP document to stdout.",
    )
    parser.add_argument("package", help="Import path of the package to scan.")
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--include-tests", action="store_true")
    args = parser.parse_args(argv)

    # Import-time prints from the scanned package must not corrupt the
    # stdout protocol: park stdout on stderr while scanning, write the
    # document to the real stdout at the very end.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        from .generator import generate_lcp
        from .scanner import scan_package

        try:
            scanned = scan_package(
                args.package,
                include_private=args.include_private,
                recursive=not args.no_recursive,
                include_tests=args.include_tests,
            )
        except ImportError as exc:
            _fail(3, "import_failure", str(exc))
        except (SystemExit, KeyboardInterrupt, Exception) as exc:
            # Import-time code can raise SystemExit (or anything else);
            # convert it into the exit-code contract instead of dying with it.
            _fail(
                4,
                "scan_failure",
                f"{type(exc).__name__} raised while importing "
                f"'{args.package}': {exc}",
            )
        try:
            payload = generate_lcp(scanned).to_json(indent=2)
        except Exception as exc:
            _fail(4, "scan_failure", f"{type(exc).__name__}: {exc}")
    finally:
        sys.stdout = real_stdout

    print(payload)


if __name__ == "__main__":
    main()
