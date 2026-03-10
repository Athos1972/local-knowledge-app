from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(slots=True)
class SourceDocument:
    """Rohdokument aus einer Quelle (z. B. Dateisystem)."""

    id: str
    title: str
    text: str
    source: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        """Liefert eine stabile Referenz auf die Quelle."""
        return self.path

    @property
    def source_checksum(self) -> str:
        """Checksumme über den relevanten Input für Incremental-Checks."""
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class NormalizedDocument:
    """Normalisierte Form eines Dokuments für Persistierung und Chunking."""

    doc_id: str
    title: str
    content: str
    source_ref: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_checksum(self) -> str:
        return sha256(self.content.encode("utf-8")).hexdigest()


# Rückwärtskompatibilität für bestehenden Loader-Code.
Document = SourceDocument
