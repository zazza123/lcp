"""Tests for Phase 5 subprocess scanning: lcp.scanjson + lcp.subprocess_scan.

The scan child speaks the public LCP document format on stdout; errors are a
single JSON object on stderr plus a distinguishing exit code (0 ok /
3 import failure / 4 scan failure).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import venv
from pathlib import Path

import pytest

from lcp.mcp_server import create_universal_server, resolve_library_document
from lcp.subprocess_scan import (
    DEFAULT_SCAN_TIMEOUT,
    ScanFailedError,
    ScanImportError,
    ScanInterpreterNotFoundError,
    ScanSpawnError,
    ScanTimeoutError,
    scan_package_subprocess,
)

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


class TestScanPackageSubprocess:
    """Server-side runner: spawn, parse, classify failures."""

    def test_happy_path_returns_document(self):
        doc = scan_package_subprocess(
            "sample_package", extra_paths=[str(TESTS_DIR)]
        ).document
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
        ).document
        assert "secondvenv_only_pkg:greet" in doc.symbols


class TestResolveViaSubprocess:
    """resolve_library_document defaults to the subprocess path."""

    def test_scan_runs_in_subprocess_and_preserves_cache_side_effect(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(TESTS_DIR)  # child inherits cwd → fixtures importable
        cache_dir = tmp_path / "cache"
        doc, source = resolve_library_document("sample_package", cache_dir=cache_dir)
        doc = doc.document
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
        doc = doc.document
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
        doc = doc.document
        assert source == "scan"
        assert len(doc.symbols) > 0

    def test_spawn_failure_falls_back_inprocess_for_own_env(
        self, tmp_path, monkeypatch
    ):
        def blocked(*args, **kwargs):
            raise ScanSpawnError("spawn blocked")

        monkeypatch.setattr("lcp.mcp_server.scan_package_subprocess", blocked)
        result, source = resolve_library_document(
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
            doc = doc.document
            assert len(doc.symbols) > 0
            assert not slow_done.is_set(), (
                "quick resolve should complete while the slow scan is running"
            )
        finally:
            thread.join(timeout=30)


class TestChildCodeIsolation:
    """The child bootstrap must not leak host packages or import pydantic (#52)."""

    def test_child_code_never_imports_lcp_or_pydantic(self):
        from lcp.subprocess_scan import _build_child_code

        code = _build_child_code([])
        assert "from lcp" not in code
        assert "import lcp" not in code
        assert "pydantic" not in code

    def test_child_code_adds_only_extra_paths_to_syspath(self):
        from lcp.subprocess_scan import _build_child_code

        assert "sys.path[:0] = []" in _build_child_code([])
        assert "sys.path[:0] = ['/tmp/fixtures']" in _build_child_code(["/tmp/fixtures"])


@pytest.fixture(scope="module")
def bare_target_venv(tmp_path_factory) -> str:
    """A pip-less venv (stdlib only) used as an isolated scan target."""
    root = tmp_path_factory.mktemp("bare-target")
    try:
        venv.create(root, with_pip=False)
    except Exception as exc:  # pragma: no cover - CI/platform guard
        pytest.skip(f"cannot create venv: {exc}")
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    vpy = root / bin_dir / ("python.exe" if sys.platform == "win32" else "python")
    if not vpy.exists():  # pragma: no cover - platform guard
        pytest.skip("venv python interpreter missing")
    return str(vpy)


class TestHostLeakIsolation:
    """Host site-packages must not make target submodules importable (#52)."""

    def test_host_only_package_does_not_leak_into_target(
        self, bare_target_venv, tmp_path
    ):
        # pytest is importable in the host but NOT in the pip-less target venv.
        pkg = tmp_path / "contam_pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(
            '"""Root package."""\n\n'
            "def core():\n"
            '    """Core function."""\n'
            "    return 1\n",
            encoding="utf-8",
        )
        (pkg / "opt.py").write_text(
            '"""Optional submodule that needs a host-only package."""\n\n'
            "import pytest  # only importable if the host env leaks in\n\n"
            "def optional_fn():\n"
            '    """Should never be scanned in an isolated child."""\n'
            "    return 2\n",
            encoding="utf-8",
        )

        doc = scan_package_subprocess(
            "contam_pkg", python=bare_target_venv, extra_paths=[str(tmp_path)]
        ).document

        assert "contam_pkg:core" in doc.symbols
        assert not any(sid.startswith("contam_pkg.opt") for sid in doc.symbols)


class TestUnresolvedReexportsPropagate:
    """The diagnostic must survive the child-to-host JSON hop."""

    def test_subprocess_scan_reports_unresolved(self):
        from lcp.subprocess_scan import scan_package_subprocess

        result = scan_package_subprocess(
            "sample_package.convenience", extra_paths=[str(TESTS_DIR)]
        )

        assert result.unresolved_reexports == [("sample_package.core", 2, 1)]
        assert result.document.manifest.library.name == "sample_package.convenience"
