"""State file for incremental local document transformations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DocumentTransformStateRecord:
    """Last known processing state for one document file."""

    source_checksum: str
    source_mtime: float
    source_size_bytes: int
    staging_output_file: str
    publish_output_file: str
    updated_at: str


@dataclass(slots=True)
class DocumentTransformState:
    """Incremental state for local documents transform runs."""

    documents: dict[str, DocumentTransformStateRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "DocumentTransformState":
        target = path.expanduser().resolve()
        if not target.exists():
            return cls()

        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_documents: dict[str, Any] = payload.get("documents", {})
        documents: dict[str, DocumentTransformStateRecord] = {}
        for document_id, record in raw_documents.items():
            documents[document_id] = DocumentTransformStateRecord(
                source_checksum=str(record.get("source_checksum", "")),
                source_mtime=float(record.get("source_mtime", 0.0) or 0.0),
                source_size_bytes=int(record.get("source_size_bytes", 0) or 0),
                staging_output_file=str(record.get("staging_output_file", "")),
                publish_output_file=str(record.get("publish_output_file", "")),
                updated_at=str(record.get("updated_at", "")),
            )
        return cls(documents=documents)

    def save(self, path: Path) -> None:
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {"documents": {doc_id: asdict(record) for doc_id, record in self.documents.items()}}
