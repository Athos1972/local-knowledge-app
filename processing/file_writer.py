from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from processing.simple_chunker import TextChunk
from sources.document import NormalizedDocument


class FileWriter:
    """Schreibt normalisierte Dokumente, Metadaten und Chunks in JSON-Dateien."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.documents_dir = self.base_dir / "processed" / "documents"
        self.metadata_dir = self.base_dir / "processed" / "metadata"
        self.chunks_dir = self.base_dir / "processed" / "chunks"

        for directory in (self.documents_dir, self.metadata_dir, self.chunks_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def write_document(self, doc: NormalizedDocument) -> None:
        payload = {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "source_ref": doc.source_ref,
            "content": doc.content,
        }
        self._write_json(self.documents_dir / f"{self._safe_name(doc.doc_id)}.json", payload)

    def write_metadata(self, doc: NormalizedDocument) -> None:
        payload: dict[str, Any] = {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "source_ref": doc.source_ref,
            "metadata": doc.metadata,
            "normalized_checksum": doc.normalized_checksum,
        }
        self._write_json(self.metadata_dir / f"{self._safe_name(doc.doc_id)}.json", payload)

    def write_chunks(self, doc_id: str, chunks: list[TextChunk]) -> None:
        payload = [
            {"doc_id": chunk.doc_id, "index": chunk.index, "text": chunk.text}
            for chunk in chunks
        ]
        self._write_json(self.chunks_dir / f"{self._safe_name(doc_id)}.json", payload)

    @staticmethod
    def _safe_name(value: str) -> str:
        return value.replace("/", "_").replace("\\", "_").replace(":", "_")

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
