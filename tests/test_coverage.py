"""Tests for the coverage module."""

import json
import tempfile
from pathlib import Path


from lcp import generate_coverage, CoverageReport, CoverageSummary, UndocumentedSymbol
from lcp.coverage import generate_coverage_from_scanned
from lcp.scanner import scan_package


class TestGenerateCoverage:
    """Tests for generate_coverage function."""

    def test_basic_report_structure(self):
        """Test that generate_coverage returns a valid CoverageReport."""
        report = generate_coverage("tests.sample_module", recursive=False)

        assert isinstance(report, CoverageReport)
        assert report.package == "tests.sample_module"
        assert report.version is not None
        assert report.generated_at is not None
        assert isinstance(report.summary, CoverageSummary)

    def test_summary_totals(self):
        """Test that summary totals are calculated correctly."""
        report = generate_coverage("tests.sample_module", recursive=False)

        assert report.summary.total_symbols > 0
        assert report.summary.documented >= 0
        assert report.summary.undocumented >= 0
        assert report.summary.documented + report.summary.undocumented == report.summary.total_symbols

    def test_coverage_percent(self):
        """Test that coverage percentage is valid."""
        report = generate_coverage("tests.sample_module", recursive=False)

        assert 0 <= report.summary.coverage_percent <= 100
        if report.summary.total_symbols > 0:
            expected = (report.summary.documented / report.summary.total_symbols) * 100
            assert abs(report.summary.coverage_percent - expected) < 0.1

    def test_by_kind_stats(self):
        """Test that by_kind statistics are present."""
        report = generate_coverage("tests.sample_module", recursive=False)

        assert len(report.summary.by_kind) > 0
        for kind, stats in report.summary.by_kind.items():
            assert stats.total >= 0
            assert stats.documented >= 0
            assert stats.undocumented >= 0
            assert stats.documented + stats.undocumented == stats.total

    def test_undocumented_symbols_detected(self):
        """Test that undocumented symbols are detected."""
        report = generate_coverage("tests.sample_module", recursive=False)

        # sample_module has ClassWithoutDocstring and method_without_docstring
        undoc_entities = [s.entity for s in report.undocumented]

        assert "ClassWithoutDocstring" in undoc_entities
        assert "ClassWithoutDocstring#method_without_docstring" in undoc_entities

    def test_undocumented_symbol_structure(self):
        """Test that UndocumentedSymbol has correct structure."""
        report = generate_coverage("tests.sample_module", recursive=False)

        for symbol in report.undocumented:
            assert isinstance(symbol, UndocumentedSymbol)
            assert symbol.kind in ("module", "class", "function", "method", "attribute", "constant")
            assert symbol.module is not None
            assert symbol.entity is not None


class TestGenerateCoverageFromScanned:
    """Tests for generate_coverage_from_scanned function."""

    def test_same_results_as_generate_coverage(self):
        """Test that generate_coverage_from_scanned produces consistent results."""
        # Generate via both methods
        report1 = generate_coverage("tests.sample_module", recursive=False)

        scanned = scan_package("tests.sample_module", recursive=False)
        report2 = generate_coverage_from_scanned(scanned)

        # Compare (excluding generated_at which will differ)
        assert report1.package == report2.package
        assert report1.summary.total_symbols == report2.summary.total_symbols
        assert report1.summary.documented == report2.summary.documented
        assert report1.summary.undocumented == report2.summary.undocumented


class TestCoverageReportOutput:
    """Tests for CoverageReport output methods."""

    def test_to_dict(self):
        """Test that to_dict produces valid dictionary."""
        report = generate_coverage("tests.sample_module", recursive=False)
        data = report.to_dict()

        assert isinstance(data, dict)
        assert "package" in data
        assert "version" in data
        assert "generated_at" in data
        assert "summary" in data
        assert "undocumented" in data

    def test_to_json(self):
        """Test that to_json produces valid JSON."""
        report = generate_coverage("tests.sample_module", recursive=False)
        json_str = report.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert data["package"] == "tests.sample_module"

    def test_to_json_with_indent(self):
        """Test that to_json respects indent parameter."""
        report = generate_coverage("tests.sample_module", recursive=False)

        json_2 = report.to_json(indent=2)
        json_4 = report.to_json(indent=4)

        # Both should be valid
        json.loads(json_2)
        json.loads(json_4)

        # 4-space indent should be longer
        assert len(json_4) > len(json_2)

    def test_to_markdown(self):
        """Test that to_markdown produces valid markdown."""
        report = generate_coverage("tests.sample_module", recursive=False)
        md = report.to_markdown()

        # Check for expected sections
        assert "# Documentation Coverage Report" in md
        assert "**Package:**" in md
        assert "## Summary" in md
        assert "| Kind | Total |" in md
        assert "| **Total** |" in md

    def test_to_markdown_with_undocumented(self):
        """Test that markdown includes undocumented symbols section."""
        report = generate_coverage("tests.sample_module", recursive=False)
        md = report.to_markdown()

        if report.undocumented:
            assert "## Undocumented Symbols" in md

    def test_to_file_json(self):
        """Test writing to JSON file."""
        report = generate_coverage("tests.sample_module", recursive=False)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            report.to_file(path)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["package"] == "tests.sample_module"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_to_file_markdown(self):
        """Test writing to Markdown file."""
        report = generate_coverage("tests.sample_module", recursive=False)

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path = f.name

        try:
            report.to_file(path)

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "# Documentation Coverage Report" in content
        finally:
            Path(path).unlink(missing_ok=True)

    def test_to_file_explicit_format(self):
        """Test that explicit format overrides extension inference."""
        report = generate_coverage("tests.sample_module", recursive=False)

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name

        try:
            report.to_file(path, format="markdown")

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "# Documentation Coverage Report" in content
        finally:
            Path(path).unlink(missing_ok=True)


class TestIncludePrivate:
    """Tests for include_private option."""

    def test_private_excluded_by_default(self):
        """Test that private symbols are excluded by default."""
        report = generate_coverage("tests.sample_module", recursive=False)

        entities = [s.entity for s in report.undocumented]
        # _private_function should not be in the report
        assert "_private_function" not in entities

    def test_private_included_when_requested(self):
        """Test that private symbols are included when requested."""
        report = generate_coverage("tests.sample_module", include_private=True, recursive=False)

        # With include_private, we should have more symbols
        report_without = generate_coverage("tests.sample_module", include_private=False, recursive=False)

        assert report.summary.total_symbols >= report_without.summary.total_symbols
