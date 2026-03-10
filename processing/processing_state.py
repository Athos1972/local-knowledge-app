from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DocumentState:
    source_checksum: str
    normalized_checksum: str
    last_processed_at: str
    title: str
    source_ref: str


@dataclass(slots=True)
class ProcessingState:
    documents: dict[str, DocumentState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ProcessingState":
        if not path.exists():
            return cls()

        raw = json.loads(path.read_text(encoding="utf-8"))
        documents: dict[str, DocumentState] = {}

        for doc_id, item in raw.get("documents", {}).items():
            documents[doc_id] = DocumentState(
                source_checksum=item.get("source_checksum", ""),
                normalized_checksum=item.get("normalized_checksum", ""),
                last_processed_at=item.get("last_processed_at", ""),
                title=item.get("title", ""),
                source_ref=item.get("source_ref", ""),
            )

        return cls(documents=documents)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "documents": {
                doc_id: {
                    "source_checksum": state.source_checksum,
                    "normalized_checksum": state.normalized_checksum,
                    "last_processed_at": state.last_processed_at,
                    "title": state.title,
                    "source_ref": state.source_ref,
                }
                for doc_id, state in self.documents.items()
            }
        }

        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
