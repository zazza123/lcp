"""Tests for the CLI module."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from lcp.cli import main


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
        indented_lines = [line for line in lines if line.startswith("    ")]
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

    def test_diff_update_flag(self, runner, temp_dir):
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

        result = runner.invoke(
            main, ["diff", str(old_path), str(new_path), "--update"]
        )
        assert result.exit_code == 0

        # Verify the new file was updated with deprecation entries
        with open(new_path) as f:
            data = json.load(f)
        assert "deprecations" in data
        assert "mod:b" in data["deprecations"]
        assert data["deprecations"]["mod:b"]["deprecated_in"] == "2.0.0"

    def test_diff_update_preserves_existing(self, runner, temp_dir):
        old_path = temp_dir / "old.lcp.json"
        new_path = temp_dir / "new.lcp.json"
        self._write_lcp(old_path, version="1.0.0", symbols={
            "mod:a": {"kind": "function", "semantics": {"summary": "A"}},
        })
        # Write new file with an existing deprecation entry
        doc = {
            "manifest": {
                "schema_version": "1.0",
                "library": {"name": "mylib", "version": "2.0.0", "language": "python"},
            },
            "symbols": {},
            "deprecations": {
                "mod:old": {"deprecated_in": "1.5.0", "notes": "Existing"},
            },
        }
        with open(new_path, "w") as f:
            json.dump(doc, f)

        result = runner.invoke(
            main, ["diff", str(old_path), str(new_path), "--update"]
        )
        assert result.exit_code == 0

        with open(new_path) as f:
            data = json.load(f)
        # Both old and new deprecation entries should be present
        assert data["deprecations"]["mod:old"]["deprecated_in"] == "1.5.0"
        assert data["deprecations"]["mod:old"]["notes"] == "Existing"
        assert data["deprecations"]["mod:a"]["deprecated_in"] == "2.0.0"

    def test_diff_update_no_changes(self, runner, temp_dir):
        """--update with no removed symbols should not add deprecations."""
        old_path = temp_dir / "old.lcp.json"
        new_path = temp_dir / "new.lcp.json"
        symbols = {"mod:a": {"kind": "function", "semantics": {"summary": "A"}}}
        self._write_lcp(old_path, version="1.0.0", symbols=symbols)
        self._write_lcp(new_path, version="2.0.0", symbols=symbols)

        result = runner.invoke(
            main, ["diff", str(old_path), str(new_path), "--update"]
        )
        assert result.exit_code == 0

        # File should not gain a deprecations key
        with open(new_path) as f:
            data = json.load(f)
        assert "deprecations" not in data


class TestServeAllCommand:
    """Tests for the serve-all CLI command."""

    def test_help(self, runner):
        """Should display help without error."""
        result = runner.invoke(main, ["serve-all", "--help"])
        assert result.exit_code == 0
        assert "resolve_library" in result.output
        assert "--cache-dir" in result.output
        assert "--no-cache" in result.output


class TestPublishCommand:
    """Tests for the publish command."""

    def test_publish_help(self, runner):
        result = runner.invoke(main, ["publish", "--help"])
        assert result.exit_code == 0
        assert "PACKAGE" in result.output
        assert "--token" in result.output
        assert "--registry-repo" in result.output
        assert "--dry-run" in result.output
        assert "--file" in result.output

    def test_publish_dry_run(self, runner):
        """Dry run should scan and display info without creating a PR."""
        result = runner.invoke(main, ["publish", "json", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "json" in result.output
        assert "new_manifest" in result.output

    def test_publish_dry_run_with_file(self, runner, sample_lcp_file):
        """Dry run with --file should load the manifest instead of scanning."""
        result = runner.invoke(
            main, ["publish", "test-lib", "--dry-run", "--file", str(sample_lcp_file)]
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "test-lib" in result.output

    def test_publish_no_token(self, runner):
        """Publishing without a token should fail."""
        result = runner.invoke(main, ["publish", "json"])
        assert result.exit_code == 1
        assert "token" in result.output.lower()

    def test_publish_nonexistent_package(self, runner):
        """Publishing a nonexistent package should fail."""
        result = runner.invoke(
            main, ["publish", "nonexistent_pkg_12345", "--dry-run"]
        )
        assert result.exit_code == 1
        assert "Error" in result.output or "error" in result.output.lower()

    @patch("lcp.cli.publish_manifest")
    def test_publish_success(self, mock_publish, runner):
        """Successful publish should show PR URL."""
        from lcp.publish import PublishResult

        mock_publish.return_value = PublishResult(
            pr_url="https://github.com/zazza123/lcp-registry/pull/42",
            pr_number=42,
            manifest_path="manifests/python/j/json/0.1.0.lcp.json.gz",
            package_name="json",
            package_version="0.1.0",
            language="python",
        )
        result = runner.invoke(
            main, ["publish", "json", "--token", "ghp_fake_token"]
        )
        assert result.exit_code == 0
        assert "Pull request created successfully" in result.output
        assert "pull/42" in result.output

    @patch("lcp.cli.publish_manifest")
    def test_publish_api_error(self, mock_publish, runner):
        """PublishError should be caught and displayed."""
        from lcp.publish import PublishError

        mock_publish.side_effect = PublishError("GitHub API error (HTTP 422): already exists")
        result = runner.invoke(
            main, ["publish", "json", "--token", "ghp_fake_token"]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output
