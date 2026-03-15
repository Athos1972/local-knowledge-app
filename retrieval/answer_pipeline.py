from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRepository
from retrieval.context_builder import ContextBuilder
from retrieval.embedding_provider import EmbeddingProvider
from retrieval.embedding_provider import build_embedding_provider
from retrieval.hybrid_search import HybridSearcher
from retrieval.keyword_search import KeywordSearcher, SearchResult
from retrieval.prompt_builder import PromptBuilder
from retrieval.reranker import BaseReranker, RerankerError, SentenceTransformerReranker
from retrieval.source_formatter import SourceFormatter
from retrieval.vector_search import VectorSearcher
from retrieval.runtime_settings import RuntimeSettings

logger = AppLogger.get_logger()


class AnswerPipeline:
    """Vorbereitung eines vollständigen QA-Payloads ohne LLM-Aufruf."""

    def __init__(
        self,
        hybrid_searcher: HybridSearcher,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        source_formatter: SourceFormatter | None = None,
        reranker: BaseReranker | None = None,
        candidate_k: int = 100,
        final_k: int = 7,
    ):
        self.hybrid_searcher = hybrid_searcher
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.source_formatter = source_formatter or SourceFormatter()
        self.reranker = reranker
        self.candidate_k = max(1, int(candidate_k))
        self.final_k = max(1, int(final_k))

    @classmethod
    def from_data_root(
        cls,
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
    ) -> "AnswerPipeline":
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
            keyword_weight=keyword_weight if keyword_weight is not None else settings.retrieval_keyword_weight,
            vector_weight=vector_weight if vector_weight is not None else settings.retrieval_vector_weight,
        )
        active_reranker_enabled = settings.reranker_enabled if reranker_enabled is None else reranker_enabled
        active_reranker = reranker
        if active_reranker is None and active_reranker_enabled:
            active_reranker = SentenceTransformerReranker(
                model_name=reranker_model or settings.reranker_model,
                device=reranker_device or settings.reranker_device,
            )

        return cls(
            hybrid_searcher=hybrid_searcher,
            context_builder=ContextBuilder(
                max_context_chars=max_context_chars
                if max_context_chars is not None
                else settings.retrieval_max_context_chars
            ),
            reranker=active_reranker,
            candidate_k=candidate_k if candidate_k is not None else settings.retrieval_candidate_k,
            final_k=final_k if final_k is not None else settings.retrieval_final_k,
        )

    def prepare_answer(
        self,
        query: str,
        top_k: int | None = None,
        candidate_k: int | None = None,
        source_filters: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_query = query.strip()
        normalized_candidate_k = max(1, int(candidate_k if candidate_k is not None else self.candidate_k))
        normalized_final_k = max(1, int(top_k if top_k is not None else self.final_k))
        logger.info(
            "AnswerPipeline query=%s candidate_k=%s final_k=%s reranker=%s",
            normalized_query,
            normalized_candidate_k,
            normalized_final_k,
            self.reranker.__class__.__name__ if self.reranker else "disabled",
        )

        candidate_results: list[SearchResult] = self.hybrid_searcher.search_candidates(
            normalized_query,
            candidate_k=normalized_candidate_k,
            source_filters=source_filters,
        )
        logger.info(
            "AnswerPipeline retrieved candidates. query=%s candidates=%s source_filters=%s top=%s",
            normalized_query,
            len(candidate_results),
            list(source_filters or []),
            self._summarize_results(candidate_results),
        )
        reranker_error: str | None = None
        reranker_guardrail_applied = False
        if self.reranker is not None:
            try:
                reranked_results = self.reranker.rerank(
                    normalized_query,
                    candidate_results,
                    top_n=normalized_final_k,
                )
                results, reranker_guardrail_applied = self._apply_rerank_guardrail(
                    query=normalized_query,
                    candidate_results=candidate_results,
                    reranked_results=reranked_results,
                    final_k=normalized_final_k,
                )
            except RerankerError as error:
                reranker_error = str(error)
                logger.warning(
                    "AnswerPipeline reranker failed. query=%s model=%s fallback=hybrid_only error=%s",
                    normalized_query,
                    getattr(self.reranker, "model_name", "unknown"),
                    reranker_error,
                )
                results = candidate_results[:normalized_final_k]
        else:
            results = candidate_results[:normalized_final_k]
        deduped_results = self._dedupe_results(results)
        if len(deduped_results) < normalized_final_k:
            deduped_results = self._backfill_deduped_results(
                existing=deduped_results,
                pool=candidate_results,
                final_k=normalized_final_k,
            )
        results = deduped_results
        logger.info(
            "AnswerPipeline finalized results. query=%s final_results=%s guardrail=%s top=%s",
            normalized_query,
            len(results),
            reranker_guardrail_applied,
            self._summarize_results(results),
        )
        context = self.context_builder.build_context(results)
        prompt = self.prompt_builder.build_prompt(
            query=normalized_query,
            results=results,
            context=context,
        )
        sources = self.source_formatter.format_sources(results)

        logger.info(
            "AnswerPipeline completed. query=%s results=%s context_chars=%s prompt_chars=%s sources=%s",
            normalized_query,
            len(results),
            len(context),
            len(prompt),
            len(sources),
        )

        return {
            "query": normalized_query,
            "candidate_results": candidate_results,
            "results": results,
            "context": context,
            "prompt": prompt,
            "sources": sources,
            "debug": {
                "candidate_k": normalized_candidate_k,
                "final_k": normalized_final_k,
                "retrieved_candidates": len(candidate_results),
                "final_results": len(results),
                "source_filters": list(source_filters or []),
                "reranker_enabled": self.reranker is not None,
                "reranker_model": getattr(self.reranker, "model_name", None),
                "reranker_error": reranker_error,
                "reranker_guardrail_applied": reranker_guardrail_applied,
                "candidate_preview": self._result_preview(candidate_results),
                "final_preview": self._result_preview(results),
            },
        }

    @staticmethod
    def _summarize_results(results: list[SearchResult], limit: int = 3) -> str:
        if not results:
            return "[]"

        preview = []
        for item in results[:limit]:
            rerank_suffix = ""
            if item.rerank_score is not None:
                rerank_suffix = f"/{item.rerank_score:.4f}"
            preview.append(f"{item.chunk_id}:{item.score:.4f}{rerank_suffix}")
        return "[" + ", ".join(preview) + "]"

    @staticmethod
    def _result_preview(results: list[SearchResult], limit: int = 10) -> list[dict[str, Any]]:
        preview: list[dict[str, Any]] = []
        for item in results[:limit]:
            preview.append(
                {
                    "doc_id": item.doc_id,
                    "chunk_id": item.chunk_id,
                    "score": round(float(item.score), 4),
                    "rerank_score": item.rerank_score,
                    "section_header": item.section_header,
                    "title": item.title,
                }
            )
        return preview

    def _apply_rerank_guardrail(
        self,
        query: str,
        candidate_results: list[SearchResult],
        reranked_results: list[SearchResult],
        final_k: int,
    ) -> tuple[list[SearchResult], bool]:
        if not reranked_results:
            return candidate_results[:final_k], True

        if not self._should_apply_rerank_guardrail(reranked_results):
            return reranked_results[:final_k], False

        hybrid_lookup = {item.chunk_id: index for index, item in enumerate(candidate_results)}
        merged_candidates: dict[str, SearchResult] = {}
        for item in reranked_results:
            merged_candidates[item.chunk_id] = item
        for item in candidate_results[: max(final_k * 3, final_k)]:
            merged_candidates.setdefault(item.chunk_id, item)

        def combined_score(item: SearchResult) -> tuple[float, float, int, str, str]:
            rerank_score = item.rerank_score if item.rerank_score is not None else 0.0
            hybrid_rank = hybrid_lookup.get(item.chunk_id, len(candidate_results))
            hybrid_bonus = max(0.0, 1.0 - (hybrid_rank / max(1, len(candidate_results))))
            exact_bonus = self._query_exact_match_bonus(query, item)
            total = (rerank_score * 0.45) + (item.score * 0.45) + (hybrid_bonus * 0.10) + exact_bonus
            return (
                round(total, 6),
                rerank_score,
                -hybrid_rank,
                item.doc_id,
                item.chunk_id,
            )

        blended = sorted(
            merged_candidates.values(),
            key=combined_score,
            reverse=True,
        )
        logger.info(
            "AnswerPipeline applied rerank guardrail. query=%s reranked=%s blended_top=%s",
            query,
            len(reranked_results),
            self._summarize_results(blended[:final_k]),
        )
        return blended[:final_k], True

    @staticmethod
    def _should_apply_rerank_guardrail(reranked_results: list[SearchResult]) -> bool:
        if len(reranked_results) < 2:
            return False

        rerank_scores = [item.rerank_score for item in reranked_results if item.rerank_score is not None]
        if len(rerank_scores) < 2:
            return True

        top_score = rerank_scores[0]
        bottom_score = rerank_scores[-1]
        spread = top_score - bottom_score
        if top_score < 0.05:
            return True
        if spread < 0.03:
            return True
        return False

    def _dedupe_results(self, results: list[SearchResult]) -> list[SearchResult]:
        deduped: list[SearchResult] = []
        seen_keys: set[str] = set()

        for item in results:
            dedupe_key = self._build_dedupe_key(item)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped.append(item)

        if len(deduped) != len(results):
            logger.info(
                "AnswerPipeline deduped final results. before=%s after=%s",
                len(results),
                len(deduped),
            )
        return deduped

    def _backfill_deduped_results(
        self,
        existing: list[SearchResult],
        pool: list[SearchResult],
        final_k: int,
    ) -> list[SearchResult]:
        results = list(existing)
        seen_keys = {self._build_dedupe_key(item) for item in results}

        for item in pool:
            if len(results) >= final_k:
                break
            dedupe_key = self._build_dedupe_key(item)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            results.append(item)

        return results[:final_k]

    @staticmethod
    def _build_dedupe_key(item: SearchResult) -> str:
        source_ref = (item.source_ref or "").strip().lower()
        title = (item.title or "").strip().lower()
        section = (item.section_header or "").strip().lower()
        text_prefix = item.text.strip()[:600].lower()
        raw = "||".join([source_ref, title, section, text_prefix])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _query_exact_match_bonus(query: str, item: SearchResult) -> float:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return 0.0

        haystack = " ".join(
            value for value in [item.title, item.section_header or "", item.text[:500]] if value
        ).lower()
        if normalized_query in haystack:
            return 0.08
        return 0.0
