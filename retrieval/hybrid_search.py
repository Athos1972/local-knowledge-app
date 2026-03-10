from __future__ import annotations

from retrieval.keyword_search import KeywordSearcher, SearchResult
from retrieval.vector_search import VectorSearcher


class HybridSearcher:
    """Kombiniert Keyword- und Vector-Ergebnisse über gewichteten Score."""

    def __init__(
        self,
        keyword_searcher: KeywordSearcher,
        vector_searcher: VectorSearcher,
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
    ):
        self.keyword_searcher = keyword_searcher
        self.vector_searcher = vector_searcher
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        keyword_results = self.keyword_searcher.search(query, top_k=top_k)
        vector_results = self.vector_searcher.search(query, top_k=top_k)

        keyword_scores = self._normalize_scores(keyword_results)
        vector_scores = self._normalize_scores(vector_results)

        merged: dict[str, SearchResult] = {}
        total_scores: dict[str, float] = {}

        for item in keyword_results:
            merged[item.chunk_id] = item
            total_scores[item.chunk_id] = self.keyword_weight * keyword_scores.get(item.chunk_id, 0.0)

        for item in vector_results:
            if item.chunk_id not in merged:
                merged[item.chunk_id] = item
                total_scores[item.chunk_id] = 0.0
            total_scores[item.chunk_id] += self.vector_weight * vector_scores.get(item.chunk_id, 0.0)

        ranked = sorted(
            merged.values(),
            key=lambda item: (-total_scores.get(item.chunk_id, 0.0), item.doc_id, item.chunk_id),
        )

        final_results: list[SearchResult] = []
        for item in ranked[: max(1, top_k)]:
            final_results.append(
                SearchResult(
                    doc_id=item.doc_id,
                    chunk_id=item.chunk_id,
                    title=item.title,
                    score=round(total_scores.get(item.chunk_id, 0.0), 4),
                    text=item.text,
                    metadata=item.metadata,
                    source_ref=item.source_ref,
                    section_header=item.section_header,
                )
            )
        return final_results

    @staticmethod
    def _normalize_scores(results: list[SearchResult]) -> dict[str, float]:
        if not results:
            return {}

        max_score = max(result.score for result in results)
        if max_score <= 0:
            return {result.chunk_id: 0.0 for result in results}

        return {result.chunk_id: result.score / max_score for result in results}
