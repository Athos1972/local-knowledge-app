from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from common.logging_setup import AppLogger

logger = AppLogger.get_logger()


class EmbeddingProviderError(RuntimeError):
    """Anwendungsnaher Fehler für Embedding-Provider."""


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@dataclass(slots=True)
class OllamaEmbeddingProvider:
    model_name: str = "nomic-embed-text"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = 60

    provider_name: str = "ollama"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized = [text.strip() for text in texts if text and text.strip()]
        if not normalized:
            return []

        endpoint = f"{self.base_url.rstrip('/')}/api/embed"
        payload = {
            "model": self.model_name,
            "input": normalized,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace") if getattr(error, "fp", None) else ""
            if error.code == 404:
                raise EmbeddingProviderError(
                    f"Ollama Embedding-Modell '{self.model_name}' wurde nicht gefunden. "
                    f"Bitte zuerst 'ollama pull {self.model_name}' ausführen."
                ) from error
            raise EmbeddingProviderError(
                f"Ollama Embedding-Request fehlgeschlagen (HTTP {error.code}): {details or error.reason}"
            ) from error
        except URLError as error:
            raise EmbeddingProviderError(
                "Ollama ist nicht erreichbar. Bitte prüfen, ob 'ollama serve' läuft "
                f"({endpoint}). Ursprünglicher Fehler: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise EmbeddingProviderError(
                f"Ollama Embedding-Request Timeout nach {self.timeout_seconds}s."
            ) from error

        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise EmbeddingProviderError("Ollama lieferte ungültiges JSON für Embeddings.") from error

        embeddings = parsed.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            return [self._to_float_vector(row) for row in embeddings]

        single_embedding = parsed.get("embedding")
        if isinstance(single_embedding, list):
            return [self._to_float_vector(single_embedding)]

        raise EmbeddingProviderError("Ollama antwortete ohne gültige Embedding-Daten.")

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderError("Leere Anfrage kann nicht eingebettet werden.")
        return vectors[0]

    @staticmethod
    def _to_float_vector(values: object) -> list[float]:
        if not isinstance(values, list) or not all(isinstance(item, (int, float)) for item in values):
            raise EmbeddingProviderError("Ungültiger Embedding-Vektor von Ollama erhalten.")
        return [float(item) for item in values]


@dataclass(slots=True)
class LegacySentenceTransformerProvider:
    model_name: str = "all-MiniLM-L6-v2"

    provider_name: str = "sentence_transformers"
    _model: object | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized = [text.strip() for text in texts if text and text.strip()]
        if not normalized:
            return []

        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as error:
                raise EmbeddingProviderError(
                    "Legacy sentence-transformers ist nicht installiert. "
                    "Bitte optionales Legacy-Extra installieren oder auf Ollama wechseln."
                ) from error

            logger.warning(
                "Legacy Embedding-Provider sentence_transformers ist aktiv. "
                "Dieser Pfad ist nur für Migrationen gedacht."
            )
            self._model = SentenceTransformer(self.model_name)

        vectors = self._model.encode(normalized, normalize_embeddings=True)
        return [list(map(float, row)) for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderError("Leere Anfrage kann nicht eingebettet werden.")
        return vectors[0]


def build_embedding_provider(
    provider_name: str,
    model_name: str,
    ollama_base_url: str,
    timeout_seconds: int = 60,
) -> EmbeddingProvider:
    normalized_provider = provider_name.strip().lower()
    if normalized_provider == "ollama":
        return OllamaEmbeddingProvider(
            model_name=model_name,
            base_url=ollama_base_url,
            timeout_seconds=timeout_seconds,
        )

    if normalized_provider == "sentence_transformers":
        return LegacySentenceTransformerProvider(model_name=model_name)

    raise EmbeddingProviderError(
        "Ungültiger Embedding-Provider. Erlaubte Werte: 'ollama', 'sentence_transformers'."
    )
