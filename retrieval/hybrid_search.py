from __future__ import annotations

import re

from common.logging_setup import AppLogger
from retrieval.keyword_search import KeywordSearcher, SearchResult
from retrieval.vector_search import VectorSearcher

logger = AppLogger.get_logger()
_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


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

    def search(
        self,
        query: str,
        top_k: int = 10,
        source_filters: list[str] | None = None,
    ) -> list[SearchResult]:
        return self.search_candidates(query=query, candidate_k=top_k, source_filters=source_filters)

    def search_candidates(
        self,
        query: str,
        candidate_k: int = 100,
        source_filters: list[str] | None = None,
    ) -> list[SearchResult]:
        normalized_query = query.strip()
        normalized_k = max(1, int(candidate_k))
        keyword_results = self.keyword_searcher.search(query, top_k=normalized_k)
        vector_results = self.vector_searcher.search(query, top_k=normalized_k)
        allowed_sources = self._normalize_source_filters(source_filters or [])
        keyword_hits_before_filter = len(keyword_results)
        vector_hits_before_filter = len(vector_results)

        if allowed_sources:
            keyword_results = [item for item in keyword_results if self._matches_source_filter(item, allowed_sources)]
            vector_results = [item for item in vector_results if self._matches_source_filter(item, allowed_sources)]

        keyword_scores = self._normalize_scores(keyword_results)
        vector_scores = self._normalize_scores(vector_results)

        merged: dict[str, SearchResult] = {}
        total_scores: dict[str, float] = {}

        for item in keyword_results:
            merged[item.chunk_id] = item
            lexical_boost = self._lexical_match_boost(query, item)
            total_scores[item.chunk_id] = (
                self.keyword_weight * keyword_scores.get(item.chunk_id, 0.0)
                + self.keyword_weight * 0.35
                + lexical_boost
            )

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
        for item in ranked[:normalized_k]:
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

        logger.info(
            "Hybrid search query=%s candidate_k=%s source_filters=%s keyword_before=%s keyword_after=%s "
            "vector_before=%s vector_after=%s merged=%s returned=%s top=%s",
            normalized_query,
            normalized_k,
            sorted(allowed_sources),
            keyword_hits_before_filter,
            len(keyword_results),
            vector_hits_before_filter,
            len(vector_results),
            len(merged),
            len(final_results),
            self._summarize_results(final_results),
        )
        return final_results

    @staticmethod
    def _matches_source_filter(item: SearchResult, allowed_sources: set[str]) -> bool:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}

        candidates: list[str] = []
        source_type = metadata.get("source_type")
        if isinstance(source_type, str) and source_type.strip():
            candidates.append(source_type.strip().lower())

        source_value = metadata.get("source")
        if isinstance(source_value, str) and source_value.strip():
            candidates.append(source_value.strip().lower())
        elif isinstance(source_value, dict):
            for key in ("source_type", "source_system", "source_name", "source_key"):
                nested = source_value.get(key)
                if isinstance(nested, str) and nested.strip():
                    candidates.append(nested.strip().lower())

        expanded_candidates: set[str] = set()
        for candidate in candidates:
            expanded_candidates.update(HybridSearcher._expand_source_aliases(candidate))

        return any(candidate in allowed_sources for candidate in expanded_candidates)

    @staticmethod
    def _normalize_source_filters(source_filters: list[str]) -> set[str]:
        normalized: set[str] = set()
        for raw in source_filters:
            value = raw.strip().lower()
            if not value:
                continue
            normalized.update(HybridSearcher._expand_source_aliases(value))
        return normalized

    @staticmethod
    def _expand_source_aliases(value: str) -> set[str]:
        aliases = {
            "web": {"web", "website", "external_website", "scraping"},
            "website": {"web", "website", "external_website", "scraping"},
            "external_website": {"web", "website", "external_website", "scraping"},
            "file": {"file", "filesystem", "documents"},
            "filesystem": {"file", "filesystem", "documents"},
            "documents": {"file", "filesystem", "documents"},
            "confluence": {"confluence"},
            "jira": {"jira"},
        }
        return aliases.get(value, {value})

    @staticmethod
    def _summarize_results(results: list[SearchResult], limit: int = 3) -> str:
        if not results:
            return "[]"

        preview = []
        for item in results[:limit]:
            preview.append(
                f"{item.chunk_id}:{item.score:.4f}"
            )
        return "[" + ", ".join(preview) + "]"

    @staticmethod
    def _lexical_match_boost(query: str, item: SearchResult) -> float:
        query_tokens = {
            token.lower()
            for token in _TOKEN_RE.findall(query.lower())
            if token.strip()
        }
        if not query_tokens:
            return 0.0

        parts = [
            item.title,
            item.section_header or "",
            item.text,
        ]
        haystack = " ".join(part for part in parts if part).lower()
        if not haystack:
            return 0.0

        matched = sum(1 for token in query_tokens if token in haystack)
        coverage = matched / len(query_tokens)
        exact_phrase = query.strip().lower() in haystack
        boost = coverage * 0.25
        if exact_phrase:
            boost += 0.15
        return round(boost, 4)

    @staticmethod
    def _normalize_scores(results: list[SearchResult]) -> dict[str, float]:
        if not results:
            return {}

        max_score = max(result.score for result in results)
        if max_score <= 0:
            return {result.chunk_id: 0.0 for result in results}

        return {result.chunk_id: result.score / max_score for result in results}
