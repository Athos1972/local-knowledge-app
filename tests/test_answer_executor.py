from __future__ import annotations

import unittest

from llm.base import BaseLlmProvider
from llm.response_models import LlmResponse
from retrieval.answer_executor import AnswerExecutor
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


class _StubProvider(BaseLlmProvider):
    provider_name = "stub"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> LlmResponse:
        self.calls += 1
        return LlmResponse(
            text="Test Answer",
            model_name="stub-model",
            provider_name=self.provider_name,
            prompt_chars=len(prompt),
            response_chars=11,
        )


class AnswerExecutorTests(unittest.TestCase):
    def test_answer_executes_llm_when_results_exist(self) -> None:
        result = SearchResult(
            doc_id="doc-1",
            chunk_id="chunk-1",
            title="Doc 1",
            score=1.5,
            text="Kyma and Event Mesh",
            metadata={},
            source_ref="domains/kyma.md",
            section_header=None,
        )
        pipeline = AnswerPipeline(
            hybrid_searcher=_StubSearcher([result]),
            context_builder=ContextBuilder(max_context_chars=400),
            prompt_builder=PromptBuilder(),
            source_formatter=SourceFormatter(),
        )
        provider = _StubProvider()

        payload = AnswerExecutor(answer_pipeline=pipeline, llm_provider=provider).answer("event mesh kyma")

        self.assertEqual(1, provider.calls)
        self.assertEqual("Test Answer", payload["answer_text"])
        self.assertIsNotNone(payload["llm_response"])

    def test_answer_skips_llm_when_no_results(self) -> None:
        pipeline = AnswerPipeline(
            hybrid_searcher=_StubSearcher([]),
            context_builder=ContextBuilder(max_context_chars=400),
            prompt_builder=PromptBuilder(),
            source_formatter=SourceFormatter(),
        )
        provider = _StubProvider()

        payload = AnswerExecutor(answer_pipeline=pipeline, llm_provider=provider).answer("unknown")

        self.assertEqual(0, provider.calls)
        self.assertIsNone(payload["llm_response"])
        self.assertIn("kein LLM-Aufruf", payload["answer_text"])


if __name__ == "__main__":
    unittest.main()
