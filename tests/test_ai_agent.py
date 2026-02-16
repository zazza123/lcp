"""Tests for the AI agent module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lcp.ai.agent import DocGenAgent
from lcp.ai.models import DocGenConfig, DocGenResult, LLMResponse, TokenUsage
from lcp.ai.prompts import build_system_prompt, build_user_prompt, build_user_prompt_hierarchical
from lcp.ai.provider import LLMProvider


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, response_text: str = "A generated docstring."):
        self._response_text = response_text
        self.call_count = 0

    @property
    def name(self) -> str:
        return "mock"

    def generate(self, system: str, prompt: str) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            content=self._response_text,
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )

    async def agenerate(self, system: str, prompt: str) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            content=self._response_text,
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )


SAMPLE_SOURCE = '''\
def undocumented_func(x, y):
    return x + y


class MyClass:
    def undocumented_method(self, val):
        return val * 2
'''


@pytest.fixture
def source_file(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(SAMPLE_SOURCE, encoding="utf-8")
    return path


@pytest.fixture
def coverage_data(source_file):
    return {
        "package": "test_pkg",
        "version": "1.0.0",
        "summary": {
            "total_symbols": 3,
            "documented": 0,
            "undocumented": 3,
        },
        "undocumented": [
            {
                "kind": "function",
                "module": "test_pkg",
                "entity": "undocumented_func",
                "source_file": str(source_file),
            },
            {
                "kind": "method",
                "module": "test_pkg",
                "entity": "MyClass#undocumented_method",
                "source_file": str(source_file),
            },
        ],
    }


@pytest.fixture
def coverage_file(tmp_path, coverage_data):
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(coverage_data), encoding="utf-8")
    return path


class TestDocGenAgent:
    """Tests for DocGenAgent."""

    def test_run_with_dict(self, coverage_data):
        provider = MockProvider()
        agent = DocGenAgent(provider=provider)
        result = agent.run(coverage_data)

        assert isinstance(result, DocGenResult)
        assert result.symbols_processed == 2
        assert result.symbols_updated == 2
        assert provider.call_count == 2

    def test_run_with_file(self, coverage_file):
        provider = MockProvider()
        agent = DocGenAgent(provider=provider)
        result = agent.run(str(coverage_file))

        assert isinstance(result, DocGenResult)
        assert result.symbols_processed == 2

    def test_run_dry_run(self, coverage_data):
        provider = MockProvider()
        config = DocGenConfig(dry_run=True)
        agent = DocGenAgent(provider=provider, config=config)
        result = agent.run(coverage_data)

        assert result.symbols_updated == 2
        for r in result.results:
            assert r.status == "dry_run"

    def test_run_filter_kinds(self, coverage_data):
        provider = MockProvider()
        config = DocGenConfig(kinds=["function"])
        agent = DocGenAgent(provider=provider, config=config)
        result = agent.run(coverage_data)

        assert result.symbols_processed == 1
        assert provider.call_count == 1

    def test_run_empty_coverage(self):
        provider = MockProvider()
        agent = DocGenAgent(provider=provider)
        result = agent.run({"undocumented": []})

        assert result.symbols_processed == 0
        assert result.symbols_updated == 0
        assert provider.call_count == 0

    def test_run_no_source_file(self):
        provider = MockProvider()
        agent = DocGenAgent(provider=provider)
        coverage = {
            "undocumented": [
                {
                    "kind": "function",
                    "module": "test_pkg",
                    "entity": "some_func",
                }
            ]
        }
        result = agent.run(coverage)

        assert result.symbols_processed == 1
        assert result.symbols_skipped == 1
        assert result.results[0].status == "skipped"

    def test_token_aggregation(self, coverage_data):
        provider = MockProvider()
        agent = DocGenAgent(provider=provider)
        result = agent.run(coverage_data)

        assert result.total_usage.input_tokens == 200  # 2 * 100
        assert result.total_usage.output_tokens == 100  # 2 * 50

    def test_docstring_written_to_file(self, coverage_data, source_file):
        provider = MockProvider(response_text="Add two values together.")
        agent = DocGenAgent(provider=provider)
        result = agent.run(coverage_data)

        content = source_file.read_text(encoding="utf-8")
        assert '"""Add two values together."""' in content

    def test_provider_error_handled(self, coverage_data):
        provider = MagicMock(spec=LLMProvider)
        provider.name = "mock"
        provider.generate.side_effect = RuntimeError("API error")

        agent = DocGenAgent(provider=provider)
        result = agent.run(coverage_data)

        assert result.symbols_failed == 2
        for r in result.results:
            assert r.status == "failed"
            assert "API error" in r.error


class TestFilterSymbols:
    """Tests for _filter_symbols."""

    def test_no_filter(self):
        provider = MockProvider()
        agent = DocGenAgent(provider=provider)
        symbols = [
            {"kind": "function"},
            {"kind": "class"},
            {"kind": "method"},
        ]
        result = agent._filter_symbols(symbols)
        assert len(result) == 3

    def test_filter_single_kind(self):
        provider = MockProvider()
        config = DocGenConfig(kinds=["function"])
        agent = DocGenAgent(provider=provider, config=config)
        symbols = [
            {"kind": "function"},
            {"kind": "class"},
            {"kind": "method"},
        ]
        result = agent._filter_symbols(symbols)
        assert len(result) == 1
        assert result[0]["kind"] == "function"

    def test_filter_multiple_kinds(self):
        provider = MockProvider()
        config = DocGenConfig(kinds=["function", "class"])
        agent = DocGenAgent(provider=provider, config=config)
        symbols = [
            {"kind": "function"},
            {"kind": "class"},
            {"kind": "method"},
        ]
        result = agent._filter_symbols(symbols)
        assert len(result) == 2


class TestBuildPrompts:
    """Tests for prompt building functions."""

    def test_system_prompt_default(self):
        prompt = build_system_prompt()
        assert "google" in prompt
        assert "documentation expert" in prompt

    def test_system_prompt_with_description(self):
        prompt = build_system_prompt(description="A web framework")
        assert "A web framework" in prompt

    def test_user_prompt(self):
        prompt = build_user_prompt(
            kind="function",
            module="mymod",
            entity="my_func",
            source_context="def my_func(x): return x",
        )
        assert "function" in prompt
        assert "mymod" in prompt
        assert "my_func" in prompt
        assert "def my_func(x): return x" in prompt


class TestHierarchicalPrompts:
    """Tests for hierarchical prompt building."""

    def test_level0_delegates_to_existing(self):
        from lcp.ai.hierarchy import SymbolNode, LEVEL_LEAF

        node = SymbolNode(
            symbol={"kind": "function", "module": "mod", "entity": "func", "source_file": "/p.py"},
            kind="function",
            level=LEVEL_LEAF,
        )
        context = "def func(x): return x"
        prompt = build_user_prompt_hierarchical(node, context)
        assert "function" in prompt
        assert "mod" in prompt
        assert "func" in prompt
        assert "def func(x): return x" in prompt

    def test_level1_class_prompt(self):
        from lcp.ai.hierarchy import SymbolNode, LEVEL_CLASS

        node = SymbolNode(
            symbol={"kind": "class", "module": "mod", "entity": "MyClass", "source_file": "/p.py"},
            kind="class",
            level=LEVEL_CLASS,
        )
        context = "class MyClass:\n    def method(self): ..."
        prompt = build_user_prompt_hierarchical(node, context)
        assert "class" in prompt
        assert "MyClass" in prompt
        assert "Class structure:" in prompt
        assert "members" in prompt.lower()

    def test_level2_module_prompt(self):
        from lcp.ai.hierarchy import SymbolNode, LEVEL_MODULE

        node = SymbolNode(
            symbol={"kind": "module", "module": "pkg.mod", "entity": "pkg.mod", "source_file": "/p.py"},
            kind="module",
            level=LEVEL_MODULE,
        )
        context = "import os\n\n# Module components:\n- class Foo: \"A foo.\""
        prompt = build_user_prompt_hierarchical(node, context)
        assert "module" in prompt
        assert "pkg.mod" in prompt
        assert "import os" in prompt
        assert "components" in prompt.lower()
