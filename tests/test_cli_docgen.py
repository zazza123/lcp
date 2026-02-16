"""Tests for docgen CLI command flags."""

from click.testing import CliRunner

from lcp.cli import main


class TestDocgenCLIFlags:
    """Test that new CLI flags are accepted."""

    def test_workers_flag_accepted(self, tmp_path):
        cov = tmp_path / "cov.json"
        cov.write_text('{"undocumented": []}', encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(main, ["docgen", str(cov), "--workers", "2", "--dry-run"])
        assert "no such option" not in (result.output or "").lower()

    def test_failure_threshold_flag_accepted(self, tmp_path):
        cov = tmp_path / "cov.json"
        cov.write_text('{"undocumented": []}', encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(main, ["docgen", str(cov), "--failure-threshold", "0.75", "--dry-run"])
        assert "no such option" not in (result.output or "").lower()
