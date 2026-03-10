#!/usr/bin/env python3
"""Einfache lokale Keyword-Suche über verarbeitete Chunk-Dateien."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRepository
from retrieval.keyword_search import KeywordSearcher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search over local chunk JSONL files")
    parser.add_argument("query", help="Suchanfrage, z. B. 'event mesh kyma'")
    parser.add_argument("--top-k", type=int, default=5, help="Anzahl Treffer (Standard: 5)")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "local-knowledge-data",
        help="Daten-Root mit processed/chunks und processed/metadata",
    )
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
    if not chunks:
        print("Keine Chunks gefunden. Bitte zuerst Ingestion ausführen.")
        return 1

    searcher = KeywordSearcher(chunks)
    results = searcher.search(args.query, top_k=args.top_k)

    logger.info("Search query=%s results=%s", args.query, len(results))

    if not results:
        print(f"Keine Treffer für Query: {args.query!r}")
        return 0

    print(f"Treffer für Query: {args.query!r}\n")
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
