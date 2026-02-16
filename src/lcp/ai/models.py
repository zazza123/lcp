"""Data models for the AI documentation generation module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    """Token usage statistics from an LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    reasoning_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_tokens=self.cache_tokens + other.cache_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    usage: TokenUsage


@dataclass
class DocGenConfig:
    """Configuration for documentation generation."""

    kinds: list[str] | None = None
    description: str | None = None
    docstring_style: str = "google"
    dry_run: bool = False


@dataclass
class HierarchicalConfig(DocGenConfig):
    """Configuration for hierarchical documentation generation.

    Extends DocGenConfig with parameters controlling the hierarchical
    bottom-up processing mode and async parallelism.
    """

    max_workers: int = 4
    flat_mode: bool = False
    failure_threshold: float = 0.5


@dataclass
class SymbolResult:
    """Result of processing a single symbol."""

    symbol_id: str
    kind: str
    source_file: str | None
    status: str  # "updated", "skipped", "failed", "dry_run"
    docstring: str | None = None
    usage: TokenUsage | None = None
    error: str | None = None


@dataclass
class DocGenResult:
    """Result of a documentation generation run."""

    symbols_processed: int
    symbols_updated: int
    symbols_skipped: int
    symbols_failed: int
    total_usage: TokenUsage
    results: list[SymbolResult] = field(default_factory=list)
