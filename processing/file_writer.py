"""Dateibasierter Output für die Ingestion-Pipeline.

Dieses Modul persistiert normalisierte Dokumente und Chunks unterhalb von
`processed/` in klar getrennten Ablageorten für Body, Metadaten und Chunk-JSONL.
"""

from __future__ import annotations

import json
from pathlib import Path

from common.logging_setup import AppLogger
from sources.document import ChunkDocument, NormalizedDocument

logger = AppLogger.get_logger()


class FileWriter:
    """Schreibt Pipeline-Artefakte in die processed-Verzeichnisstruktur."""

    def __init__(self, data_root: Path):
        """Initialisiert Zielpfade und legt erforderliche Ordner bei Bedarf an."""
        self.data_root = data_root.expanduser().resolve()
        self.documents_dir = self.data_root / "processed" / "documents"
        self.metadata_dir = self.data_root / "processed" / "metadata"
        self.chunks_dir = self.data_root / "processed" / "chunks"

        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def write_document(self, doc: NormalizedDocument) -> None:
        """Schreibt Dokument-Body als Markdown und vollständige Metadaten als JSON."""
        document_path = self.documents_dir / f"{doc.doc_id}.md"
        metadata_path = self.metadata_dir / f"{doc.doc_id}.json"

        document_path.write_text(doc.body, encoding="utf-8")
        metadata_path.write_text(
            json.dumps(doc.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("Wrote document and metadata for doc_id=%s", doc.doc_id)

    def write_chunks(self, doc_id: str, chunks: list[ChunkDocument]) -> None:
        """Schreibt Chunks eines Dokuments als JSONL-Datei."""
        chunks_path = self.chunks_dir / f"{doc_id}.jsonl"

        with chunks_path.open("w", encoding="utf-8") as file_handle:
            for chunk in chunks:
                file_handle.write(chunk.to_json())
                file_handle.write("\n")

        logger.debug("Wrote %s chunks for doc_id=%s", len(chunks), doc_id)
