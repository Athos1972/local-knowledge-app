from __future__ import annotations

from retrieval.keyword_search import SearchResult


class PromptBuilder:
    """Baut einen kompakten, strukturierten Prompt für spätere QA-Modelle."""

    def build_prompt(self, query: str, results: list[SearchResult], context: str) -> str:
        normalized_query = query.strip()
        normalized_context = context.strip()

        if not normalized_context:
            normalized_context = self._build_empty_context(results)

        instructions = [
            "Du bist ein QA-Assistent für lokale Wissensdaten.",
            "Beantworte die Frage ausschließlich anhand des bereitgestellten CONTEXT.",
            "Erfinde keine Informationen und nutze kein externes Wissen.",
            "Wenn die Antwort im CONTEXT nicht enthalten ist, sage das klar und knapp.",
            "Nenne verwendete Quellen mit [SOURCE <nummer>] passend zur Kontext-Nummerierung.",
        ]

        parts = [
            "SYSTEM / INSTRUCTIONS",
            "\n".join(instructions),
            "",
            "QUESTION",
            normalized_query,
            "",
            "CONTEXT",
            normalized_context,
        ]
        return "\n".join(parts).strip()

    @staticmethod
    def _build_empty_context(results: list[SearchResult]) -> str:
        if results:
            return "(Kontext konnte nicht aufgebaut werden.)"
        return "(Kein relevanter Kontext gefunden.)"
