"""OpenAI LLM provider."""

from __future__ import annotations

import os

from ..models import LLMResponse, TokenUsage
from ..provider import LLMProvider


class OpenAIProvider(LLMProvider):
    """LLM provider using the OpenAI API.

    Args:
        model: Model name to use.
        api_key: API key. Falls back to OPENAI_API_KEY env var.
        reasoning: If True, uses the developer message format required
            by reasoning models (o1, o3, etc.).
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        reasoning: bool = False,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._reasoning = reasoning
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "The 'openai' package is required for the OpenAI provider. "
                    "Install it with: pip install lcp[ai]"
                )
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def _get_async_client(self):
        if not hasattr(self, "_async_client") or self._async_client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "The 'openai' package is required for the OpenAI provider. "
                    "Install it with: pip install lcp[ai]"
                )
            self._async_client = openai.AsyncOpenAI(api_key=self._api_key)
        return self._async_client

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text using the OpenAI API."""
        client = self._get_client()

        if self._reasoning:
            messages = [
                {"role": "developer", "content": system},
                {"role": "user", "content": prompt},
            ]
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]

        response = client.chat.completions.create(
            model=self._model,
            messages=messages,
        )

        content = response.choices[0].message.content or ""
        usage_data = response.usage

        usage = TokenUsage()
        if usage_data:
            usage.input_tokens = usage_data.prompt_tokens or 0
            usage.output_tokens = usage_data.completion_tokens or 0

            # Cache tokens from prompt_tokens_details
            prompt_details = getattr(usage_data, "prompt_tokens_details", None)
            if prompt_details:
                usage.cache_tokens = getattr(prompt_details, "cached_tokens", 0) or 0

            # Reasoning tokens from completion_tokens_details
            completion_details = getattr(usage_data, "completion_tokens_details", None)
            if completion_details:
                usage.reasoning_tokens = (
                    getattr(completion_details, "reasoning_tokens", 0) or 0
                )

        return LLMResponse(content=content, usage=usage)

    async def agenerate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text using the OpenAI API (async)."""
        client = self._get_async_client()

        if self._reasoning:
            messages = [
                {"role": "developer", "content": system},
                {"role": "user", "content": prompt},
            ]
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]

        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
        )

        content = response.choices[0].message.content or ""
        usage_data = response.usage

        usage = TokenUsage()
        if usage_data:
            usage.input_tokens = usage_data.prompt_tokens or 0
            usage.output_tokens = usage_data.completion_tokens or 0

            prompt_details = getattr(usage_data, "prompt_tokens_details", None)
            if prompt_details:
                usage.cache_tokens = getattr(prompt_details, "cached_tokens", 0) or 0

            completion_details = getattr(usage_data, "completion_tokens_details", None)
            if completion_details:
                usage.reasoning_tokens = (
                    getattr(completion_details, "reasoning_tokens", 0) or 0
                )

        return LLMResponse(content=content, usage=usage)
