from __future__ import annotations

from typing import Any

from retrieval.keyword_search import SearchResult


class SourceFormatter:
    """Formatiert Retrieval-Treffer in zitierfähige Quellobjekte."""

    def format_sources(self, results: list[SearchResult]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []

        for index, result in enumerate(results, start=1):
            title = self._first_non_empty(
                result.title,
                self._as_non_empty_str(result.metadata.get("title")),
                result.doc_id,
            )
            section_header = self._first_non_empty(
                result.section_header,
                self._as_non_empty_str(result.metadata.get("section_header")),
            )
            source_ref = self._first_non_empty(
                result.source_ref,
                self._as_non_empty_str(result.metadata.get("source_ref")),
                self._as_non_empty_str(result.metadata.get("source")),
            )

            source: dict[str, Any] = {
                "source_number": index,
                "doc_id": result.doc_id,
                "chunk_id": result.chunk_id,
                "title": title,
                "source_ref": source_ref or None,
                "score": round(float(result.score), 4),
            }
            if section_header:
                source["section_header"] = section_header

            sources.append(source)

        return sources

    @staticmethod
    def _as_non_empty_str(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    def _first_non_empty(self, *values: Any) -> str:
        for value in values:
            normalized = self._as_non_empty_str(value)
            if normalized:
                return normalized
        return ""
