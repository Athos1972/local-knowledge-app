#!/usr/bin/env python3
"""Komplette Retrieval+Prompt+LLM-Ausführung für lokale Fragen."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from llm.ollama_provider import OllamaProvider, OllamaProviderError
from retrieval.answer_executor import AnswerExecutor
from retrieval.embedding_provider import EmbeddingProviderError
from retrieval.embedding_provider import build_embedding_provider
from retrieval.reranker import RerankerError
from retrieval.reranker import SentenceTransformerReranker
from retrieval.runtime_settings import RuntimeSettings


def parse_args() -> argparse.Namespace:
    settings = RuntimeSettings.load()

    parser = argparse.ArgumentParser(description="Answer question via retrieval + optional LLM provider")
    parser.add_argument("query", help="Suchanfrage, z. B. 'event mesh kyma'")
    parser.add_argument(
        "--top-k",
        type=int,
        default=settings.retrieval_final_k,
        help="Anzahl finaler Treffer nach Reranking",
    )
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=settings.retrieval_candidate_k,
        help="Anzahl Kandidaten vor dem Reranking",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "local-knowledge-data",
        help="Daten-Root mit processed/chunks, processed/metadata und index/",
    )
    parser.add_argument(
        "--keyword-weight",
        type=float,
        default=settings.retrieval_keyword_weight,
        help="Gewichtung Keyword in hybrid",
    )
    parser.add_argument(
        "--vector-weight",
        type=float,
        default=settings.retrieval_vector_weight,
        help="Gewichtung Vector in hybrid",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        default=settings.retrieval_max_context_chars,
        help="Maximale Kontextgröße",
    )
    parser.add_argument("--provider", default="ollama", choices=["ollama"], help="Aktueller LLM-Provider")
    parser.add_argument("--model", default=settings.ollama_chat_model, help="LLM-Modellname")
    parser.add_argument("--base-url", default=settings.ollama_base_url, help="Provider Base URL")
    parser.add_argument(
        "--embedding-provider",
        choices=["ollama", "sentence_transformers"],
        default=settings.embedding_provider,
        help="Embedding-Provider für Query+Vektorsuche",
    )
    parser.add_argument(
        "--embedding-model",
        default=settings.ollama_embed_model,
        help="Embedding-Modell für Query+Vektorsuche",
    )
    parser.add_argument(
        "--ollama-url",
        default=settings.ollama_base_url,
        help="Ollama Base URL für Chat + Embeddings",
    )
    parser.add_argument(
        "--disable-reranker",
        action="store_true",
        help="Lokalen Reranker deaktivieren und direkt Hybrid-Treffer verwenden",
    )
    parser.add_argument(
        "--reranker-model",
        default=settings.reranker_model,
        help="Lokales Reranker-Modell",
    )
    parser.add_argument(
        "--reranker-device",
        default=settings.reranker_device,
        help="Optionales Device für den Reranker (z. B. mps, cpu, cuda)",
    )
    parser.add_argument(
        "--source-filter",
        action="append",
        default=[],
        help="Optionaler Quellenfilter; mehrfach verwendbar, z. B. --source-filter confluence",
    )
    return parser.parse_args()


def _build_provider(args: argparse.Namespace) -> OllamaProvider:
    if args.provider == "ollama":
        return OllamaProvider(model_name=args.model, base_url=args.base_url)
    raise ValueError(f"Unsupported provider: {args.provider}")


def main() -> int:
    args = parse_args()
    logger = AppLogger.get_logger()

    try:
        embedding_provider = build_embedding_provider(
            provider_name=args.embedding_provider,
            model_name=args.embedding_model,
            ollama_base_url=args.ollama_url,
        )
    except EmbeddingProviderError as error:
        logger.error("Embedding provider setup failed: %s", error)
        print(f"Fehler beim Embedding-Setup: {error}")
        return 2

    reranker = None
    if not args.disable_reranker:
        reranker = SentenceTransformerReranker(
            model_name=args.reranker_model,
            device=args.reranker_device,
        )

    provider = _build_provider(args)
    executor = AnswerExecutor.from_data_root(
        llm_provider=provider,
        data_root=args.root,
        keyword_weight=args.keyword_weight,
        vector_weight=args.vector_weight,
        max_context_chars=args.max_context_chars,
        embedding_provider=embedding_provider,
        reranker=reranker,
        candidate_k=args.candidate_k,
        final_k=args.top_k,
        reranker_enabled=not args.disable_reranker,
        reranker_model=args.reranker_model,
        reranker_device=args.reranker_device,
    )

    try:
        payload = executor.answer(
            args.query,
            top_k=max(1, args.top_k),
            candidate_k=max(1, args.candidate_k),
            source_filters=args.source_filter,
        )
    except (OllamaProviderError, EmbeddingProviderError, RerankerError, ValueError) as error:
        logger.error("Provider error: %s", error)
        print(f"Fehler beim Aufruf ({provider.provider_name}/{provider.model_name}): {error}")
        return 2
    except Exception as error:  # pragma: no cover - defensive fallback for CLI users
        logger.error("Unexpected error in answer CLI: %s", error)
        print(f"Unerwarteter Fehler: {error}")
        return 1

    results = payload["results"]
    candidate_results = payload.get("candidate_results", [])
    sources = payload["sources"]
    prompt = payload["prompt"]
    answer_text = payload["answer_text"]

    logger.info(
        "answer CLI query=%s hits=%s context_chars=%s prompt_chars=%s provider=%s model=%s embedding_provider=%s embedding_model=%s",
        payload["query"],
        len(results),
        len(payload["context"]),
        len(prompt),
        provider.provider_name,
        provider.model_name,
        embedding_provider.provider_name,
        embedding_provider.model_name,
    )

    print("=" * 80)
    print("Query")
    print("=" * 80)
    print(payload["query"])
    print()

    print("=" * 80)
    print("Antwort")
    print("=" * 80)
    print(answer_text)
    print()

    debug = payload.get("debug", {})
    if debug:
        print("=" * 80)
        print("Retrieval Debug")
        print("=" * 80)
        print(
            f"candidate_k={debug.get('candidate_k')} | retrieved_candidates={debug.get('retrieved_candidates')} "
            f"| final_k={debug.get('final_k')} | final_results={debug.get('final_results')}"
        )
        print(
            f"reranker_enabled={debug.get('reranker_enabled')} | reranker_model={debug.get('reranker_model')}"
        )
        if debug.get("source_filters"):
            print(f"source_filters={', '.join(debug['source_filters'])}")
        print()

    print("=" * 80)
    print(f"Quellen ({len(sources)})")
    print("=" * 80)
    if not sources:
        print("Keine Quellen vorhanden.")
    else:
        for source in sources:
            section = source.get("section_header")
            print(
                f"[{source['source_number']}] title={source['title']} | doc_id={source['doc_id']} "
                f"| chunk_id={source['chunk_id']} | score={source['score']:.4f}"
            )
            if section:
                print(f"    section={section}")
            if source.get("source_ref"):
                print(f"    source_ref={source['source_ref']}")

    if candidate_results:
        print()
        print("=" * 80)
        print(f"Kandidaten vor Reranking ({len(candidate_results)})")
        print("=" * 80)
        for candidate in candidate_results[: min(10, len(candidate_results))]:
            rerank_suffix = ""
            if candidate.rerank_score is not None:
                rerank_suffix = f" | rerank_score={candidate.rerank_score:.4f}"
            print(
                f"{candidate.chunk_id} | doc_id={candidate.doc_id} | score={candidate.score:.4f}{rerank_suffix}"
            )

    llm_response = payload.get("llm_response")
    if llm_response:
        print()
        print("=" * 80)
        print("LLM Metadaten")
        print("=" * 80)
        print(f"provider={llm_response['provider_name']} | model={llm_response['model_name']}")
        print(
            f"prompt_chars={llm_response['prompt_chars']} | response_chars={llm_response['response_chars']}"
        )
        if llm_response.get("latency_ms") is not None:
            print(f"latency_ms={llm_response['latency_ms']:.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
