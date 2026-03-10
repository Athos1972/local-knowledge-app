from __future__ import annotations

import re
from typing import Any


class CitationFormatter:
    """Erzeugt einheitliche In-Text-Zitationen und einen Sources-Block."""

    _SOURCE_CITATION_PATTERN = re.compile(r"\[\s*source\s*(\d+)\s*\]", re.IGNORECASE)

    def format_answer(self, answer_text: str, sources: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
        citation_map = self.build_chunk_citation_map(sources)
        normalized_answer = self._normalize_answer(answer_text, citation_map)
        sources_block = self._build_sources_block(sources, citation_map)

        if sources_block:
            return f"ANSWER\n\n{normalized_answer}\n\nSources\n{sources_block}", citation_map
        return f"ANSWER\n\n{normalized_answer}\n\nSources\nkeine", citation_map

    def build_chunk_citation_map(self, sources: list[dict[str, Any]]) -> dict[str, int]:
        chunk_map: dict[str, int] = {}
        for fallback_index, source in enumerate(sources, start=1):
            chunk_id = str(source.get("chunk_id") or "").strip()
            if not chunk_id:
                continue

            source_number = source.get("source_number")
            if isinstance(source_number, int) and source_number > 0:
                chunk_map[chunk_id] = source_number
            else:
                chunk_map[chunk_id] = fallback_index
        return chunk_map

    def _normalize_answer(self, answer_text: str, citation_map: dict[str, int]) -> str:
        normalized = (answer_text or "").strip()
        normalized = self._SOURCE_CITATION_PATTERN.sub(r"[\1]", normalized)

        if normalized:
            has_citation = bool(re.search(r"\[\d+\]", normalized))
            if not has_citation and citation_map:
                ordered = sorted(set(citation_map.values()))
                normalized = f"{normalized} {' '.join(f'[{index}]' for index in ordered)}"
            return normalized

        if citation_map:
            ordered = sorted(set(citation_map.values()))
            return f"Keine Antwort generiert. {' '.join(f'[{index}]' for index in ordered)}"
        return "Keine Antwort generiert."

    def _build_sources_block(self, sources: list[dict[str, Any]], citation_map: dict[str, int]) -> str:
        if not sources:
            return ""

        lines: list[tuple[int, str]] = []
        for fallback_index, source in enumerate(sources, start=1):
            source_number = source.get("source_number")
            if isinstance(source_number, int) and source_number > 0:
                citation_index = source_number
            else:
                chunk_id = str(source.get("chunk_id") or "").strip()
                citation_index = citation_map.get(chunk_id, fallback_index)

            title = str(source.get("title") or source.get("doc_id") or "Unbekannte Quelle").strip()
            section_header = str(source.get("section_header") or "").strip()
            label = f"{title} – {section_header}" if section_header else title
            lines.append((citation_index, f"[{citation_index}] {label}"))

        lines.sort(key=lambda item: item[0])
        return "\n".join(line for _, line in lines)
