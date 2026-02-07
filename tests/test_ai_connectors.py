"""Tests for the AI connectors module."""

from unittest.mock import MagicMock, patch

import pytest

from lcp.ai.connectors.openai import OpenAIProvider
from lcp.ai.connectors.anthropic import AnthropicProvider
from lcp.ai.models import LLMResponse, TokenUsage


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_name(self):
        provider = OpenAIProvider(api_key="test-key")
        assert provider.name == "openai"

    def test_default_model(self):
        provider = OpenAIProvider(api_key="test-key")
        assert provider._model == "gpt-4o"

    def test_custom_model(self):
        provider = OpenAIProvider(model="gpt-4o-mini", api_key="test-key")
        assert provider._model == "gpt-4o-mini"

    def test_api_key_from_env(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider()
            assert provider._api_key == "env-key"

    def test_api_key_precedence(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider(api_key="explicit-key")
            assert provider._api_key == "explicit-key"

    def test_reasoning_flag(self):
        provider = OpenAIProvider(api_key="test-key", reasoning=True)
        assert provider._reasoning is True

    def test_lazy_import_error(self):
        provider = OpenAIProvider(api_key="test-key")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                provider._get_client()

    @patch("lcp.ai.connectors.openai.OpenAIProvider._get_client")
    def test_generate_standard(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.prompt_tokens_details = None
        mock_usage.completion_tokens_details = None

        mock_choice = MagicMock()
        mock_choice.message.content = "Generated docstring"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(api_key="test-key")
        result = provider.generate("system prompt", "user prompt")

        assert isinstance(result, LLMResponse)
        assert result.content == "Generated docstring"
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50

        # Verify standard message format
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "system"

    @patch("lcp.ai.connectors.openai.OpenAIProvider._get_client")
    def test_generate_reasoning(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 200
        mock_usage.prompt_tokens_details = None

        mock_completion_details = MagicMock()
        mock_completion_details.reasoning_tokens = 150
        mock_usage.completion_tokens_details = mock_completion_details

        mock_choice = MagicMock()
        mock_choice.message.content = "Generated docstring"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(api_key="test-key", reasoning=True)
        result = provider.generate("system prompt", "user prompt")

        assert result.usage.reasoning_tokens == 150

        # Verify reasoning message format
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "developer"


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_name(self):
        provider = AnthropicProvider(api_key="test-key")
        assert provider.name == "anthropic"

    def test_default_model(self):
        provider = AnthropicProvider(api_key="test-key")
        assert provider._model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        provider = AnthropicProvider(model="claude-haiku-4-20250514", api_key="test-key")
        assert provider._model == "claude-haiku-4-20250514"

    def test_api_key_from_env(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            provider = AnthropicProvider()
            assert provider._api_key == "env-key"

    def test_api_key_precedence(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            provider = AnthropicProvider(api_key="explicit-key")
            assert provider._api_key == "explicit-key"

    def test_lazy_import_error(self):
        provider = AnthropicProvider(api_key="test-key")
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="anthropic"):
                provider._get_client()

    @patch("lcp.ai.connectors.anthropic.AnthropicProvider._get_client")
    def test_generate(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_usage = MagicMock()
        mock_usage.input_tokens = 80
        mock_usage.output_tokens = 40
        mock_usage.cache_creation_input_tokens = 10
        mock_usage.cache_read_input_tokens = 5

        mock_content = MagicMock()
        mock_content.text = "Generated docstring"

        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage = mock_usage

        mock_client.messages.create.return_value = mock_response

        provider = AnthropicProvider(api_key="test-key")
        result = provider.generate("system prompt", "user prompt")

        assert isinstance(result, LLMResponse)
        assert result.content == "Generated docstring"
        assert result.usage.input_tokens == 80
        assert result.usage.output_tokens == 40
        assert result.usage.cache_tokens == 15

        # Verify message format
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == "system prompt"
