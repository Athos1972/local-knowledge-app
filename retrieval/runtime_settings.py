from __future__ import annotations

from dataclasses import dataclass

from common.config import AppConfig


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embed_model: str
    embedding_provider: str

    @classmethod
    def load(cls) -> "RuntimeSettings":
        return cls(
            ollama_base_url=AppConfig.get_str(
                "OLLAMA_BASE_URL",
                "ollama",
                "base_url",
                default="http://localhost:11434",
            ),
            ollama_chat_model=AppConfig.get_str(
                "OLLAMA_CHAT_MODEL",
                "ollama",
                "chat_model",
                default="llama3.1:8b",
            ),
            ollama_embed_model=AppConfig.get_str(
                "OLLAMA_EMBED_MODEL",
                "ollama",
                "embed_model",
                default="nomic-embed-text",
            ),
            embedding_provider=AppConfig.get_str(
                "EMBEDDING_PROVIDER",
                "embeddings",
                "provider",
                default="ollama",
            ).lower(),
        )
