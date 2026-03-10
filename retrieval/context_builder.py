from __future__ import annotations

from typing import Any

from retrieval.keyword_search import SearchResult


class ContextBuilder:
    """Erzeugt einen strukturierten Kontextblock aus Retrieval-Treffern."""

    def __init__(self, max_context_chars: int = 8000):
        self.max_context_chars = max(1, max_context_chars)

    def build_context(self, results: list[SearchResult]) -> str:
        if not results:
            return ""

        sections: list[str] = []
        current_length = 0

        for index, result in enumerate(results, start=1):
            section = self._build_source_section(index=index, result=result)
            if not section:
                continue

            additional_length = len(section)
            if sections:
                additional_length += 2  # Abstand zwischen Quellen

            if current_length + additional_length > self.max_context_chars:
                break

            sections.append(section)
            current_length += additional_length

        return "\n\n".join(sections)

    def _build_source_section(self, index: int, result: SearchResult) -> str:
        lines = [f"SOURCE {index}", f"Title: {result.title or result.doc_id}"]

        section_header = self._as_non_empty_str(result.section_header) or self._as_non_empty_str(
            result.metadata.get("section_header")
        )
        if section_header:
            lines.append(f"Section: {section_header}")

        tags = self._extract_tags(result.metadata)
        if tags:
            lines.append(f"Tags: {', '.join(tags)}")

        lines.append("")
        lines.append(result.text.strip())

        return "\n".join(lines).strip()

    @staticmethod
    def _extract_tags(metadata: dict[str, Any]) -> list[str]:
        tags = metadata.get("tags")
        if not isinstance(tags, list):
            return []

        normalized_tags: list[str] = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip():
                normalized_tags.append(tag.strip())
        return normalized_tags

    @staticmethod
    def _as_non_empty_str(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""
