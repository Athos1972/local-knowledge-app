"""Manifest-Modelle für einen einzelnen Ingestion-Lauf.

Das Manifest dokumentiert Laufmetadaten sowie den Status pro Dokument
(inkl. Checksummen), damit Verarbeitung und Diagnose nachvollziehbar bleiben.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import uuid
from typing import Any


def generate_run_id() -> str:
    """Erzeugt eine kompakte, eindeutige Run-ID mit Zeitstempelpräfix."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{timestamp}-{uuid.uuid4().hex[:8]}"


@dataclass(slots=True)
class ProcessedDocumentRecord:
    """Ergebnisdatensatz eines einzelnen Dokuments innerhalb eines Laufs."""

    doc_id: str
    source_ref: str
    title: str
    source_checksum: str
    normalized_checksum: str
    chunk_count: int
    processed_at: str
    status: str


@dataclass(slots=True)
class RunManifest:
    """Zusammenfassung und Detailstatus für einen Ingestion-Lauf."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    run_duration: float = 0.0
    run_duration_human: str = "0s"
    source_name: str = "local-knowledge-data"
    mode: str = "incremental"
    documents_seen: int = 0
    documents_processed: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    records: list[ProcessedDocumentRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert Manifest und Records als Python-Dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialisiert Manifest als JSON-String."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
