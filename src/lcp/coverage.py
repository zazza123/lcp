"""Coverage module for analyzing documentation completeness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .scanner import ScannedModule, ScannedSymbol, scan_package


@dataclass
class UndocumentedSymbol:
    """A symbol missing documentation."""

    kind: str
    module: str
    entity: str
    source_file: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "kind": self.kind,
            "module": self.module,
            "entity": self.entity,
        }
        if self.source_file:
            result["source_file"] = self.source_file
        return result


@dataclass
class KindStats:
    """Statistics for a specific symbol kind."""

    total: int = 0
    documented: int = 0
    undocumented: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total": self.total,
            "documented": self.documented,
            "undocumented": self.undocumented,
        }


@dataclass
class CoverageSummary:
    """Summary of documentation coverage."""

    total_symbols: int = 0
    documented: int = 0
    undocumented: int = 0
    coverage_percent: float = 0.0
    by_kind: dict[str, KindStats] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_symbols": self.total_symbols,
            "documented": self.documented,
            "undocumented": self.undocumented,
            "coverage_percent": round(self.coverage_percent, 1),
            "by_kind": {k: v.to_dict() for k, v in self.by_kind.items()},
        }


@dataclass
class CoverageReport:
    """Documentation coverage report for a package."""

    package: str
    version: str
    generated_at: datetime
    summary: CoverageSummary
    undocumented: list[UndocumentedSymbol] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary suitable for JSON serialization."""
        return {
            "package": self.package,
            "version": self.version,
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary.to_dict(),
            "undocumented": [s.to_dict() for s in self.undocumented],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        lines = [
            "# Documentation Coverage Report",
            "",
            f"**Package:** {self.package}  ",
            f"**Version:** {self.version}  ",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
            "| Kind | Total | Documented | Undocumented | Coverage |",
            "|------|-------|------------|--------------|----------|",
        ]

        # Add rows for each kind
        for kind, stats in sorted(self.summary.by_kind.items()):
            if stats.total > 0:
                coverage = (stats.documented / stats.total) * 100
                lines.append(
                    f"| {kind} | {stats.total} | {stats.documented} | "
                    f"{stats.undocumented} | {coverage:.1f}% |"
                )

        # Add total row
        lines.append(
            f"| **Total** | **{self.summary.total_symbols}** | "
            f"**{self.summary.documented}** | **{self.summary.undocumented}** | "
            f"**{self.summary.coverage_percent:.1f}%** |"
        )

        # Add undocumented symbols section
        if self.undocumented:
            lines.extend(["", "## Undocumented Symbols", ""])

            # Group by kind
            by_kind: dict[str, list[UndocumentedSymbol]] = {}
            for symbol in self.undocumented:
                by_kind.setdefault(symbol.kind, []).append(symbol)

            for kind in sorted(by_kind.keys()):
                symbols = by_kind[kind]
                kind_title = kind.capitalize() + "s" if not kind.endswith("s") else kind.capitalize()
                lines.extend([f"### {kind_title} ({len(symbols)})", ""])

                for symbol in symbols:
                    source_info = f" - `{symbol.source_file}`" if symbol.source_file else ""
                    lines.append(f"- `{symbol.module}:{symbol.entity}`{source_info}")

                lines.append("")

        return "\n".join(lines)

    def to_file(self, path: str, format: str | None = None) -> None:
        """Write report to a file.

        Args:
            path: Output file path.
            format: Output format ('json' or 'markdown'). If None, inferred from extension.
        """
        if format is None:
            format = "markdown" if path.endswith(".md") else "json"

        content = self.to_markdown() if format == "markdown" else self.to_json()

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def _is_documented(symbol: ScannedSymbol) -> bool:
    """Check if a symbol has documentation."""
    return symbol.summary is not None and not symbol.summary.startswith("Module ")


def _analyze_symbol(
    symbol: ScannedSymbol,
    stats: dict[str, KindStats],
    undocumented: list[UndocumentedSymbol],
) -> None:
    """Analyze a single symbol and update stats."""
    kind = symbol.kind

    if kind not in stats:
        stats[kind] = KindStats()

    stats[kind].total += 1

    if _is_documented(symbol):
        stats[kind].documented += 1
    else:
        stats[kind].undocumented += 1
        undocumented.append(
            UndocumentedSymbol(
                kind=kind,
                module=symbol.module_path,
                entity=symbol.qualified_name or symbol.name,
                source_file=symbol.source_file,
            )
        )

    # Analyze members (for classes)
    for member in symbol.members:
        _analyze_symbol(member, stats, undocumented)


def _analyze_coverage(scanned: ScannedModule) -> CoverageReport:
    """Analyze documentation coverage from scanned module data."""
    stats: dict[str, KindStats] = {}
    undocumented: list[UndocumentedSymbol] = []

    for symbol in scanned.symbols:
        _analyze_symbol(symbol, stats, undocumented)

    # Calculate totals
    total = sum(s.total for s in stats.values())
    documented = sum(s.documented for s in stats.values())
    undocumented_count = sum(s.undocumented for s in stats.values())
    coverage_percent = (documented / total * 100) if total > 0 else 100.0

    summary = CoverageSummary(
        total_symbols=total,
        documented=documented,
        undocumented=undocumented_count,
        coverage_percent=coverage_percent,
        by_kind=stats,
    )

    return CoverageReport(
        package=scanned.name,
        version=scanned.version,
        generated_at=datetime.now(timezone.utc),
        summary=summary,
        undocumented=undocumented,
    )


def generate_coverage(
    package_name: str,
    include_private: bool = False,
    recursive: bool = True,
) -> CoverageReport:
    """Generate documentation coverage report for a package.

    Args:
        package_name: The name of an installed Python package to analyze.
        include_private: Include private symbols (starting with _).
        recursive: Scan submodules recursively.

    Returns:
        A CoverageReport containing coverage statistics and undocumented symbols.

    Raises:
        ImportError: If the package cannot be imported.

    Example:
        >>> from lcp import generate_coverage
        >>> report = generate_coverage("requests")
        >>> print(f"Coverage: {report.summary.coverage_percent}%")
        >>> report.to_file("coverage.json")
    """
    scanned = scan_package(package_name, include_private, recursive)
    return _analyze_coverage(scanned)


def generate_coverage_from_scanned(scanned: ScannedModule) -> CoverageReport:
    """Generate coverage report from already scanned module data.

    This is useful when you want to generate both LCP and coverage
    from the same scan, avoiding duplicate work.

    Args:
        scanned: Pre-scanned module data from scan_package().

    Returns:
        A CoverageReport containing coverage statistics.
    """
    return _analyze_coverage(scanned)
