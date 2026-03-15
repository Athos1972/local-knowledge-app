from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRecord

logger = AppLogger.get_logger()

_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(slots=True)
class SearchResult:
    doc_id: str
    chunk_id: str
    title: str
    score: float
    text: str
    metadata: dict[str, Any]
    source_ref: str | None = None
    section_header: str | None = None
    rerank_score: float | None = None


class KeywordSearcher:
    """Pragmatische lokale Keyword-Suche über geladene Chunks."""

    def __init__(self, chunks: list[ChunkRecord]):
        self.chunks = chunks

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        tokens = self._tokenize(normalized_query)
        if not tokens:
            return []

        logger.info("Running keyword search. query=%s top_k=%s", normalized_query, top_k)

        results: list[SearchResult] = []
        phrase = " ".join(tokens)

        for chunk in self.chunks:
            score = self._score_chunk(chunk, tokens=tokens, phrase=phrase)
            if score <= 0:
                continue

            section_header = self._as_non_empty_str(chunk.metadata.get("section_header"))
            results.append(
                SearchResult(
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    score=score,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    source_ref=chunk.source_ref,
                    section_header=section_header or None,
                )
            )

        results.sort(key=lambda item: (-item.score, item.doc_id, item.chunk_id))
        top_results = results[: max(1, top_k)]
        logger.info("Keyword search completed. query=%s hits=%s", normalized_query, len(top_results))
        return top_results

    def _score_chunk(self, chunk: ChunkRecord, tokens: list[str], phrase: str) -> float:
        text = chunk.text.lower()
        title = chunk.title.lower()
        section_header = self._as_non_empty_str(chunk.metadata.get("section_header")).lower()
        tags = self._extract_tags(chunk.metadata)

        text_hits = sum(text.count(token) for token in tokens)
        title_hits = sum(title.count(token) for token in tokens)
        section_hits = sum(section_header.count(token) for token in tokens)
        tag_hits = sum(tag.count(token) for token in tokens for tag in tags)

        score = 0.0
        score += text_hits * 1.0
        score += title_hits * 2.5
        score += section_hits * 1.5
        score += tag_hits * 1.2

        if phrase and phrase in text:
            score += 1.5
        if phrase and phrase in title:
            score += 2.0
        if phrase and section_header and phrase in section_header:
            score += 1.0

        return round(score, 4)

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        return [token.lower() for token in _TOKEN_RE.findall(value.lower()) if token.strip()]

    @staticmethod
    def _extract_tags(metadata: dict[str, Any]) -> list[str]:
        tags = metadata.get("tags")
        if not isinstance(tags, list):
            return []

        normalized_tags: list[str] = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip():
                normalized_tags.append(tag.lower())
        return normalized_tags

    @staticmethod
    def _as_non_empty_str(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""
