#!/usr/bin/env python3
"""Ausführbares MVP-Ingestion-Script für lokale Markdown-Quellen.

Ablauf pro Dokument:
1) Laden über FilesystemLoader
2) Normalisieren (inkl. Frontmatter)
3) Schreiben von Dokument + Metadaten
4) Chunking
5) Schreiben der Chunks
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from processing.file_writer import FileWriter
from processing.markdown_normalizer import MarkdownNormalizer
from processing.simple_chunker import SimpleChunker
from sources.filesystem.filesystem_loader import FilesystemLoader


def main() -> int:
    """Führt die vollständige lokale Markdown-Ingestion für `~/local-knowledge-data` aus."""
    logger = AppLogger.get_logger()

    data_root = Path.home() / "local-knowledge-data"
    domains_root = data_root / "domains"

    loader = FilesystemLoader(domains_root)
    normalizer = MarkdownNormalizer()
    chunker = SimpleChunker()
    writer = FileWriter(data_root)

    processed_count = 0
    for source_doc in loader.load():
        normalized = normalizer.normalize(source_doc)
        writer.write_document(normalized)

        chunks = chunker.chunk_document(normalized)
        writer.write_chunks(normalized.doc_id, chunks)

        processed_count += 1
        logger.info(
            "Ingested doc_id=%s title=%s chunks=%s",
            normalized.doc_id,
            normalized.title,
            len(chunks),
        )

    logger.info("Ingestion completed. documents=%s", processed_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
