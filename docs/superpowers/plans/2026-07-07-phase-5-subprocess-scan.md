# Phase 5 — Subprocess Scanning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `resolve_library` no longer imports arbitrary package code into the MCP server process, and can scan packages installed in a *different* interpreter/venv (configured via `.lcp.json`).

**Architecture:** A new machine-mode entry point `python -m lcp.scanjson <pkg>` (stdlib `argparse`, no `click`) writes the public LCP JSON document to stdout, a structured JSON error to stderr, and distinguishes failures by exit code. A new `lcp.subprocess_scan` module launches it as `<python> -c <bootstrap> <pkg>`, where the bootstrap **appends** the server's own import paths (`lcp` + `pydantic` locations) to the child's `sys.path` — so the scanned environment's packages always win and `lcp` need not be installed there. `resolve_library_document` (the single choke point) gains a subprocess path that preserves the cache side effect and the three-step resolution order.

**Tech Stack:** Python stdlib only (`subprocess`, `argparse`, `json`, `venv` for tests) — **no new runtime deps**. Bash for `plugin/lcp/bin/serve.sh`.

## Global Constraints

- Python `>=3.10`; core deps stay `pydantic>=2`, `click>=8`, `jsonschema>=4`, `fastmcp>=2`. This phase adds **zero** new dependencies.
- **FREEZE:** manifest format / schema version `"1.0"` unchanged — this phase changes *how* scanning happens, not *what* is emitted. The subprocess protocol IS the public LCP document format (no private IPC format).
- Main suite (`.venv`) all green at start and end: baseline **541 passed, 0 failed**; end state 541 + new tests, 0 failed. The `evals/` suite is separate — do NOT touch `evals/.venv` (fastmcp 2.14.4 pinned); no eval-harness run is required for Phase 5.
- Commits follow the `git-commit-convention` skill (invoke it at every commit). Repo is public: **no co-author lines, no claude.ai session links** in commits or PR bodies.
- Docs follow the `lcp-writing-documentation` skill; `mkdocs build --strict` must pass.
- `docs/superpowers/` is gitignored — commit plan/roadmap changes with `git add -f`.
- Scope out: sandboxing beyond process isolation (document the residual trust model honestly), Windows launcher work beyond `sys.executable` defaults.

## Settled Open Decisions (with rationale)

1. **`.lcp.json` `python` field vs new `scan_python` field:** add `scan_python` as the explicit override; when absent, `serve.sh` falls back to the `python` value as the scan interpreter. Rationale: the user's intent for `python` is "my project's interpreter". In the #1 friction case (lcp installed globally, project venv without lcp) the `python -m lcp` launch probe *fails* and the server starts from the global lcp — but the scan must still target the project venv the user pointed at. So `python` does documented double duty as the *default* scan environment, and `scan_python` exists for the rare case where the two must diverge. Conflation is explicit and documented, not silent: the resolution is visible in `serve.sh` and in the plugin guide.
2. **Exit-code contract for the scan child:** `0` = success (LCP JSON document on stdout), `3` = import failure (target package not importable), `4` = scan/generate failure (including `SystemExit`/crash raised by import-time code). stderr carries one JSON object `{"type": ..., "message": ...}` (`type` ∈ `import_failure` | `scan_failure`). Exit codes `1`/`2` stay reserved for Python tracebacks / argparse errors and are mapped to a generic scan failure by the server. Timeout and interpreter-not-found are detected server-side (no exit code needed).
3. **`--scan-mode` default:** `subprocess` (both in `resolve_library_document` and the CLI), with `inprocess` as an explicit option. Automatic fallback to in-process happens **only** on spawn failure (`OSError` before any code was imported) **and only when the scan target is the server's own environment** — falling back when `scan_python` points elsewhere would silently scan the wrong venv, and falling back after a scan *crash* would re-import the crashing package inside the server, defeating the isolation.
4. **Timeout:** default 60 s (`DEFAULT_SCAN_TIMEOUT = 60.0` in `lcp.subprocess_scan`), configurable via `--scan-timeout` on `lcp serve-all` and a `scan_timeout` field in `.lcp.json` (passed through by `serve.sh`).
5. **Entry-point shape (from the roadmap's either/or):** `python -m lcp.scanjson` rather than a `--json -` flag on `lcp scan`. Decisive reason: the scan child must run in the *target* interpreter, whose environment only needs `lcp` + `pydantic` importable (bootstrapped from the server's paths); `lcp scan` would additionally require `click` there. `lcp scan` is untouched.
6. **Child bootstrap = append, not prepend:** the child is `<python> -c "import sys; sys.path.extend([...server paths...]); from lcp.scanjson import main; main()" <pkg>`. Appending means the target env's own packages always shadow the server's (scanning `requests` in the target venv can never pick up the server venv's `requests`); `PYTHONPATH` injection would prepend and is therefore wrong. Residual limitation (document, don't fix): if the target env holds an incompatible `pydantic` (v1) it wins over the server's v2 and the child fails cleanly with a generic scan error.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/lcp/scanjson.py` | **create** | Machine-mode scan entry point run inside the scan interpreter; owns the stdout/stderr/exit-code contract |
| `src/lcp/subprocess_scan.py` | **create** | Server-side runner: builds the bootstrap command, spawns, times out, parses, raises typed errors |
| `src/lcp/mcp_server.py` | modify | `resolve_library_document` + `_scan_live` subprocess path, error wording, plumbing through `_register_tools`, `create_universal_server`, `run_universal_server` |
| `src/lcp/cli.py` | modify | `lcp serve-all` gains `--scan-mode`, `--scan-python`, `--scan-timeout` |
| `plugin/lcp/bin/serve.sh` | modify | `lcp_build_args` function; `scan_python`→`python` fallback + `scan_timeout` pass-through |
| `tests/crashing_module.py`, `tests/printing_module.py`, `tests/slow_import_module.py` | **create** | Import-time crash / stdout-noise / slow-import fixtures |
| `tests/test_subprocess_scan.py` | **create** | All new tests (entry point, runner, cross-venv, resolve integration, concurrency) |
| `tests/test_mcp_server.py`, `tests/test_resolve_error_message.py` | modify | Pin `scan_mode="inprocess"` where tests mock in-process internals |
| `tests/test_cli.py` | modify | serve-all scan-option pass-through tests |
| `tests/plugin/test_scan_args.sh`, `tests/plugin/run_all.sh` | create/modify | Shell tests for the serve.sh pass-through |
| `docs/cli.md`, `docs/guides/mcp-server.md`, `docs/guides/claude-code-plugin.md`, `docs/architecture/mcp_server/architecture.md`, `docs/architecture/plugin/architecture.md`, `docs/api/subprocess-scan.md`, `mkdocs.yml`, `CLAUDE.md` | modify/create | Docs alignment (same phase) |

---

### Task 1: Machine-mode scan entry point (`lcp.scanjson`)

**Files:**
- Create: `src/lcp/scanjson.py`
- Create: `tests/crashing_module.py`, `tests/printing_module.py`, `tests/slow_import_module.py`
- Create: `tests/test_subprocess_scan.py` (first test class)

**Interfaces:**
- Consumes: `lcp.scanner.scan_package(package_name, include_private=False, recursive=True) -> ScannedModule`; `lcp.generator.generate_lcp(scanned) -> LCPDocument`; `LCPDocument.to_json(indent=2) -> str`.
- Produces: `python -m lcp.scanjson <pkg> [--include-private] [--no-recursive]` with the exit-code contract of Settled Decision 2, and `lcp.scanjson.main(argv: list[str] | None = None) -> None`. Task 2's bootstrap imports `lcp.scanjson.main`.

- [ ] **Step 1: Create the three fixtures**

`tests/crashing_module.py`:
```python
"""Fixture: a module whose import raises SystemExit (subprocess-scan tests)."""

import sys

sys.exit(1)
```

`tests/printing_module.py`:
```python
"""Fixture: a module that prints to stdout at import time (protocol hygiene)."""

print("import-time noise on stdout")


def documented(x: int) -> int:
    """Return x unchanged."""
    return x
```

`tests/slow_import_module.py`:
```python
"""Fixture: a module whose import blocks (timeout / concurrency tests).

Sleep length is read from LCP_TEST_IMPORT_SLEEP so tests choose their own
duration; the default is long enough that a missing override always trips
the scan timeout rather than passing by accident.
"""

import os
import time

time.sleep(float(os.environ.get("LCP_TEST_IMPORT_SLEEP", "30")))
```

These live directly in `tests/` (same convention as `tests/sample_module.py`); pytest only collects `test_*.py`, so they are never imported by the suite itself — only by scan children.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_subprocess_scan.py`:

```python
"""Tests for Phase 5 subprocess scanning: lcp.scanjson + lcp.subprocess_scan.

The scan child speaks the public LCP document format on stdout; errors are a
single JSON object on stderr plus a distinguishing exit code (0 ok /
3 import failure / 4 scan failure).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent


def _last_stderr_json(stderr: str) -> dict:
    """Parse the contract's JSON object from stderr (skipping any noise)."""
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON object on stderr: {stderr!r}")


class TestScanJsonEntryPoint:
    """python -m lcp.scanjson — the machine-mode scan contract."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        # cwd=tests/ puts the fixtures on the child's sys.path (sys.path[0]).
        return subprocess.run(
            [sys.executable, "-m", "lcp.scanjson", *args],
            capture_output=True,
            text=True,
            cwd=TESTS_DIR,
            timeout=120,
        )

    def test_happy_path_writes_lcp_document_to_stdout(self):
        proc = self._run("sample_package")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert doc["manifest"]["library"]["name"] == "sample_package"
        assert doc["symbols"]

    def test_import_failure_exits_3_with_stderr_json(self):
        proc = self._run("definitely_not_installed_xyz")
        assert proc.returncode == 3
        err = _last_stderr_json(proc.stderr)
        assert err["type"] == "import_failure"
        assert "definitely_not_installed_xyz" in err["message"]
        assert proc.stdout == ""

    def test_systemexit_during_import_exits_4(self):
        proc = self._run("crashing_module")
        assert proc.returncode == 4
        err = _last_stderr_json(proc.stderr)
        assert err["type"] == "scan_failure"
        assert "SystemExit" in err["message"]
        assert proc.stdout == ""

    def test_import_time_stdout_noise_does_not_corrupt_protocol(self):
        proc = self._run("printing_module")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)  # fails if noise leaked onto stdout
        assert "printing_module:documented" in doc["symbols"]
        assert "import-time noise" in proc.stderr
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py -v`
Expected: 4 FAIL — `returncode == 1` with `No module named lcp.scanjson` on stderr.

- [ ] **Step 4: Implement `src/lcp/scanjson.py`**

```python
"""Machine-mode scan entry point: ``python -m lcp.scanjson <package>``.

Runs inside the *scan interpreter* — possibly a different venv from the MCP
server — and speaks the public LCP document format on stdout, so there is no
private IPC format to version. Errors are a single JSON object
``{"type": ..., "message": ...}`` on stderr plus a distinguishing exit code.

Exit codes:
    0: success — the LCP JSON document is on stdout.
    3: import failure — the target package could not be imported.
    4: scan failure — the package imported but scanning or generation failed,
       including ``SystemExit`` (or any other ``BaseException``) raised by
       import-time code.

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
        argv: Argument list (default: ``sys.argv[1:]``): the package name
            plus optional ``--include-private`` / ``--no-recursive`` flags.
    """
    parser = argparse.ArgumentParser(
        prog="python -m lcp.scanjson",
        description="Scan an installed package and write its LCP document to stdout.",
    )
    parser.add_argument("package", help="Import path of the package to scan.")
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--no-recursive", action="store_true")
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
            )
        except ImportError as exc:
            _fail(3, "import_failure", str(exc))
        except BaseException as exc:  # SystemExit & co. from import-time code
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
```

Note: the `SystemExit` raised by `_fail` inside an `except` handler propagates normally — sibling `except BaseException` clauses of the *same* `try` cannot catch it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit** (invoke `git-commit-convention` skill)

```bash
git add src/lcp/scanjson.py tests/crashing_module.py tests/printing_module.py tests/slow_import_module.py tests/test_subprocess_scan.py
git commit  # "ADD: Machine-mode scan entry point (python -m lcp.scanjson)"
```

---

### Task 2: Subprocess scan runner (`lcp.subprocess_scan`) + cross-venv proof

**Files:**
- Create: `src/lcp/subprocess_scan.py`
- Test: `tests/test_subprocess_scan.py` (append)

**Interfaces:**
- Consumes: `lcp.scanjson.main` (via the `-c` bootstrap), `lcp.models.LCPDocument.model_validate`.
- Produces (used by Task 3):
  - `scan_package_subprocess(package: str, python: str | None = None, timeout: float = DEFAULT_SCAN_TIMEOUT, extra_paths: Sequence[str] = ()) -> LCPDocument`
  - `DEFAULT_SCAN_TIMEOUT: float = 60.0`
  - Exceptions (all subclass `SubprocessScanError(Exception)`): `ScanImportError`, `ScanFailedError`, `ScanTimeoutError`, `ScanInterpreterNotFoundError`, `ScanSpawnError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_subprocess_scan.py`:

```python
import time
import venv

import pytest

from lcp.subprocess_scan import (
    DEFAULT_SCAN_TIMEOUT,
    ScanFailedError,
    ScanImportError,
    ScanInterpreterNotFoundError,
    ScanSpawnError,
    ScanTimeoutError,
    scan_package_subprocess,
)


class TestScanPackageSubprocess:
    """Server-side runner: spawn, parse, classify failures."""

    def test_happy_path_returns_document(self):
        doc = scan_package_subprocess(
            "sample_package", extra_paths=[str(TESTS_DIR)]
        )
        assert doc.manifest.library.name == "sample_package"
        assert len(doc.symbols) > 0

    def test_import_failure_raises_scan_import_error(self):
        with pytest.raises(ScanImportError, match="definitely_not_installed_xyz"):
            scan_package_subprocess("definitely_not_installed_xyz")

    def test_crashing_package_raises_scan_failed_error(self):
        with pytest.raises(ScanFailedError, match="SystemExit"):
            scan_package_subprocess(
                "crashing_module", extra_paths=[str(TESTS_DIR)]
            )

    def test_timeout_kills_the_scan(self, monkeypatch):
        monkeypatch.setenv("LCP_TEST_IMPORT_SLEEP", "30")
        start = time.monotonic()
        with pytest.raises(ScanTimeoutError, match="timed out"):
            scan_package_subprocess(
                "slow_import_module",
                extra_paths=[str(TESTS_DIR)],
                timeout=1.0,
            )
        assert time.monotonic() - start < 10  # killed, not waited out

    def test_interpreter_not_found(self):
        with pytest.raises(
            ScanInterpreterNotFoundError, match="/nonexistent/python"
        ):
            scan_package_subprocess("json", python="/nonexistent/python")

    def test_spawn_oserror_raises_scan_spawn_error(self, monkeypatch):
        def blocked(*args, **kwargs):
            raise PermissionError("spawn blocked")

        monkeypatch.setattr("lcp.subprocess_scan.subprocess.run", blocked)
        with pytest.raises(ScanSpawnError, match="spawn blocked"):
            scan_package_subprocess("json")

    def test_default_timeout_is_60s(self):
        assert DEFAULT_SCAN_TIMEOUT == 60.0


@pytest.fixture(scope="module")
def second_venv(tmp_path_factory) -> Path:
    """A pip-less venv whose site-packages holds a package this process cannot see."""
    root = tmp_path_factory.mktemp("second-venv")
    venv.create(root, with_pip=False)
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    vpy = root / bin_dir / ("python.exe" if sys.platform == "win32" else "python")
    purelib = subprocess.run(
        [str(vpy), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (Path(purelib) / "secondvenv_only_pkg.py").write_text(
        '"""A package that exists only in the second venv."""\n'
        "\n"
        "def greet(name: str) -> str:\n"
        '    """Return a greeting for name."""\n'
        '    return f"hello {name}"\n',
        encoding="utf-8",
    )
    return vpy


class TestCrossEnvironmentScan:
    """Exit criterion: a package installed only in a second venv resolves."""

    def test_package_is_invisible_to_the_server_env(self):
        import importlib.util

        assert importlib.util.find_spec("secondvenv_only_pkg") is None

    def test_scan_resolves_package_from_second_venv(self, second_venv):
        doc = scan_package_subprocess(
            "secondvenv_only_pkg", python=str(second_venv)
        )
        assert "secondvenv_only_pkg:greet" in doc.symbols
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py -v`
Expected: Task 1 tests still PASS; the new ones FAIL at import with `ModuleNotFoundError: No module named 'lcp.subprocess_scan'`.

- [ ] **Step 3: Implement `src/lcp/subprocess_scan.py`**

```python
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
            f"higher scan timeout (--scan-timeout / .lcp.json 'scan_timeout')"
        ) from exc
    except FileNotFoundError as exc:
        raise ScanInterpreterNotFoundError(
            f"scan interpreter not found: {interpreter} — check the "
            f"'scan_python' / 'python' setting in .lcp.json"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py -v`
Expected: all PASS (Task 1's 4 + 8 runner tests + 2 cross-venv tests).

- [ ] **Step 5: Commit** (invoke `git-commit-convention` skill)

```bash
git add src/lcp/subprocess_scan.py tests/test_subprocess_scan.py
git commit  # "ADD: Subprocess scan runner with typed failures and cross-venv support"
```

---

### Task 3: Wire `resolve_library_document` to the subprocess path

**Files:**
- Modify: `src/lcp/mcp_server.py` (`resolve_library_document`, new `_scan_inprocess`/`_scan_live` helpers, imports)
- Modify: `tests/test_mcp_server.py` (classes `TestResolveLibraryDocument`, `TestResolveDocumentVersion`)
- Modify: `tests/test_resolve_error_message.py`
- Test: `tests/test_subprocess_scan.py` (append)

**Interfaces:**
- Consumes: everything Task 2 produces.
- Produces (used by Task 4): `resolve_library_document(name, cache_dir=_DEFAULT_CACHE_DIR, no_cache=False, registry_url=None, version=None, scan_mode="subprocess", scan_python=None, scan_timeout=DEFAULT_SCAN_TIMEOUT) -> tuple[LCPDocument, str]`. Resolution order (cache → live scan → registry) and the cache side effect are unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_subprocess_scan.py`:

```python
from lcp.mcp_server import resolve_library_document


class TestResolveViaSubprocess:
    """resolve_library_document defaults to the subprocess path."""

    def test_scan_runs_in_subprocess_and_preserves_cache_side_effect(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(TESTS_DIR)  # child inherits cwd → fixtures importable
        cache_dir = tmp_path / "cache"
        doc, source = resolve_library_document("sample_package", cache_dir=cache_dir)
        assert source == "scan"
        assert len(doc.symbols) > 0
        _, source2 = resolve_library_document("sample_package", cache_dir=cache_dir)
        assert source2 == "cache"

    def test_crashing_import_degrades_to_clean_error(self, tmp_path, monkeypatch):
        """Exit criterion: SystemExit at import must not kill the server."""
        monkeypatch.chdir(TESTS_DIR)
        with pytest.raises(ImportError, match="SystemExit"):
            resolve_library_document(
                "crashing_module", cache_dir=tmp_path, no_cache=True
            )
        # Reaching this line at all proves the crash stayed in the child.

    def test_resolve_via_scan_python(self, tmp_path, second_venv):
        """Exit criterion: package installed only in a second venv resolves."""
        doc, source = resolve_library_document(
            "secondvenv_only_pkg",
            cache_dir=tmp_path / "cache",
            no_cache=True,
            scan_python=str(second_venv),
        )
        assert source == "scan"
        assert "secondvenv_only_pkg:greet" in doc.symbols

    def test_import_failure_message_names_configured_interpreter(
        self, tmp_path, second_venv
    ):
        """The 'different environment' error now names the interpreter used."""
        with pytest.raises(ImportError) as ei:
            resolve_library_document(
                "definitely_not_installed_xyz",
                cache_dir=tmp_path,
                no_cache=True,
                scan_python=str(second_venv),
            )
        assert str(second_venv) in str(ei.value)
        assert "not importable" in str(ei.value).lower()

    def test_scan_mode_inprocess_still_works(self, tmp_path):
        doc, source = resolve_library_document(
            "tests.sample_module",
            cache_dir=tmp_path,
            no_cache=True,
            scan_mode="inprocess",
        )
        assert source == "scan"
        assert len(doc.symbols) > 0

    def test_spawn_failure_falls_back_inprocess_for_own_env(
        self, tmp_path, monkeypatch
    ):
        def blocked(*args, **kwargs):
            raise ScanSpawnError("spawn blocked")

        monkeypatch.setattr("lcp.mcp_server.scan_package_subprocess", blocked)
        doc, source = resolve_library_document(
            "tests.sample_module", cache_dir=tmp_path, no_cache=True
        )
        assert source == "scan"  # fell back to in-process, same environment

    def test_spawn_failure_with_scan_python_does_not_fall_back(
        self, tmp_path, monkeypatch
    ):
        """Falling back in-process would scan the WRONG environment."""

        def blocked(*args, **kwargs):
            raise ScanSpawnError("spawn blocked")

        monkeypatch.setattr("lcp.mcp_server.scan_package_subprocess", blocked)
        with pytest.raises(ImportError, match="spawn blocked"):
            resolve_library_document(
                "tests.sample_module",
                cache_dir=tmp_path,
                no_cache=True,
                scan_python="/some/other/python",
            )

    def test_timeout_surfaces_actionable_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LCP_TEST_IMPORT_SLEEP", "30")
        monkeypatch.chdir(TESTS_DIR)
        with pytest.raises(ImportError, match="timed out"):
            resolve_library_document(
                "slow_import_module",
                cache_dir=tmp_path,
                no_cache=True,
                scan_timeout=1.0,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py::TestResolveViaSubprocess -v`
Expected: FAIL — `TypeError: resolve_library_document() got an unexpected keyword argument 'scan_python'` (and the crash test fails because the in-process scan path raises differently).

- [ ] **Step 3: Implement in `src/lcp/mcp_server.py`**

Add to the imports block (after `from .naming import normalize_package_name`):

```python
from .subprocess_scan import (
    DEFAULT_SCAN_TIMEOUT,
    ScanImportError,
    ScanInterpreterNotFoundError,
    ScanSpawnError,
    ScanTimeoutError,
    scan_package_subprocess,
)
```

Add two helpers immediately above `resolve_library_document`:

```python
def _scan_inprocess(name: str) -> LCPDocument:
    """Scan *name* by importing it into this process (legacy path)."""
    from .generator import generate_lcp
    from .scanner import scan_package

    return generate_lcp(scan_package(name, include_private=False, recursive=True))


def _scan_live(
    name: str,
    scan_mode: str,
    scan_python: str | None,
    scan_timeout: float,
) -> LCPDocument:
    """Run the live scan for *name* honoring the configured scan mode.

    Falls back to in-process scanning only when the subprocess could not be
    *spawned* (no package code ran) and the scan target is this very
    environment — a spawn failure with a configured ``scan_python`` must
    error instead, because scanning in-process would read the wrong venv,
    and a scan *crash* must never re-run in-process at all.
    """
    if scan_mode == "inprocess":
        return _scan_inprocess(name)
    try:
        return scan_package_subprocess(
            name, python=scan_python, timeout=scan_timeout
        )
    except ScanSpawnError:
        if scan_python is None or scan_python == sys.executable:
            return _scan_inprocess(name)
        raise
```

Change `resolve_library_document`'s signature and docstring (new args documented Google-style):

```python
def resolve_library_document(
    name: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    no_cache: bool = False,
    registry_url: str | None = None,
    version: str | None = None,
    scan_mode: str = "subprocess",
    scan_python: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> tuple[LCPDocument, str]:
```

Docstring additions (keep the existing text; extend `Args:` and the resolution-order note):

```
        scan_mode: ``"subprocess"`` (default) runs the live scan in a child
            interpreter — import-time crashes and heavy imports stay out of
            the server process; ``"inprocess"`` imports the package into
            this process (for environments where spawning is restricted).
        scan_python: Interpreter whose environment the live scan reads
            (default: this process's interpreter). This is how packages
            installed in a different venv get resolved.
        scan_timeout: Seconds before a subprocess scan is killed.
```

Replace the body of step "2. Live scan" (currently `scanned = scan_package(...); doc = generate_lcp(scanned)`) with:

```python
    # 2. Live scan
    scan_error: Exception | None = None
    try:
        doc = _scan_live(name, scan_mode, scan_python, scan_timeout)
        if not no_cache:
            try:
                _save_to_cache(cache_dir, doc)
            except Exception:
                pass  # cache write failure is non-fatal
        return doc, "scan"
    except Exception as exc:
        scan_error = exc
```

Also remove the now-unused local imports at the top of the function (`from .scanner import scan_package`, `from .generator import generate_lcp`) — they live in `_scan_inprocess` now.

Replace the final error-wording block (everything from `if installed_ver:` to the closing `raise ImportError(...)`) with:

```python
    scan_interpreter = scan_python or sys.executable
    if isinstance(scan_error, ScanImportError):
        if scan_python:
            remedy = (
                "Check that the package is installed in that environment, "
                "or fix 'scan_python' in .lcp.json"
            )
        else:
            remedy = (
                "It may be installed in a different environment — point the "
                "server at that env via .lcp.json ('scan_python' or 'python')"
            )
        reason = (
            f"'{name}' is not importable by the scan interpreter "
            f"({scan_interpreter}). {remedy}; the distribution name may also "
            f"differ from the import path (e.g. import 'google.adk' is "
            f"provided by 'pip install google-adk')."
        )
    elif isinstance(
        scan_error, (ScanTimeoutError, ScanInterpreterNotFoundError, ScanSpawnError)
    ):
        # The runner's messages are already agent-facing and actionable.
        reason = str(scan_error)
    elif installed_ver:
        # The package is installed in this environment but scanning failed.
        reason = (
            f"'{name}' is installed (version {installed_ver}) in this environment "
            f"but the scan failed: {type(scan_error).__name__}: {scan_error}"
        )
    elif isinstance(scan_error, ImportError):
        # In-process scan: could not import with the interpreter running lcp.
        reason = (
            f"'{name}' is not importable by the Python interpreter running lcp "
            f"({sys.executable}). It may be installed in a different environment "
            f"(point the plugin at that env via .lcp.json), or the distribution "
            f"name may differ from the import path "
            f"(e.g. import 'google.adk' is provided by 'pip install google-adk')."
        )
    else:
        reason = (
            f"could not resolve '{name}': {type(scan_error).__name__}: {scan_error}"
        )

    raise ImportError(
        f"Cannot resolve library '{name}': {reason}"
        + (f" (registry fetch also failed: {registry_url})" if registry_url else "")
    ) from scan_error
```

- [ ] **Step 4: Pin existing resolution-logic tests to in-process mode**

These tests exercise cache/registry logic or monkeypatch `lcp.scanner.scan_package`, so they must not depend on (or pay for) a child process:

- `tests/test_mcp_server.py`: add `scan_mode="inprocess",` to **every** `resolve_library_document(...)` call inside `class TestResolveLibraryDocument` and `class TestResolveDocumentVersion` (11 call sites; e.g. `resolve_library_document("tests.sample_module", cache_dir=tmp_path / "cache", no_cache=True, scan_mode="inprocess")`).
- `tests/test_resolve_error_message.py::test_installed_but_scan_fails_message`: add `scan_mode="inprocess"` to its `resolve_library_document` call (it monkeypatches `lcp.scanner.scan_package`, which only the in-process path reaches).
- `tests/test_resolve_error_message.py::test_missing_package_message_names_interpreter`: leave on the default — it now validates the subprocess `ScanImportError` wording, which deliberately keeps "not importable", `sys.executable`, and the no-`pip install <import-path>` guarantees.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS (541 baseline + new), 0 failed.

- [ ] **Step 6: Commit** (invoke `git-commit-convention` skill)

```bash
git add src/lcp/mcp_server.py tests/test_subprocess_scan.py tests/test_mcp_server.py tests/test_resolve_error_message.py
git commit  # "UPD: resolve_library scans in a subprocess by default"
```

---

### Task 4: Server + CLI plumbing (`--scan-mode`, `--scan-python`, `--scan-timeout`)

**Files:**
- Modify: `src/lcp/mcp_server.py` (`_register_tools`, `create_universal_server`, `run_universal_server`)
- Modify: `src/lcp/cli.py` (`serve_all`)
- Test: `tests/test_subprocess_scan.py` (append), `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: Task 3's `resolve_library_document(..., scan_mode=, scan_python=, scan_timeout=)`.
- Produces: `create_universal_server(..., scan_mode: str = "subprocess", scan_python: str | None = None, scan_timeout: float = DEFAULT_SCAN_TIMEOUT)`; same three kwargs on `run_universal_server` and `_register_tools`; CLI flags `--scan-mode {subprocess,inprocess}`, `--scan-python TEXT`, `--scan-timeout FLOAT` on `lcp serve-all` (consumed by Task 6's `serve.sh`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_subprocess_scan.py`:

```python
from lcp.mcp_server import create_universal_server


class TestServerScanPlumbing:
    def test_scan_params_reach_the_resolver(self, tmp_path, monkeypatch):
        calls: dict = {}

        def fake_resolve(name, **kwargs):
            calls.update(kwargs)
            raise ImportError("stop here")

        monkeypatch.setattr(
            "lcp.mcp_server.resolve_library_document", fake_resolve
        )
        server = create_universal_server(
            cache_dir=tmp_path,
            scan_mode="inprocess",
            scan_python="/x/py",
            scan_timeout=5.0,
        )
        result = server.tools["resolve_library"]("whatever")
        assert result["error"]["code"] == "resolve_failed"
        assert calls["scan_mode"] == "inprocess"
        assert calls["scan_python"] == "/x/py"
        assert calls["scan_timeout"] == 5.0
```

Append to `tests/test_cli.py`:

```python
class TestServeAllScanOptions:
    """serve-all must pass the scan options through to the server."""

    def _invoke_with_capture(self, monkeypatch, args):
        from click.testing import CliRunner

        from lcp import cli

        captured: dict = {}
        monkeypatch.setattr(
            cli, "run_universal_server", lambda **kw: captured.update(kw)
        )
        result = CliRunner().invoke(cli.main, ["serve-all", *args])
        assert result.exit_code == 0, result.output
        return captured

    def test_scan_options_are_passed_through(self, monkeypatch):
        captured = self._invoke_with_capture(
            monkeypatch,
            [
                "--scan-mode", "inprocess",
                "--scan-python", "/x/py",
                "--scan-timeout", "30",
            ],
        )
        assert captured["scan_mode"] == "inprocess"
        assert captured["scan_python"] == "/x/py"
        assert captured["scan_timeout"] == 30.0

    def test_scan_defaults(self, monkeypatch):
        captured = self._invoke_with_capture(monkeypatch, [])
        assert captured["scan_mode"] == "subprocess"
        assert captured["scan_python"] is None
        assert captured["scan_timeout"] == 60.0
```

(If `tests/test_cli.py` does not already import `CliRunner`/`cli` at module level, the local imports above keep the addition self-contained.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py::TestServerScanPlumbing tests/test_cli.py -v`
Expected: FAIL — `create_universal_server() got an unexpected keyword argument 'scan_mode'`; CLI test fails with `no such option: --scan-mode`.

- [ ] **Step 3: Implement the plumbing**

In `src/lcp/mcp_server.py`:

1. `_register_tools` — add parameters (after `max_response_bytes`) and document them in its docstring:

```python
    scan_mode: str = "subprocess",
    scan_python: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
```

and inside its `resolve_library` closure pass them to `resolve_library_document`:

```python
            doc, source = resolve_library_document(
                name,
                cache_dir=cache_dir,
                no_cache=no_cache,
                registry_url=registry_url,
                version=version,
                scan_mode=scan_mode,
                scan_python=scan_python,
                scan_timeout=scan_timeout,
            )
```

2. `create_universal_server` — add the same three keyword args (after `max_response_bytes`), document them (Google-style `Args:`), and forward them in the `_register_tools(...)` call.
3. `run_universal_server` — add the same three keyword args, document them, and forward them to `create_universal_server(...)`.

In `src/lcp/cli.py`, add to the `serve_all` command (after the `--max-response-bytes` option):

```python
@click.option(
    "--scan-mode",
    type=click.Choice(["subprocess", "inprocess"]),
    default="subprocess",
    show_default=True,
    help=(
        "How resolve_library scans installed packages: 'subprocess' isolates "
        "package imports in a disposable child process (crash isolation, "
        "cross-venv scanning, no import-lock stalls); 'inprocess' imports "
        "into the server process (for environments where spawning is "
        "restricted)."
    ),
)
@click.option(
    "--scan-python",
    type=str,
    default=None,
    help=(
        "Python interpreter whose environment resolve_library scans "
        "(default: the interpreter running the server). Lets the server "
        "document packages installed in a different venv."
    ),
)
@click.option(
    "--scan-timeout",
    type=float,
    default=60.0,
    show_default=True,
    help="Seconds before a subprocess scan is killed.",
)
```

extend the function signature:

```python
def serve_all(
    cache_dir: str | None,
    name: str,
    no_cache: bool,
    registry: str | None,
    expose: tuple[str, ...],
    preload: tuple[str, ...],
    max_response_bytes: int,
    scan_mode: str,
    scan_python: str | None,
    scan_timeout: float,
):
```

and forward inside:

```python
        run_universal_server(
            name=name,
            cache_dir=cache_dir,
            no_cache=no_cache,
            registry_url=registry,
            expose=list(expose) if expose else None,
            preload=list(preload) if preload else None,
            max_response_bytes=max_response_bytes,
            scan_mode=scan_mode,
            scan_python=scan_python,
            scan_timeout=scan_timeout,
        )
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS, 0 failed.

- [ ] **Step 5: Commit** (invoke `git-commit-convention` skill)

```bash
git add src/lcp/mcp_server.py src/lcp/cli.py tests/test_subprocess_scan.py tests/test_cli.py
git commit  # "UPD: serve-all scan options (--scan-mode/--scan-python/--scan-timeout)"
```

---

### Task 5: Concurrency exit criterion

**Files:**
- Test: `tests/test_subprocess_scan.py` (append)

**Interfaces:**
- Consumes: Task 3's `resolve_library_document`, the `slow_import_module` fixture (`LCP_TEST_IMPORT_SLEEP`).

- [ ] **Step 1: Write the test**

Append to `tests/test_subprocess_scan.py`:

```python
import threading


class TestConcurrency:
    def test_slow_scan_does_not_block_other_resolves(self, tmp_path, monkeypatch):
        """Exit criterion: a heavy import in one scan must not stall other
        tool calls. In-process, the CPython import lock + GIL would hold the
        quick resolve hostage for the full sleep; the subprocess releases
        the GIL while waiting on the child.
        """
        monkeypatch.setenv("LCP_TEST_IMPORT_SLEEP", "4")
        monkeypatch.chdir(TESTS_DIR)
        slow_done = threading.Event()

        def slow_scan():
            try:
                resolve_library_document(
                    "slow_import_module",
                    cache_dir=tmp_path / "slow-cache",
                    no_cache=True,
                )
            finally:
                slow_done.set()

        thread = threading.Thread(target=slow_scan)
        thread.start()
        try:
            time.sleep(0.5)  # let the slow child get going
            doc, _ = resolve_library_document(
                "sample_package",
                cache_dir=tmp_path / "quick-cache",
                no_cache=True,
            )
            assert len(doc.symbols) > 0
            assert not slow_done.is_set(), (
                "quick resolve should complete while the slow scan is running"
            )
        finally:
            thread.join(timeout=30)
```

- [ ] **Step 2: Run the test — it must pass already** (the subprocess default is what makes it pass; that is the point of the criterion)

Run: `.venv/bin/python -m pytest tests/test_subprocess_scan.py::TestConcurrency -v`
Expected: PASS in well under 10 s. Sanity-check the criterion is real: temporarily rerun with the quick call forced to `scan_mode="inprocess"` — it still passes (the *slow* scan is the one that must not hold the import lock). No code change needed; this step documents behavior with a test.

- [ ] **Step 3: Commit** (invoke `git-commit-convention` skill)

```bash
git add tests/test_subprocess_scan.py
git commit  # "ADD: Concurrency regression test for subprocess scanning"
```

---

### Task 6: Plugin pass-through (`serve.sh` + `.lcp.json`)

**Files:**
- Modify: `plugin/lcp/bin/serve.sh`
- Create: `tests/plugin/test_scan_args.sh`
- Modify: `tests/plugin/run_all.sh`

**Interfaces:**
- Consumes: Task 4's `--scan-python` / `--scan-timeout` flags.
- Produces: `.lcp.json` fields `scan_python` (string) and `scan_timeout` (number); shell function `lcp_build_args` (one argv element per line). Decision 1's fallback lives here: `scan_python` wins, else `python`, else no flag.

- [ ] **Step 1: Write the failing shell test**

Create `tests/plugin/test_scan_args.sh` (mode 755):

```bash
#!/usr/bin/env bash
# serve.sh must pass the scan interpreter through to `lcp serve-all`:
# scan_python wins, python is the documented fallback, scan_timeout follows.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVE="$HERE/../../plugin/lcp/bin/serve.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

export LCP_SERVE_LIB=1
export CLAUDE_PROJECT_DIR="$TMP"
# shellcheck disable=SC1090
source "$SERVE"

# 1. scan_python set → used verbatim; scan_timeout passes through
cat > "$TMP/.lcp.json" <<'JSON'
{ "python": "/venv/server/bin/python", "scan_python": "/venv/scan/bin/python", "scan_timeout": 120 }
JSON
args="$(lcp_build_args | tr '\n' ' ')"
case "$args" in *"--scan-python /venv/scan/bin/python "*) ;; *) echo "FAIL scan_python: $args"; exit 1;; esac
case "$args" in *"--scan-timeout 120 "*) ;; *) echo "FAIL scan_timeout: $args"; exit 1;; esac

# 2. no scan_python → python is the fallback scan interpreter
cat > "$TMP/.lcp.json" <<'JSON'
{ "python": "/venv/project/bin/python" }
JSON
args="$(lcp_build_args | tr '\n' ' ')"
case "$args" in *"--scan-python /venv/project/bin/python "*) ;; *) echo "FAIL python fallback: $args"; exit 1;; esac

# 3. neither field → no --scan-python at all; existing args still built
cat > "$TMP/.lcp.json" <<'JSON'
{ "expose": ["json"] }
JSON
args="$(lcp_build_args | tr '\n' ' ')"
case "$args" in *"--scan-python"*) echo "FAIL unexpected scan_python: $args"; exit 1;; *) ;; esac
case "$args" in *"--expose json "*) ;; *) echo "FAIL expose lost: $args"; exit 1;; esac

echo "OK scan_args"
```

Add `test_scan_args.sh` to the loop list in `tests/plugin/run_all.sh`:

```bash
for t in test_config_reader.sh test_resolution.sh test_generate_config.sh test_manifest.sh test_scan_args.sh; do
```

- [ ] **Step 2: Run to verify it fails**

Run: `bash tests/plugin/test_scan_args.sh`
Expected: FAIL — `lcp_build_args: command not found`.

- [ ] **Step 3: Implement in `plugin/lcp/bin/serve.sh`**

Insert a `lcp_build_args` function **above** the `LCP_SERVE_LIB` guard (after `lcp_resolve_launcher`), and note the trailing space produced by the test's `tr` when matching:

```bash
# lcp_build_args — echo the `lcp serve-all` argv, one element per line.
# The scan interpreter resolution implements the documented double duty:
# `scan_python` wins; else `python` (the user's "my project env" intent —
# even when the launcher probe rejected it for *running* the server, it is
# still the environment the user wants scanned); else the server scans its
# own environment.
lcp_build_args() {
  local out=(serve-all) r e p sp st
  for r in $(lcp_config_get registries); do out+=(--registry "$r"); break; done
  for e in $(lcp_config_get expose);  do out+=(--expose "$e");  done
  for p in $(lcp_config_get preload); do out+=(--preload "$p"); done
  sp="$(lcp_config_get scan_python)"
  if [ -z "$sp" ]; then sp="$(lcp_config_get python)"; fi
  if [ -n "$sp" ]; then out+=(--scan-python "$sp"); fi
  st="$(lcp_config_get scan_timeout)"
  if [ -n "$st" ]; then out+=(--scan-timeout "$st"); fi
  printf '%s\n' "${out[@]}"
}
```

Replace the bottom-of-file `ARGS=(serve-all); for ...` block with (bash 3.2 compatible — no `mapfile` on macOS):

```bash
ARGS=()
while IFS= read -r a; do ARGS+=("$a"); done < <(lcp_build_args)

# shellcheck disable=SC2086
exec $LAUNCHER "${ARGS[@]}"
```

Update the header comment of `serve.sh`: append to the config paragraph a line such as `# Scan interpreter: .lcp.json 'scan_python' (fallback: 'python') is passed to the server as --scan-python; 'scan_timeout' as --scan-timeout.`

- [ ] **Step 4: Run the shell suites**

Run: `bash tests/plugin/run_all.sh`
Expected: `OK scan_args` and `ALL PLUGIN TESTS PASSED` (existing tests must stay green — they source the same file).

- [ ] **Step 5: Run the Python suite** (plugin hook tests exercise plugin files)

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit** (invoke `git-commit-convention` skill)

```bash
git add plugin/lcp/bin/serve.sh tests/plugin/test_scan_args.sh tests/plugin/run_all.sh
git commit  # "UPD: Plugin passes scan_python/scan_timeout from .lcp.json to serve-all"
```

---

### Task 7: Documentation alignment (same phase — mandatory)

**Files:**
- Modify: `docs/cli.md`, `docs/guides/mcp-server.md`, `docs/guides/claude-code-plugin.md`
- Modify: `docs/architecture/mcp_server/architecture.md`, `docs/architecture/plugin/architecture.md`
- Create: `docs/api/subprocess-scan.md`; Modify: `mkdocs.yml` (nav), `CLAUDE.md`

**Interfaces:**
- Consumes: everything shipped in Tasks 1–6.

- [ ] **Step 1: Invoke the `lcp-writing-documentation` skill** and follow its conventions for each area (architecture: no code snippets, `snake_case`; guides/CLI: task-oriented, examples expected; API reference: docstrings only + mkdocstrings stub).

- [ ] **Step 2: User-facing docs**

- `docs/cli.md` › `lcp serve-all`: document `--scan-mode` (default `subprocess`), `--scan-python`, `--scan-timeout` (default 60) in the options table/format already used by the page. Add a short subsection **Machine-mode scanning** documenting `python -m lcp.scanjson <pkg>` with the contract table: exit `0` → LCP JSON on stdout; `3` → import failure; `4` → scan failure; stderr → one JSON object `{"type", "message"}`. Note it needs no `click` in the target environment.
- `docs/guides/mcp-server.md` › "How it works": state that the live scan runs in a disposable child interpreter by default (crash isolation; heavy imports don't stall concurrent tool calls; the subprocess speaks the public LCP document format). Add a **Scanning environment** subsection: `--scan-python` for a different venv, `--scan-timeout`, `--scan-mode inprocess` escape hatch, and an honest trust-model note: *scanned package code still executes at import time — in a child process, which contains crashes and hangs but is not a sandbox*.
- `docs/guides/claude-code-plugin.md` › "Configuration: `.lcp.json`": add `scan_python` and `scan_timeout` to the field list; document the fallback (`scan_python` → `python` → server's own interpreter) and update the "installed in a different environment" troubleshooting entry — the remedy is now real: set `python` (or `scan_python`) to the project venv and the server *scans that venv* even when `lcp` itself is not installed there.

- [ ] **Step 3: Architecture docs**

- `docs/architecture/mcp_server/architecture.md`: update the resolution-flow diagram node (`scan_package() + generate_lcp()` → subprocess scan via `lcp.scanjson`) and add a design-rationale paragraph: why subprocess (crash isolation, import-lock/GIL responsiveness, cross-venv reach), why the protocol is the public document format (no private IPC to version), the append-not-prepend `sys.path` bootstrap, the spawn-failure-only fallback rule, and the residual trust model.
- `docs/architecture/plugin/architecture.md`: document the launcher-interpreter vs scan-interpreter distinction and the `scan_python` → `python` fallback chain.

- [ ] **Step 4: API reference + project docs**

- Create `docs/api/subprocess-scan.md` mirroring the existing api pages' mkdocstrings format, covering `lcp.subprocess_scan` and `lcp.scanjson`; add `- Subprocess Scan: api/subprocess-scan.md` to the API nav in `mkdocs.yml` (after `MCP Server`).
- `CLAUDE.md`: add `scanjson.py` and `subprocess_scan.py` rows to the Module Responsibilities table; add a Conventions bullet: live scans run in a subprocess by default (`scan_mode="inprocess"` in tests that mock scanner internals).

- [ ] **Step 5: Build the docs**

Run: `.venv/bin/python -m mkdocs build --strict`
Expected: clean build, no warnings. (If `mkdocs` is missing: `pip install -e ".[docs]"` into `.venv` — never into `evals/.venv`.)

- [ ] **Step 6: Commit** (invoke `git-commit-convention` skill)

```bash
git add docs/cli.md docs/guides/mcp-server.md docs/guides/claude-code-plugin.md docs/architecture/mcp_server/architecture.md docs/architecture/plugin/architecture.md docs/api/subprocess-scan.md mkdocs.yml CLAUDE.md
git commit  # "UPD: Document subprocess scanning (CLI, server guide, plugin config, architecture)"
```

---

### Task 8: Final verification, roadmap status, PR

**Files:**
- Modify: `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` (Phase 5 **Status** line only — no eval log entry, not required for this phase)

- [ ] **Step 1: Full verification** (invoke `superpowers:verification-before-completion`)

```bash
.venv/bin/python -m pytest -q          # expect: 541 + new tests passed, 0 failed
bash tests/plugin/run_all.sh           # expect: ALL PLUGIN TESTS PASSED
.venv/bin/python -m mkdocs build --strict
```

Manual end-to-end check of the headline behavior (exit criterion 1, outside pytest):

```bash
python3 -m venv /tmp/lcp-phase5-demo --without-pip
/tmp/lcp-phase5-demo/bin/python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
# copy a trivial module into that purelib, then:
.venv/bin/python -c "
from lcp.mcp_server import resolve_library_document
doc, src = resolve_library_document('<that module>', no_cache=True, scan_python='/tmp/lcp-phase5-demo/bin/python')
print(src, len(doc.symbols))
"
rm -rf /tmp/lcp-phase5-demo
```

- [ ] **Step 2: Update the roadmap Status line** for Phase 5:

```
**Status:** done (2026-07-07) — subprocess scanning is the default
(`lcp.scanjson` machine entry point + `lcp.subprocess_scan` runner);
`.lcp.json` gains `scan_python`/`scan_timeout` (fallback: `python`);
plan: `docs/superpowers/plans/2026-07-07-phase-5-subprocess-scan.md`.
```

- [ ] **Step 3: Commit roadmap + plan** (gitignored — force-add; invoke `git-commit-convention`)

```bash
git add -f docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md docs/superpowers/plans/2026-07-07-phase-5-subprocess-scan.md
git commit  # "UPD: Phase 5 status in the roadmap"
```

- [ ] **Step 4: Push and open the PR** (title starts with `MRG:`, base `roadmap/agentic-improvements`, **no session links** — public repo)

```bash
git push -u origin roadmap/phase-5-subprocess-scan
gh pr create --base roadmap/agentic-improvements \
  --title "MRG: Phase 5 — subprocess scanning" \
  --body "$(cat <<'EOF'
## Summary
- `resolve_library` no longer imports package code into the MCP server process: live scans run `python -m lcp.scanjson` in a disposable child interpreter (exit codes 0/3/4, structured JSON on stderr, public LCP document on stdout — no private IPC format).
- Cross-venv scanning: `.lcp.json` `scan_python` (fallback: `python`) is passed through `serve.sh` as `--scan-python`, so packages installed only in the project venv now resolve even when `lcp` runs from a global install.
- `lcp serve-all` gains `--scan-mode {subprocess,inprocess}` (default subprocess), `--scan-python`, `--scan-timeout` (default 60s); in-process fallback happens only on spawn failure for the server's own environment.
- Docs aligned in-phase (CLI, server guide, plugin config, architecture, API reference); residual trust model documented honestly.

## Exit criteria
- [x] Package installed only in a second venv resolves via `scan_python` (test: `TestCrossEnvironmentScan`, `TestResolveViaSubprocess::test_resolve_via_scan_python`)
- [x] `SystemExit` at import degrades to a clean error without killing the server (test: `test_crashing_import_degrades_to_clean_error`)
- [x] Heavy scan does not freeze concurrent tool calls (test: `TestConcurrency`)

## Test plan
- `pytest`: full suite green (baseline 541 + new subprocess-scan tests, 0 failed)
- `bash tests/plugin/run_all.sh`: all plugin shell tests green
- `mkdocs build --strict`: clean
EOF
)"
```

---

## Self-Review (completed at write time)

- **Spec coverage:** machine entry point (T1), subprocess path with interpreter/timeout/captured stderr (T2–T3), cache side effect + three-step order preserved (T3 test 1), in-process fallback option + spawn-only auto-fallback (T3), real remedy in the env-mismatch error (T3), tests for happy/timeout/crash/interpreter-not-found/fallback (T2–T3), concurrency (T5), `serve.sh` pass-through (T6), docs + trust model (T7), roadmap/PR (T8). Scope-out respected: no sandboxing, no Windows launcher work (the venv fixture's `sys.platform` guard is test portability, not launcher work).
- **Placeholder scan:** none — every code step carries the full code.
- **Type consistency:** `scan_package_subprocess(package, python, timeout, extra_paths)` used identically in T2/T3; exception names (`ScanImportError`, `ScanFailedError`, `ScanTimeoutError`, `ScanInterpreterNotFoundError`, `ScanSpawnError`, `SubprocessScanError`) consistent across T2/T3; `scan_mode/scan_python/scan_timeout` kwargs identical across `resolve_library_document`/`_register_tools`/`create_universal_server`/`run_universal_server`/CLI.
