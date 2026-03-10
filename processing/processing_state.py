"""Persistenter Minimalzustand für inkrementelle Ingestion-Läufe.

Der Zustand speichert pro Dokument die zuletzt verarbeitete Checksumme und
Basis-Metadaten, damit unveränderte Quellen im nächsten Lauf übersprungen
werden können.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProcessingStateRecord:
    """Zuletzt bekannter Verarbeitungsstand eines Dokuments."""

    source_checksum: str
    normalized_checksum: str
    last_processed_at: str
    title: str
    source_ref: str


@dataclass(slots=True)
class ProcessingState:
    """Container für den persistierten Zustand über alle Dokumente."""

    documents: dict[str, ProcessingStateRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> ProcessingState:
        """Lädt den Zustand aus JSON oder liefert leeren Default bei Erstlauf."""
        target = path.expanduser().resolve()
        if not target.exists():
            return cls()

        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_documents: dict[str, Any] = payload.get("documents", {})

        documents: dict[str, ProcessingStateRecord] = {}
        for doc_id, record in raw_documents.items():
            documents[doc_id] = ProcessingStateRecord(
                source_checksum=str(record.get("source_checksum", "")),
                normalized_checksum=str(record.get("normalized_checksum", "")),
                last_processed_at=str(record.get("last_processed_at", "")),
                title=str(record.get("title", "")),
                source_ref=str(record.get("source_ref", "")),
            )

        return cls(documents=documents)

    def save(self, path: Path) -> None:
        """Persistiert den Zustand als JSON-Datei."""
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")

    def update_document(
        self,
        doc_id: str,
        source_checksum: str,
        normalized_checksum: str,
        last_processed_at: str,
        title: str,
        source_ref: str,
    ) -> None:
        """Schreibt oder ersetzt den Stand eines Dokuments im Speicher."""
        self.documents[doc_id] = ProcessingStateRecord(
            source_checksum=source_checksum,
            normalized_checksum=normalized_checksum,
            last_processed_at=last_processed_at,
            title=title,
            source_ref=source_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den vollständigen Zustand als Dictionary."""
        return {"documents": {doc_id: asdict(record) for doc_id, record in self.documents.items()}}

    def to_json(self) -> str:
        """Serialisiert den vollständigen Zustand als JSON-String."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
