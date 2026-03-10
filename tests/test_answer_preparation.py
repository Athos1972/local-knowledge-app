from __future__ import annotations

import unittest

from retrieval.answer_pipeline import AnswerPipeline
from retrieval.context_builder import ContextBuilder
from retrieval.keyword_search import SearchResult
from retrieval.prompt_builder import PromptBuilder
from retrieval.source_formatter import SourceFormatter


class _StubSearcher:
    def __init__(self, results: list[SearchResult]):
        self._results = results

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return self._results[:top_k]


class AnswerPreparationTests(unittest.TestCase):
    def test_prompt_builder_handles_missing_context(self) -> None:
        prompt = PromptBuilder().build_prompt(query="Was ist Kyma?", results=[], context="")
        self.assertIn("SYSTEM / INSTRUCTIONS", prompt)
        self.assertIn("Die Antwort ist im Kontext nicht enthalten", prompt)
        self.assertIn("OUTPUT FORMAT", prompt)

    def test_source_formatter_builds_reference_fields(self) -> None:
        result = SearchResult(
            doc_id="doc-1",
            chunk_id="chunk-1",
            title="",
            score=1.23456,
            text="Chunk text",
            metadata={"title": "Fallback Title", "source_ref": "docs/file.md", "section_header": "Intro"},
            source_ref=None,
            section_header=None,
        )

        sources = SourceFormatter().format_sources([result])
        self.assertEqual(1, len(sources))
        self.assertEqual("Fallback Title", sources[0]["title"])
        self.assertEqual("docs/file.md", sources[0]["source_ref"])
        self.assertEqual("Intro", sources[0]["section_header"])
        self.assertEqual(1.2346, sources[0]["score"])

    def test_answer_pipeline_returns_expected_payload(self) -> None:
        results = [
            SearchResult(
                doc_id="doc-1",
                chunk_id="chunk-1",
                title="Doc 1",
                score=3.0,
                text="Kyma Event Mesh Integration.",
                metadata={"section_header": "Overview"},
                source_ref="domains/kyma.md",
                section_header="Overview",
            )
        ]
        pipeline = AnswerPipeline(
            hybrid_searcher=_StubSearcher(results),
            context_builder=ContextBuilder(max_context_chars=500),
            prompt_builder=PromptBuilder(),
            source_formatter=SourceFormatter(),
        )

        payload = pipeline.prepare_answer("event mesh kyma", top_k=0)
        self.assertEqual("event mesh kyma", payload["query"])
        self.assertEqual(1, len(payload["results"]))
        self.assertEqual(1, len(payload["sources"]))
        self.assertIn("SOURCE 1", payload["context"])
        self.assertIn("QUESTION", payload["prompt"])


if __name__ == "__main__":
    unittest.main()
