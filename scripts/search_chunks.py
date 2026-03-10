#!/usr/bin/env python3
"""Lokale Suche über verarbeitete Chunk-Dateien (Keyword, Vector, Hybrid)."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRepository
from retrieval.hybrid_search import HybridSearcher
from retrieval.keyword_search import KeywordSearcher
from retrieval.vector_search import VectorSearcher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search over local chunk JSONL files")
    parser.add_argument("query", help="Suchanfrage, z. B. 'event mesh kyma'")
    parser.add_argument("--top-k", type=int, default=5, help="Anzahl Treffer (Standard: 5)")
    parser.add_argument(
        "--mode",
        choices=["keyword", "vector", "hybrid"],
        default="hybrid",
        help="Retrieval-Modus (Standard: hybrid)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "local-knowledge-data",
        help="Daten-Root mit processed/chunks, processed/metadata und index/",
    )
    parser.add_argument("--keyword-weight", type=float, default=0.5, help="Gewichtung Keyword in hybrid")
    parser.add_argument("--vector-weight", type=float, default=0.5, help="Gewichtung Vector in hybrid")
    return parser.parse_args()


def build_preview(text: str, max_length: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 1].rstrip()}…"


def main() -> int:
    args = parse_args()
    logger = AppLogger.get_logger()

    repository = ChunkRepository(data_root=args.root)
    chunks = repository.load_chunks()
    logger.info("Loaded chunks=%s retrieval_mode=%s", len(chunks), args.mode)

    if not chunks:
        print("Keine Chunks gefunden. Bitte zuerst Ingestion ausführen.")
        return 1

    keyword_searcher = KeywordSearcher(chunks)
    vector_searcher = VectorSearcher(
        db_path=args.root.expanduser().resolve() / "index" / "vector_index.sqlite",
        chunks=chunks,
    )

    if args.mode == "keyword":
        results = keyword_searcher.search(args.query, top_k=args.top_k)
    elif args.mode == "vector":
        results = vector_searcher.search(args.query, top_k=args.top_k)
    else:
        searcher = HybridSearcher(
            keyword_searcher=keyword_searcher,
            vector_searcher=vector_searcher,
            keyword_weight=args.keyword_weight,
            vector_weight=args.vector_weight,
        )
        results = searcher.search(args.query, top_k=args.top_k)

    logger.info("Search query=%s mode=%s results=%s", args.query, args.mode, len(results))

    if not results:
        print(f"Keine Treffer für Query: {args.query!r}")
        return 0

    print(f"Treffer für Query: {args.query!r} (mode={args.mode})\n")
    for index, result in enumerate(results, start=1):
        print(f"{index}. score={result.score:.2f} | title={result.title}")
        print(f"   doc_id={result.doc_id} | chunk_id={result.chunk_id}")
        if result.section_header:
            print(f"   section={result.section_header}")
        if result.source_ref:
            print(f"   source_ref={result.source_ref}")
        print(f"   preview={build_preview(result.text)}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
