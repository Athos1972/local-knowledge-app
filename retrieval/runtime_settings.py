from __future__ import annotations

from dataclasses import dataclass

from common.config import AppConfig


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embed_model: str
    embedding_provider: str
    retrieval_candidate_k: int
    retrieval_final_k: int
    retrieval_max_context_chars: int
    retrieval_keyword_weight: float
    retrieval_vector_weight: float
    reranker_enabled: bool
    reranker_model: str
    reranker_device: str | None

    @classmethod
    def load(cls) -> "RuntimeSettings":
        reranker_device = AppConfig.get_str(
            "RERANKER_DEVICE",
            "reranker",
            "device",
            default="",
        ).strip()
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
            retrieval_candidate_k=max(
                1,
                int(AppConfig.get("retrieval", "candidate_k", default=100)),
            ),
            retrieval_final_k=max(
                1,
                int(AppConfig.get("retrieval", "final_k", default=7)),
            ),
            retrieval_max_context_chars=max(
                1,
                int(AppConfig.get("retrieval", "max_context_chars", default=8000)),
            ),
            retrieval_keyword_weight=float(
                AppConfig.get("retrieval", "keyword_weight", default=0.5)
            ),
            retrieval_vector_weight=float(
                AppConfig.get("retrieval", "vector_weight", default=0.5)
            ),
            reranker_enabled=str(
                AppConfig.get("reranker", "enabled", default=True)
            ).strip().lower()
            in {"1", "true", "yes", "on"},
            reranker_model=AppConfig.get_str(
                "RERANKER_MODEL",
                "reranker",
                "model",
                default="BAAI/bge-reranker-v2-m3",
            ),
            reranker_device=reranker_device or None,
        )
