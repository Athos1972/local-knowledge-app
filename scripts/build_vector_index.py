#!/usr/bin/env python3
"""Erzeugt/aktualisiert den lokalen Vector-Index aus Chunk-JSONL-Dateien."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRepository
from retrieval.vector_index import VectorIndex


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build vector index from local chunks")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "local-knowledge-data",
        help="Daten-Root mit processed/chunks und index/",
    )
    parser.add_argument("--rebuild", action="store_true", help="Bestehenden Index vor Neuaufbau leeren")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = AppLogger.get_logger()

    repository = ChunkRepository(data_root=args.root)
    chunks = repository.load_chunks()
    logger.info("Loaded chunks for vector index build: %s", len(chunks))

    if not chunks:
        print("Keine Chunks gefunden. Bitte zuerst Ingestion ausführen.")
        return 1

    index_path = args.root.expanduser().resolve() / "index" / "vector_index.sqlite"
    index = VectorIndex(db_path=index_path)
    written = index.build(chunks, rebuild=args.rebuild)

    print(f"Vector index erfolgreich erstellt/aktualisiert: {index_path}")
    print(f"Gespeicherte Chunks: {written}")
    logger.info("Vector index build done. path=%s chunks=%s", index_path, written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
