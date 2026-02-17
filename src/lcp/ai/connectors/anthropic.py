"""Anthropic LLM provider."""

from __future__ import annotations

import os

from ..models import LLMResponse, TokenUsage
from ..provider import LLMProvider


class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic API.

    Args:
        model: Model name to use.
        api_key: API key. Falls back to ANTHROPIC_API_KEY env var.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for the Anthropic provider. "
                    "Install it with: pip install lcp[ai]"
                )
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _get_async_client(self):
        if not hasattr(self, "_async_client") or self._async_client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for the Anthropic provider. "
                    "Install it with: pip install lcp[ai]"
                )
            self._async_client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._async_client

    @property
    def name(self) -> str:
        return "anthropic"

    def generate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text using the Anthropic API."""
        client = self._get_client()

        response = client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text if response.content else ""

        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.input_tokens or 0
            usage.output_tokens = response.usage.output_tokens or 0

            cache_creation = getattr(
                response.usage, "cache_creation_input_tokens", 0
            ) or 0
            cache_read = getattr(
                response.usage, "cache_read_input_tokens", 0
            ) or 0
            usage.cache_tokens = cache_creation + cache_read

        return LLMResponse(content=content, usage=usage)

    async def agenerate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text using the Anthropic API (async)."""
        client = self._get_async_client()

        response = await client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text if response.content else ""

        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.input_tokens or 0
            usage.output_tokens = response.usage.output_tokens or 0

            cache_creation = getattr(
                response.usage, "cache_creation_input_tokens", 0
            ) or 0
            cache_read = getattr(
                response.usage, "cache_read_input_tokens", 0
            ) or 0
            usage.cache_tokens = cache_creation + cache_read

        return LLMResponse(content=content, usage=usage)
