#!/usr/bin/env python3
"""Bereitet ein QA-Payload inkl. Prompt und Quellen vor (ohne LLM-Call)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from retrieval.answer_pipeline import AnswerPipeline
from retrieval.keyword_search import SearchResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare answer payload from local retrieval")
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
    return parser.parse_args()


def _print_result(index: int, result: SearchResult) -> None:
    print(f"{index}. score={result.score:.2f} | title={result.title}")
    print(f"   doc_id={result.doc_id} | chunk_id={result.chunk_id}")
    if result.section_header:
        print(f"   section={result.section_header}")
    if result.source_ref:
        print(f"   source_ref={result.source_ref}")


def main() -> int:
    args = parse_args()
    logger = AppLogger.get_logger()
    top_k = max(1, args.top_k)

    pipeline = AnswerPipeline.from_data_root(
        data_root=args.root,
        keyword_weight=args.keyword_weight,
        vector_weight=args.vector_weight,
        max_context_chars=args.max_context_chars,
    )

    payload = pipeline.prepare_answer(args.query, top_k=top_k)

    query = payload["query"]
    results: list[SearchResult] = payload["results"]
    context = payload["context"]
    prompt = payload["prompt"]
    sources = payload["sources"]

    logger.info(
        "prepare_answer CLI query=%s hits=%s context_chars=%s prompt_chars=%s sources=%s",
        query,
        len(results),
        len(context),
        len(prompt),
        len(sources),
    )

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
    print(f"Quellen ({len(sources)})")
    print("=" * 80)
    if not sources:
        print("Keine Quellen vorhanden.")
    else:
        for source in sources:
            section = source.get("section_header")
            line = (
                f"[{source['source_number']}] title={source['title']} | doc_id={source['doc_id']} "
                f"| chunk_id={source['chunk_id']} | score={source['score']:.4f}"
            )
            print(line)
            if section:
                print(f"    section={section}")
            if source.get("source_ref"):
                print(f"    source_ref={source['source_ref']}")

    print()
    print("=" * 80)
    print(f"Generierter Prompt ({len(prompt)} Zeichen)")
    print("=" * 80)
    print(prompt)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
