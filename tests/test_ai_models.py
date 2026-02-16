"""Tests for the AI models module."""

from lcp.ai.models import (
    DocGenConfig,
    DocGenResult,
    HierarchicalConfig,
    LLMResponse,
    SymbolResult,
    TokenUsage,
)


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_defaults(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_tokens == 0
        assert usage.reasoning_tokens == 0

    def test_add(self):
        a = TokenUsage(input_tokens=10, output_tokens=5, cache_tokens=2, reasoning_tokens=1)
        b = TokenUsage(input_tokens=20, output_tokens=10, cache_tokens=3, reasoning_tokens=4)
        result = a + b
        assert result.input_tokens == 30
        assert result.output_tokens == 15
        assert result.cache_tokens == 5
        assert result.reasoning_tokens == 5

    def test_add_with_defaults(self):
        a = TokenUsage(input_tokens=10)
        b = TokenUsage()
        result = a + b
        assert result.input_tokens == 10
        assert result.output_tokens == 0


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_creation(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        response = LLMResponse(content="Hello", usage=usage)
        assert response.content == "Hello"
        assert response.usage.input_tokens == 100


class TestHierarchicalConfig:
    """Tests for HierarchicalConfig dataclass."""

    def test_defaults(self):
        config = HierarchicalConfig()
        # Inherited from DocGenConfig
        assert config.kinds is None
        assert config.description is None
        assert config.docstring_style == "google"
        assert config.dry_run is False
        # New fields
        assert config.max_workers == 4
        assert config.flat_mode is False
        assert config.failure_threshold == 0.5

    def test_custom(self):
        config = HierarchicalConfig(
            kinds=["class"],
            dry_run=True,
            max_workers=8,
            flat_mode=True,
            failure_threshold=0.75,
        )
        assert config.kinds == ["class"]
        assert config.dry_run is True
        assert config.max_workers == 8
        assert config.flat_mode is True
        assert config.failure_threshold == 0.75

    def test_is_subclass_of_docgen_config(self):
        config = HierarchicalConfig()
        assert isinstance(config, DocGenConfig)


class TestDocGenConfig:
    """Tests for DocGenConfig dataclass."""

    def test_defaults(self):
        config = DocGenConfig()
        assert config.kinds is None
        assert config.description is None
        assert config.docstring_style == "google"
        assert config.dry_run is False

    def test_custom(self):
        config = DocGenConfig(
            kinds=["class", "function"],
            description="A library for X",
            dry_run=True,
        )
        assert config.kinds == ["class", "function"]
        assert config.description == "A library for X"
        assert config.dry_run is True


class TestSymbolResult:
    """Tests for SymbolResult dataclass."""

    def test_creation(self):
        result = SymbolResult(
            symbol_id="mod:func",
            kind="function",
            source_file="/path/to/file.py",
            status="updated",
            docstring="A function.",
        )
        assert result.symbol_id == "mod:func"
        assert result.status == "updated"
        assert result.error is None

    def test_failed_result(self):
        result = SymbolResult(
            symbol_id="mod:func",
            kind="function",
            source_file="/path/to/file.py",
            status="failed",
            error="Connection error",
        )
        assert result.status == "failed"
        assert result.error == "Connection error"


class TestDocGenResult:
    """Tests for DocGenResult dataclass."""

    def test_creation(self):
        result = DocGenResult(
            symbols_processed=10,
            symbols_updated=7,
            symbols_skipped=2,
            symbols_failed=1,
            total_usage=TokenUsage(input_tokens=1000, output_tokens=500),
        )
        assert result.symbols_processed == 10
        assert result.symbols_updated == 7
        assert result.results == []

    def test_with_results(self):
        sym_result = SymbolResult(
            symbol_id="mod:func",
            kind="function",
            source_file=None,
            status="updated",
        )
        result = DocGenResult(
            symbols_processed=1,
            symbols_updated=1,
            symbols_skipped=0,
            symbols_failed=0,
            total_usage=TokenUsage(),
            results=[sym_result],
        )
        assert len(result.results) == 1
