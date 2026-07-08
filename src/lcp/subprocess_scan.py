"""Run package scans in a separate interpreter.

The MCP server must not import arbitrary package code in-process: import-time
side effects can crash the server, heavy imports stall concurrent tool calls
(CPython import lock + GIL, even though FastMCP runs sync tools on worker
threads), and the server's environment is often not the project's environment.
This module launches :mod:`lcp.scanjson` in a child interpreter and parses the
LCP document it writes to stdout — the subprocess protocol IS the public
document format, so there is no private IPC format to version.

The child is started as ``<python> -c <bootstrap> <package>``, where the
bootstrap **appends** the server's import locations (``lcp`` and ``pydantic``)
to the child's ``sys.path`` before handing over to ``lcp.scanjson.main``.
Appending means the scan environment's own packages always win — the server's
site-packages can never shadow the target environment — while ``lcp`` does not
need to be installed in the scanned environment. The child inherits the
server's working directory; with ``-c``, that directory is also on its
``sys.path``, mirroring in-process import behavior.

Residual trust model (documented, not solved here): the scanned package's
import-time code still executes — just in a disposable child process. Process
isolation contains crashes and hangs; it is not a sandbox.
"""

from __future__ import annotations

import json
import subprocess
import sys
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


_BOOTSTRAP = (
    "import sys; sys.path.extend({paths!r}); "
    "from lcp.scanjson import main; main()"
)


def _bootstrap_paths(extra_paths: Sequence[str]) -> list[str]:
    """Return the paths appended to the child's ``sys.path``.

    Order matters: *extra_paths* first (test fixtures, path-based scans),
    then the server's ``lcp`` and ``pydantic`` locations. Everything is
    appended after the target environment's own entries, so the target
    always wins.
    """
    import pydantic

    import lcp

    paths = [str(p) for p in extra_paths]
    for mod in (lcp, pydantic):
        parent = str(Path(mod.__file__).resolve().parent.parent)
        if parent not in paths:
            paths.append(parent)
    return paths


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


def scan_package_subprocess(
    package: str,
    python: str | None = None,
    timeout: float = DEFAULT_SCAN_TIMEOUT,
    extra_paths: Sequence[str] = (),
) -> LCPDocument:
    """Scan *package* in a child interpreter and return its LCP document.

    Args:
        package: Import path of the package to scan (e.g. ``"requests"``).
        python: Interpreter whose environment gets scanned. Defaults to
            ``sys.executable`` — the server's own environment.
        timeout: Seconds before the child is killed.
        extra_paths: Additional ``sys.path`` entries for the child, appended
            before the server's own paths.

    Returns:
        The validated :class:`~lcp.models.LCPDocument` parsed from the
        child's stdout.

    Raises:
        ScanImportError: The package is not importable in the scan environment.
        ScanFailedError: The scan crashed or produced invalid output.
        ScanTimeoutError: The child exceeded *timeout* and was killed.
        ScanInterpreterNotFoundError: *python* does not exist.
        ScanSpawnError: The child process could not be spawned at all.
    """
    interpreter = python or sys.executable
    code = _BOOTSTRAP.format(paths=_bootstrap_paths(extra_paths))
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
            return LCPDocument.model_validate(json.loads(proc.stdout))
        except Exception as exc:
            raise ScanFailedError(
                f"scan of '{package}' returned invalid LCP JSON: {exc}"
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
