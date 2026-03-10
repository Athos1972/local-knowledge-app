from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from common.logging_setup import AppLogger
from llm.base import BaseLlmProvider
from llm.response_models import LlmResponse

logger = AppLogger.get_logger()


class OllamaProviderError(RuntimeError):
    """Anwendungsnaher Fehler für fehlgeschlagene Ollama-Aufrufe."""


class OllamaProvider(BaseLlmProvider):
    provider_name = "ollama"

    def __init__(
        self,
        model_name: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout_seconds: int = 120,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> LlmResponse:
        normalized_prompt = prompt.strip()
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": normalized_prompt,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace") if getattr(error, "fp", None) else ""
            raise OllamaProviderError(
                f"Ollama request failed with HTTP {error.code}: {details or error.reason}"
            ) from error
        except URLError as error:
            raise OllamaProviderError(
                "Ollama ist nicht erreichbar. Bitte prüfen, ob der Server läuft "
                f"({endpoint}). Ursprünglicher Fehler: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise OllamaProviderError(
                f"Ollama request timed out after {self.timeout_seconds} seconds."
            ) from error

        latency_ms = (perf_counter() - start) * 1000

        try:
            parsed: dict[str, Any] = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise OllamaProviderError(
                "Ollama returned invalid JSON response."
            ) from error

        text = str(parsed.get("response", "")).strip()
        logger.info(
            "Ollama generate completed model=%s prompt_chars=%s response_chars=%s latency_ms=%.2f",
            self.model_name,
            len(normalized_prompt),
            len(text),
            latency_ms,
        )

        return LlmResponse(
            text=text,
            model_name=self.model_name,
            provider_name=self.provider_name,
            prompt_chars=len(normalized_prompt),
            response_chars=len(text),
            raw=parsed,
            latency_ms=latency_ms,
        )
