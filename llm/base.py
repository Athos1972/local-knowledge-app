from __future__ import annotations

from abc import ABC, abstractmethod

from llm.response_models import LlmResponse


class BaseLlmProvider(ABC):
    """Kleines Provider-Interface für LLM-Ausführung."""

    provider_name: str = "base"

    @abstractmethod
    def generate(self, prompt: str) -> LlmResponse:
        """Generiert eine Antwort für den gegebenen Prompt."""
        raise NotImplementedError
