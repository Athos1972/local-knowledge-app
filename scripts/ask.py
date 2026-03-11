#!/usr/bin/env python3
"""Ask-Pipeline: erzeugt strukturierten Kontext aus Hybrid-Treffern (ohne LLM-Call)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from retrieval.ask_pipeline import AskPipeline
from retrieval.embedding_provider import EmbeddingProviderError
from retrieval.embedding_provider import build_embedding_provider
from retrieval.keyword_search import SearchResult
from retrieval.runtime_settings import RuntimeSettings


def parse_args() -> argparse.Namespace:
    settings = RuntimeSettings.load()
    parser = argparse.ArgumentParser(description="Build LLM context from local retrieval results")
    parser.add_argument("query", help="Suchanfrage, z. B. 'event mesh kyma'")
    parser.add_argument("--top-k", type=int, default=5, help="Anzahl Treffer (Standard: 5)")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "local-knowledge-data",
        help="Daten-Root mit processed/chunks, processed/metadata und index/",
    )
    parser.add_argument("--keyword-weight", type=float, default=0.5, help="Gewichtung Keyword in hybrid")
    parser.add_argument("--vector-weight", type=float, default=0.5, help="Gewichtung Vector in hybrid")
    parser.add_argument("--max-context-chars", type=int, default=8000, help="Maximale Kontextgröße")
    parser.add_argument("--embedding-provider", choices=["ollama", "sentence_transformers"], default=settings.embedding_provider)
    parser.add_argument("--embedding-model", default=settings.ollama_embed_model)
    parser.add_argument("--ollama-url", default=settings.ollama_base_url)
    return parser.parse_args()


def _print_result(index: int, result: SearchResult) -> None:
    print(f"{index}. score={result.score:.2f} | title={result.title}")
    print(f"   doc_id={result.doc_id} | chunk_id={result.chunk_id}")
    if result.section_header:
        print(f"   section={result.section_header}")


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
        print(f"Fehler beim Embedding-Setup: {error}")
        return 2

    pipeline = AskPipeline.from_data_root(
        data_root=args.root,
        keyword_weight=args.keyword_weight,
        vector_weight=args.vector_weight,
        max_context_chars=args.max_context_chars,
        embedding_provider=embedding_provider,
    )

    payload = pipeline.ask(args.query, top_k=args.top_k)

    query = payload["query"]
    results: list[SearchResult] = payload["results"]
    context = payload["context"]

    logger.info("Ask CLI query=%s hits=%s context_chars=%s", query, len(results), len(context))

    print("=" * 80)
    print("Query")
    print("=" * 80)
    print(query)
    print()

    print("=" * 80)
    print(f"Top Treffer ({len(results)})")
    print("=" * 80)
    if not results:
        print("Keine Treffer gefunden.")
    else:
        for idx, result in enumerate(results, start=1):
            _print_result(idx, result)
            print()

    print("=" * 80)
    print(f"Generierter Kontext ({len(context)} Zeichen)")
    print("=" * 80)
    if context:
        print(context)
    else:
        print("Kein Kontext generiert.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
