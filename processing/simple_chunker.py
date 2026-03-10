"""Einfacher, deterministischer Chunking-Schritt für normalisierte Dokumente.

Das Modul zerlegt den Body eines Dokuments zeichenbasiert in überlappende
Chunks und gibt eine Liste von `ChunkDocument`-Objekten zurück.
"""

from __future__ import annotations

from common.logging_setup import AppLogger
from sources.document import ChunkDocument, NormalizedDocument, stable_hash

logger = AppLogger.get_logger()


class SimpleChunker:
    """Erzeugt überlappende Text-Chunks für ein normalisiertes Dokument."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 150):
        """Initialisiert Chunk-Größe und Overlap mit einfacher Validierung."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(self, doc: NormalizedDocument) -> list[ChunkDocument]:
        """Zerlegt ein Dokument in nicht-leere Chunks und annotiert Chunk-Metadaten."""
        text = doc.body.strip()
        if not text:
            logger.debug("Skipping chunking for empty body. doc_id=%s", doc.doc_id)
            return []

        chunks: list[ChunkDocument] = []
        step = self.chunk_size - self.overlap

        for index, start in enumerate(range(0, len(text), step)):
            raw_chunk = text[start : start + self.chunk_size]
            chunk_text = raw_chunk.strip()
            if not chunk_text:
                continue

            chunk_id = f"{doc.doc_id}-chunk-{index:04d}"
            chunk = ChunkDocument(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                chunk_index=index,
                text=chunk_text,
                title=doc.title,
                doc_type=doc.doc_type,
                source_type=doc.source.source_type,
                source_name=doc.source.source_name,
                metadata={"chunk_start": start, "chunk_end": start + len(raw_chunk)},
                checksum=stable_hash(chunk_text),
            )
            chunks.append(chunk)

            if start + self.chunk_size >= len(text):
                break

        logger.debug("Chunked doc_id=%s into %s chunks", doc.doc_id, len(chunks))
        return chunks
