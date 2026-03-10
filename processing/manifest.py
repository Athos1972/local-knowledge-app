from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import uuid


def now_iso() -> str:
    """UTC-Zeitstempel im ISO-Format."""
    return datetime.now(UTC).isoformat()


def generate_run_id() -> str:
    """Kurze, stabile Run-ID für Logging und Manifest-Dateinamen."""
    return uuid.uuid4().hex[:12]


@dataclass(slots=True)
class ProcessedDocumentRecord:
    doc_id: str
    source_ref: str
    title: str
    source_checksum: str
    normalized_checksum: str
    chunk_count: int
    processed_at: str
    status: str  # processed, skipped, error


@dataclass(slots=True)
class RunManifest:
    run_id: str
    started_at: str
    finished_at: str | None = None
    source_name: str = "local-knowledge-data"
    mode: str = "incremental"
    documents_seen: int = 0
    documents_processed: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    records: list[ProcessedDocumentRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
