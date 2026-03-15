from __future__ import annotations

import unittest

from retrieval.answer_pipeline import AnswerPipeline
from retrieval.context_builder import ContextBuilder
from retrieval.keyword_search import SearchResult
from retrieval.prompt_builder import PromptBuilder
from retrieval.reranker import BaseReranker
from retrieval.source_formatter import SourceFormatter


class _StubSearcher:
    def __init__(self, results: list[SearchResult]):
        self._results = results

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return self._results[:top_k]

    def search_candidates(self, query: str, candidate_k: int = 100, source_filters: list[str] | None = None) -> list[SearchResult]:
        return self._results[:candidate_k]


class _StubReranker(BaseReranker):
    model_name = "stub-reranker"

    def rerank(self, query: str, candidates: list[SearchResult], top_n: int) -> list[SearchResult]:
        reranked: list[SearchResult] = []
        for index, candidate in enumerate(reversed(candidates[:top_n]), start=1):
            candidate.metadata["rerank_score"] = float(top_n - index + 1)
            candidate.rerank_score = float(top_n - index + 1)
            reranked.append(candidate)
        return reranked


class _FlatScoreReranker(BaseReranker):
    model_name = "flat-reranker"

    def rerank(self, query: str, candidates: list[SearchResult], top_n: int) -> list[SearchResult]:
        reranked = list(reversed(candidates[:top_n]))
        for item in reranked:
            item.metadata["rerank_score"] = 0.0025
            item.rerank_score = 0.0025
        return reranked


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
            reranker=_StubReranker(),
            candidate_k=20,
            final_k=1,
        )

        payload = pipeline.prepare_answer("event mesh kyma", top_k=1, candidate_k=10)
        self.assertEqual("event mesh kyma", payload["query"])
        self.assertEqual(1, len(payload["results"]))
        self.assertEqual(1, len(payload["candidate_results"]))
        self.assertEqual(1, len(payload["sources"]))
        self.assertIn("SOURCE 1", payload["context"])
        self.assertIn("QUESTION", payload["prompt"])
        self.assertEqual(10, payload["debug"]["candidate_k"])
        self.assertTrue(payload["debug"]["reranker_enabled"])

    def test_answer_pipeline_dedupes_final_results(self) -> None:
        duplicated_source = "domains/idex.md"
        results = [
            SearchResult(
                doc_id="doc-1",
                chunk_id="chunk-1",
                title="IDEX Grundlagen",
                score=1.0,
                text="IDEX content repeated",
                metadata={"section_header": "Overview"},
                source_ref=duplicated_source,
                section_header="Overview",
            ),
            SearchResult(
                doc_id="doc-2",
                chunk_id="chunk-2",
                title="IDEX Grundlagen",
                score=0.99,
                text="IDEX content repeated",
                metadata={"section_header": "Overview"},
                source_ref=duplicated_source,
                section_header="Overview",
            ),
            SearchResult(
                doc_id="doc-3",
                chunk_id="chunk-3",
                title="IDEX Historie",
                score=0.8,
                text="Another IDEX text",
                metadata={"section_header": "History"},
                source_ref="domains/idex-history.md",
                section_header="History",
            ),
        ]
        pipeline = AnswerPipeline(
            hybrid_searcher=_StubSearcher(results),
            context_builder=ContextBuilder(max_context_chars=500),
            prompt_builder=PromptBuilder(),
            source_formatter=SourceFormatter(),
            reranker=None,
            candidate_k=10,
            final_k=3,
        )

        payload = pipeline.prepare_answer("IDEX", top_k=3, candidate_k=10)

        self.assertEqual(2, len(payload["results"]))
        self.assertEqual(["chunk-1", "chunk-3"], [item.chunk_id for item in payload["results"]])

    def test_answer_pipeline_applies_guardrail_for_flat_rerank_scores(self) -> None:
        results = [
            SearchResult(
                doc_id="doc-1",
                chunk_id="chunk-1",
                title="Neue Wechselverordnung",
                score=0.95,
                text="Die neue Wechselverordnung aendert Fristen und Prozesse.",
                metadata={"section_header": "Aenderungen"},
                source_ref="domains/wechselverordnung.md",
                section_header="Aenderungen",
            ),
            SearchResult(
                doc_id="doc-2",
                chunk_id="chunk-2",
                title="Allgemeine Projektseite",
                score=0.60,
                text="Projektinformationen ohne direkten Bezug.",
                metadata={"section_header": "Overview"},
                source_ref="domains/project.md",
                section_header="Overview",
            ),
        ]
        pipeline = AnswerPipeline(
            hybrid_searcher=_StubSearcher(results),
            context_builder=ContextBuilder(max_context_chars=500),
            prompt_builder=PromptBuilder(),
            source_formatter=SourceFormatter(),
            reranker=_FlatScoreReranker(),
            candidate_k=10,
            final_k=2,
        )

        payload = pipeline.prepare_answer("Was aendert sich mit der neuen Wechselverordnung?", top_k=2, candidate_k=10)

        self.assertTrue(payload["debug"]["reranker_guardrail_applied"])
        self.assertEqual("chunk-1", payload["results"][0].chunk_id)


if __name__ == "__main__":
    unittest.main()
