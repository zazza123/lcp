"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import LLMResponse


class LLMProvider(ABC):
    """Abstract base class for LLM connectors."""

    @abstractmethod
    def generate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text from the LLM.

        Args:
            system: System prompt with instructions.
            prompt: User prompt with the specific request.

        Returns:
            LLMResponse with generated content and token usage.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g. 'openai', 'anthropic')."""
        ...
