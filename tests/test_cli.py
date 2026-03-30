"""Tests for the CLI module."""

import json

import pytest
from click.testing import CliRunner

from lcp.cli import main, scan, validate_cmd


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


class TestMainGroup:
    """Tests for the main CLI group."""

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "LCP Python SDK" in result.output
        assert "scan" in result.output
        assert "validate" in result.output


class TestScanCommand:
    """Tests for the scan command."""

    def test_scan_help(self, runner):
        result = runner.invoke(main, ["scan", "--help"])
        assert result.exit_code == 0
        assert "PACKAGE" in result.output
        assert "--output" in result.output
        assert "--include-private" in result.output
        assert "--no-recursive" in result.output

    def test_scan_builtin_module(self, runner):
        result = runner.invoke(main, ["scan", "json"])
        assert result.exit_code == 0
        # Output goes to stdout, status to stderr
        output = result.output
        assert '"manifest"' in output
        assert '"symbols"' in output

    def test_scan_to_file(self, runner, temp_dir):
        output_path = temp_dir / "output.lcp.json"
        result = runner.invoke(main, ["scan", "json", "-o", str(output_path)])
        assert result.exit_code == 0
        assert output_path.exists()

        with open(output_path) as f:
            data = json.load(f)
        assert "manifest" in data
        assert "symbols" in data
        assert data["manifest"]["library"]["name"] == "json"

    def test_scan_nonexistent_package(self, runner):
        result = runner.invoke(main, ["scan", "nonexistent_package_12345"])
        assert result.exit_code == 1
        assert "Error" in result.output or "error" in result.output.lower()

    def test_scan_no_validate(self, runner):
        result = runner.invoke(main, ["scan", "json", "--no-validate"])
        assert result.exit_code == 0
        assert '"manifest"' in result.output

    def test_scan_include_private(self, runner):
        result = runner.invoke(main, ["scan", "json", "--include-private"])
        assert result.exit_code == 0
        # Should still produce valid output
        output = result.output
        assert '"manifest"' in output

    def test_scan_no_recursive(self, runner):
        result = runner.invoke(main, ["scan", "json", "--no-recursive"])
        assert result.exit_code == 0
        output = result.output
        assert '"manifest"' in output

    def test_scan_custom_indent(self, runner):
        result = runner.invoke(main, ["scan", "json", "--indent", "4"])
        assert result.exit_code == 0
        # With indent=4, there should be 4-space indentation
        lines = result.output.split("\n")
        indented_lines = [l for l in lines if l.startswith("    ")]
        assert len(indented_lines) > 0


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_help(self, runner):
        result = runner.invoke(main, ["validate", "--help"])
        assert result.exit_code == 0
        assert "FILE" in result.output

    def test_validate_valid_file(self, runner, sample_lcp_file):
        result = runner.invoke(main, ["validate", str(sample_lcp_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid_file(self, runner, temp_dir):
        invalid_path = temp_dir / "invalid.lcp.json"
        with open(invalid_path, "w") as f:
            json.dump({"manifest": {}}, f)

        result = runner.invoke(main, ["validate", str(invalid_path)])
        assert result.exit_code == 1
        assert "failed" in result.output.lower() or "error" in result.output.lower()

    def test_validate_nonexistent_file(self, runner):
        result = runner.invoke(main, ["validate", "/nonexistent/path/file.json"])
        assert result.exit_code != 0


class TestEndToEnd:
    """End-to-end tests for CLI workflow."""

    def test_scan_then_validate(self, runner, temp_dir):
        # First scan a package
        output_path = temp_dir / "collections.lcp.json"
        scan_result = runner.invoke(
            main, ["scan", "collections", "-o", str(output_path)]
        )
        assert scan_result.exit_code == 0
        assert output_path.exists()

        # Then validate the output
        validate_result = runner.invoke(main, ["validate", str(output_path)])
        assert validate_result.exit_code == 0
        assert "valid" in validate_result.output.lower()

    def test_full_workflow_with_options(self, runner, temp_dir):
        output_path = temp_dir / "json.lcp.json"
        result = runner.invoke(
            main,
            [
                "scan",
                "json",
                "-o", str(output_path),
                "--no-recursive",
                "--indent", "2",
            ],
        )
        assert result.exit_code == 0

        # Verify the output file
        with open(output_path) as f:
            data = json.load(f)

        assert data["manifest"]["schema_version"] == "1.0"
        assert data["manifest"]["library"]["name"] == "json"
        assert data["manifest"]["library"]["language"] == "python"
        assert len(data["symbols"]) > 0


class TestDiffCommand:
    """Tests for the diff command."""

    def _write_lcp(self, path, name="mylib", version="1.0.0", symbols=None):
        """Write a minimal LCP document to *path*."""
        doc = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": name, "version": version, "language": "python"},
            },
            "symbols": symbols or {},
        }
        with open(path, "w") as f:
            json.dump(doc, f)

    def test_diff_help(self, runner):
        result = runner.invoke(main, ["diff", "--help"])
        assert result.exit_code == 0
        assert "OLD" in result.output
        assert "NEW" in result.output

    def test_diff_identical_files(self, temp_dir):
        cli = CliRunner(mix_stderr=False)
        old_path = temp_dir / "old.lcp.json"
        new_path = temp_dir / "new.lcp.json"
        symbols = {"mod:func": {"kind": "function", "semantics": {"summary": "F"}}}
        self._write_lcp(old_path, version="1.0.0", symbols=symbols)
        self._write_lcp(new_path, version="2.0.0", symbols=symbols)

        result = cli.invoke(main, ["diff", str(old_path), str(new_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["summary"]["removed"] == 0
        assert data["summary"]["added"] == 0

    def test_diff_removed_symbol(self, temp_dir):
        cli = CliRunner(mix_stderr=False)
        old_path = temp_dir / "old.lcp.json"
        new_path = temp_dir / "new.lcp.json"
        self._write_lcp(
            old_path,
            version="1.0.0",
            symbols={
                "mod:a": {"kind": "function", "semantics": {"summary": "A"}},
                "mod:b": {"kind": "function", "semantics": {"summary": "B"}},
            },
        )
        self._write_lcp(
            new_path,
            version="2.0.0",
            symbols={
                "mod:a": {"kind": "function", "semantics": {"summary": "A"}},
            },
        )

        result = cli.invoke(main, ["diff", str(old_path), str(new_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["summary"]["removed"] == 1
        assert data["removed"][0]["symbol_id"] == "mod:b"
        assert data["deprecations"]["mod:b"]["deprecated_in"] == "2.0.0"

    def test_diff_to_file(self, runner, temp_dir):
        old_path = temp_dir / "old.lcp.json"
        new_path = temp_dir / "new.lcp.json"
        out_path = temp_dir / "diff.json"
        self._write_lcp(old_path, version="1.0.0")
        self._write_lcp(new_path, version="2.0.0")

        result = runner.invoke(
            main, ["diff", str(old_path), str(new_path), "-o", str(out_path)]
        )
        assert result.exit_code == 0
        assert out_path.exists()
        with open(out_path) as f:
            data = json.load(f)
        assert data["old_version"] == "1.0.0"

    def test_diff_nonexistent_old(self, runner, temp_dir):
        new_path = temp_dir / "new.lcp.json"
        self._write_lcp(new_path, version="2.0.0")
        result = runner.invoke(main, ["diff", "/nonexistent/old.json", str(new_path)])
        assert result.exit_code != 0

    def test_diff_nonexistent_new(self, runner, temp_dir):
        old_path = temp_dir / "old.lcp.json"
        self._write_lcp(old_path, version="1.0.0")
        result = runner.invoke(main, ["diff", str(old_path), "/nonexistent/new.json"])
        assert result.exit_code != 0
