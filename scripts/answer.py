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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Answer question via retrieval + optional LLM provider")
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
    parser.add_argument("--provider", default="ollama", choices=["ollama"], help="Aktueller LLM-Provider")
    parser.add_argument("--model", default="llama3.1:8b", help="LLM-Modellname")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Provider Base URL")
    return parser.parse_args()


def _build_provider(args: argparse.Namespace) -> OllamaProvider:
    if args.provider == "ollama":
        return OllamaProvider(model_name=args.model, base_url=args.base_url)
    raise ValueError(f"Unsupported provider: {args.provider}")


def main() -> int:
    args = parse_args()
    logger = AppLogger.get_logger()

    provider = _build_provider(args)
    executor = AnswerExecutor.from_data_root(
        llm_provider=provider,
        data_root=args.root,
        keyword_weight=args.keyword_weight,
        vector_weight=args.vector_weight,
        max_context_chars=args.max_context_chars,
    )

    try:
        payload = executor.answer(args.query, top_k=max(1, args.top_k))
    except OllamaProviderError as error:
        logger.error("LLM provider error: %s", error)
        print(f"Fehler beim LLM-Aufruf ({provider.provider_name}/{provider.model_name}): {error}")
        return 2
    except Exception as error:  # pragma: no cover - defensive fallback for CLI users
        logger.error("Unexpected error in answer CLI: %s", error)
        print(f"Unerwarteter Fehler: {error}")
        return 1

    results = payload["results"]
    sources = payload["sources"]
    prompt = payload["prompt"]
    answer_text = payload["answer_text"]

    logger.info(
        "answer CLI query=%s hits=%s context_chars=%s prompt_chars=%s provider=%s model=%s",
        payload["query"],
        len(results),
        len(payload["context"]),
        len(prompt),
        provider.provider_name,
        provider.model_name,
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
