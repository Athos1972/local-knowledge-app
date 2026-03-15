from __future__ import annotations

from pathlib import Path
from typing import Any

from common.logging_setup import AppLogger
from llm.base import BaseLlmProvider
from retrieval.answer_pipeline import AnswerPipeline
from retrieval.citation_formatter import CitationFormatter
from retrieval.embedding_provider import EmbeddingProvider
from retrieval.reranker import BaseReranker

logger = AppLogger.get_logger()


class AnswerExecutor:
    """Führt vorbereitete Answer-Payloads optional gegen ein LLM aus."""

    def __init__(self, answer_pipeline: AnswerPipeline, llm_provider: BaseLlmProvider):
        self.answer_pipeline = answer_pipeline
        self.llm_provider = llm_provider
        self.citation_formatter = CitationFormatter()

    @classmethod
    def from_data_root(
        cls,
        llm_provider: BaseLlmProvider,
        data_root: Path | None = None,
        keyword_weight: float | None = None,
        vector_weight: float | None = None,
        max_context_chars: int | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        reranker: BaseReranker | None = None,
        candidate_k: int | None = None,
        final_k: int | None = None,
        reranker_enabled: bool | None = None,
        reranker_model: str | None = None,
        reranker_device: str | None = None,
    ) -> "AnswerExecutor":
        pipeline = AnswerPipeline.from_data_root(
            data_root=data_root,
            keyword_weight=keyword_weight,
            vector_weight=vector_weight,
            max_context_chars=max_context_chars,
            embedding_provider=embedding_provider,
            reranker=reranker,
            candidate_k=candidate_k,
            final_k=final_k,
            reranker_enabled=reranker_enabled,
            reranker_model=reranker_model,
            reranker_device=reranker_device,
        )
        return cls(answer_pipeline=pipeline, llm_provider=llm_provider)

    def answer(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int | None = None,
        source_filters: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = self.answer_pipeline.prepare_answer(
            query=query,
            top_k=top_k,
            candidate_k=candidate_k,
            source_filters=source_filters,
        )
        results = payload["results"]
        prompt = payload["prompt"]

        logger.info(
            "AnswerExecutor started query=%s hits=%s context_chars=%s prompt_chars=%s provider=%s",
            payload["query"],
            len(results),
            len(payload["context"]),
            len(prompt),
            self.llm_provider.provider_name,
        )

        if not results:
            logger.info("AnswerExecutor skipped LLM call because no retrieval hits were found.")
            payload["llm_response"] = None
            formatted_answer, citation_map = self.citation_formatter.format_answer(
                "Keine Treffer gefunden. Daher wurde kein LLM-Aufruf durchgeführt.",
                payload["sources"],
            )
            payload["answer_text"] = formatted_answer
            payload["citation_map"] = citation_map
            return payload

        llm_response = self.llm_provider.generate(prompt)
        payload["llm_response"] = llm_response.to_dict()
        formatted_answer, citation_map = self.citation_formatter.format_answer(
            llm_response.text,
            payload["sources"],
        )
        payload["answer_text"] = formatted_answer
        payload["citation_map"] = citation_map
        return payload
