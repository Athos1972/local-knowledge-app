from __future__ import annotations

from pathlib import Path
from typing import Any

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRepository
from retrieval.context_builder import ContextBuilder
from retrieval.embedding_provider import EmbeddingProvider
from retrieval.embedding_provider import build_embedding_provider
from retrieval.hybrid_search import HybridSearcher
from retrieval.keyword_search import KeywordSearcher, SearchResult
from retrieval.vector_search import VectorSearcher
from retrieval.runtime_settings import RuntimeSettings

logger = AppLogger.get_logger()


class AskPipeline:
    """Baut aus Hybrid-Suchergebnissen einen LLM-tauglichen Kontextblock."""

    def __init__(
        self,
        hybrid_searcher: HybridSearcher,
        context_builder: ContextBuilder | None = None,
    ):
        self.hybrid_searcher = hybrid_searcher
        self.context_builder = context_builder or ContextBuilder()

    @classmethod
    def from_data_root(
        cls,
        data_root: Path | None = None,
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
        max_context_chars: int = 8000,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "AskPipeline":
        root = (data_root or (Path.home() / "local-knowledge-data")).expanduser().resolve()
        settings = RuntimeSettings.load()
        active_embedding_provider = embedding_provider or build_embedding_provider(
            provider_name=settings.embedding_provider,
            model_name=settings.ollama_embed_model,
            ollama_base_url=settings.ollama_base_url,
        )

        repository = ChunkRepository(data_root=root)
        chunks = repository.load_chunks()

        keyword_searcher = KeywordSearcher(chunks)
        vector_searcher = VectorSearcher(
            embedding_provider=active_embedding_provider,
            db_path=root / "index" / "vector_index.sqlite",
            chunks=chunks,
        )
        hybrid_searcher = HybridSearcher(
            keyword_searcher=keyword_searcher,
            vector_searcher=vector_searcher,
            keyword_weight=keyword_weight,
            vector_weight=vector_weight,
        )

        return cls(
            hybrid_searcher=hybrid_searcher,
            context_builder=ContextBuilder(max_context_chars=max_context_chars),
        )

    def ask(self, query: str, top_k: int = 5) -> dict[str, Any]:
        normalized_query = query.strip()
        logger.info("AskPipeline query=%s top_k=%s", normalized_query, top_k)

        results: list[SearchResult] = self.hybrid_searcher.search(normalized_query, top_k=top_k)
        context = self.context_builder.build_context(results)

        logger.info(
            "AskPipeline completed. query=%s results=%s context_chars=%s",
            normalized_query,
            len(results),
            len(context),
        )

        return {
            "query": normalized_query,
            "results": results,
            "context": context,
        }
