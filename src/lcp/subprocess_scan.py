"""Run package scans in a separate interpreter.

The MCP server must not import arbitrary package code in-process: import-time
side effects can crash the server, heavy imports stall concurrent tool calls
(CPython import lock + GIL, even though FastMCP runs sync tools on worker
threads), and the server's environment is often not the project's environment.
This module launches an **isolated** child interpreter that runs only raw
introspection and parses the ``ScannedModule`` tree it writes to stdout as
JSON; the host then runs :func:`lcp.generator.generate_lcp` with its own
``pydantic`` to produce the LCP document.

The child is started as ``<python> -c <bootstrap> <package>``. The bootstrap
loads the self-contained ``scanner.py`` and the stdlib-only ``_childscan.py``
**by absolute file path** (so ``lcp/__init__.py`` — and thus ``pydantic`` and
``fastmcp`` — never runs in the child) and adds only *extra_paths* to the
child's ``sys.path``. The host ``site-packages`` is therefore never exposed:
target submodules cannot import host packages, and the target's
``pydantic_core`` cannot collide with the host's ``pydantic``. The target
interpreter needs neither ``lcp`` nor ``pydantic`` installed. The child
inherits the server's working directory; with ``-c``, that directory is also
on its ``sys.path``, mirroring in-process import behavior.

Residual trust model (documented, not solved here): the scanned package's
import-time code still executes — just in a disposable child process. Process
isolation contains crashes and hangs; it is not a sandbox.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .models import LCPDocument

DEFAULT_SCAN_TIMEOUT = 60.0
"""Seconds before a scan subprocess is killed (heavy imports can be slow)."""

_STDERR_TAIL_CHARS = 1000


class SubprocessScanError(Exception):
    """Base class for subprocess scan failures; messages are agent-facing."""


class ScanImportError(SubprocessScanError):
    """The target package is not importable in the scan environment (exit 3)."""


class ScanFailedError(SubprocessScanError):
    """The scan ran but failed: crash, invalid output, or unexpected exit."""


class ScanTimeoutError(SubprocessScanError):
    """The scan subprocess exceeded its timeout and was killed."""


class ScanInterpreterNotFoundError(SubprocessScanError):
    """The configured scan interpreter does not exist."""


class ScanSpawnError(SubprocessScanError):
    """The scan subprocess could not be started (process spawning restricted)."""


_PKG_DIR = Path(__file__).resolve().parent
_SCANNER_PATH = str(_PKG_DIR / "scanner.py")
_CHILDSCAN_PATH = str(_PKG_DIR / "_childscan.py")

# The child loads scanner.py and _childscan.py BY FILE PATH so lcp/__init__.py
# (and thus pydantic/fastmcp) never runs in the target interpreter, and only
# extra_paths are added to the child's sys.path — the host site-packages is
# never exposed. Generation runs host-side in scan_package_subprocess.
_CHILD_CODE_TEMPLATE = (
    "import sys, importlib.util as _u\n"
    "sys.path[:0] = {extra_paths!r}\n"
    "def _load(_n, _p):\n"
    "    _s = _u.spec_from_file_location(_n, _p)\n"
    "    _m = _u.module_from_spec(_s)\n"
    "    sys.modules[_n] = _m\n"  # register before exec so dataclass annotations resolve
    "    _s.loader.exec_module(_m)\n"
    "    return _m\n"
    "_scanner = _load('_lcp_scanner', {scanner_path!r})\n"
    "_child = _load('_lcp_childscan', {childscan_path!r})\n"
    "_child.main(_scanner, sys.argv[1:])\n"
)


def _build_child_code(extra_paths: Sequence[str]) -> str:
    """Build the ``-c`` bootstrap run by the target interpreter.

    Adds only *extra_paths* to the child's ``sys.path``; the scan modules are
    loaded by absolute host path, so no host ``site-packages`` entry is leaked.
    """
    return _CHILD_CODE_TEMPLATE.format(
        extra_paths=[str(p) for p in extra_paths],
        scanner_path=_SCANNER_PATH,
        childscan_path=_CHILDSCAN_PATH,
    )


def _stderr_message(stderr: str) -> str | None:
    """Extract the structured error message from the child's stderr.

    The contract is one JSON object ``{"type", "message"}``, but import-time
    code may print noise around it — scan backwards for the last line that
    parses as a JSON object with a ``message`` key.
    """
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "message" in obj:
            return str(obj["message"])
    return None


@dataclass
class ScanResult:
    """A generated LCP document plus the diagnostics from producing it.

    Attributes:
        document: The generated LCP document.
        unresolved_reexports: ``(ancestor_module, count, module_count)``
            triples for sibling packages that define re-exported names but
            were never scanned (issue #58). Empty for documents that did not
            come from a live scan.
    """

    document: LCPDocument
    unresolved_reexports: list[tuple[str, int, int]] = field(default_factory=list)


def scan_package_subprocess(
    package: str,
    python: str | None = None,
    timeout: float = DEFAULT_SCAN_TIMEOUT,
    extra_paths: Sequence[str] = (),
) -> ScanResult:
    """Scan *package* in a child interpreter and return its LCP document.

    Args:
        package: Import path of the package to scan (e.g. ``"requests"``).
        python: Interpreter whose environment gets scanned. Defaults to
            ``sys.executable`` — the server's own environment.
        timeout: Seconds before the child is killed.
        extra_paths: Additional ``sys.path`` entries for the child (test
            fixtures, path-based scans). The scan modules load by absolute path,
            so the target interpreter needs neither ``lcp`` nor ``pydantic``.

    Returns:
        A :class:`ScanResult` with the :class:`~lcp.models.LCPDocument`
        generated on the host from the child's raw ``ScannedModule`` JSON,
        plus any unresolved re-export diagnostics from the scan.

    Raises:
        ScanImportError: The package is not importable in the scan environment.
        ScanFailedError: The scan crashed or produced invalid output.
        ScanTimeoutError: The child exceeded *timeout* and was killed.
        ScanInterpreterNotFoundError: *python* does not exist.
        ScanSpawnError: The child process could not be spawned at all.
    """
    interpreter = python or sys.executable
    code = _build_child_code(extra_paths)
    cmd = [interpreter, "-c", code, package]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ScanTimeoutError(
            f"scan of '{package}' timed out after {timeout:.0f}s "
            f"(interpreter: {interpreter}); heavy packages may need a "
            f"higher scan timeout (--scan-timeout / .lcp-config.json 'scan_timeout')"
        ) from exc
    except FileNotFoundError as exc:
        raise ScanInterpreterNotFoundError(
            f"scan interpreter not found: {interpreter} — check the "
            f"'scan_python' / 'python' setting in .lcp-config.json"
        ) from exc
    except OSError as exc:
        raise ScanSpawnError(
            f"could not spawn the scan subprocess ({interpreter}): {exc}"
        ) from exc

    if proc.returncode == 0:
        try:
            from .generator import generate_lcp
            from .scanner import scanned_from_dict

            scanned = scanned_from_dict(json.loads(proc.stdout))
            return ScanResult(
                document=generate_lcp(scanned),
                unresolved_reexports=scanned.unresolved_reexports,
            )
        except Exception as exc:
            raise ScanFailedError(
                f"scan of '{package}' produced invalid scan data: {exc}"
            ) from exc

    message = _stderr_message(proc.stderr)
    if proc.returncode == 3:
        raise ScanImportError(
            message or f"'{package}' could not be imported by {interpreter}"
        )
    detail = (
        message
        or proc.stderr.strip()[-_STDERR_TAIL_CHARS:]
        or "no error output"
    )
    raise ScanFailedError(
        f"scan of '{package}' failed (exit code {proc.returncode}, "
        f"interpreter: {interpreter}): {detail}"
    )
