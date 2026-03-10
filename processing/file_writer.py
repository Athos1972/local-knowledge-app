from __future__ import annotations

import json
from pathlib import Path

from sources.document import ChunkDocument, NormalizedDocument


class FileWriter:
    def __init__(self, data_root: Path):
        self.data_root = data_root.expanduser().resolve()
        self.documents_dir = self.data_root / "processed" / "documents"
        self.metadata_dir = self.data_root / "processed" / "metadata"
        self.chunks_dir = self.data_root / "processed" / "chunks"

        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def write_document(self, doc: NormalizedDocument) -> None:
        document_path = self.documents_dir / f"{doc.doc_id}.md"
        metadata_path = self.metadata_dir / f"{doc.doc_id}.json"

        document_path.write_text(doc.body, encoding="utf-8")
        metadata_path.write_text(
            json.dumps(doc.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_chunks(self, doc_id: str, chunks: list[ChunkDocument]) -> None:
        chunks_path = self.chunks_dir / f"{doc_id}.jsonl"

        with chunks_path.open("w", encoding="utf-8") as file_handle:
            for chunk in chunks:
                file_handle.write(chunk.to_json())
                file_handle.write("\n")
