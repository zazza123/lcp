"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import LLMResponse


class LLMProvider(ABC):
    """Abstract base class for LLM connectors."""

    @abstractmethod
    def generate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text from the LLM (synchronous)."""

    @abstractmethod
    async def agenerate(self, system: str, prompt: str) -> LLMResponse:
        """Generate text from the LLM (async)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider."""
