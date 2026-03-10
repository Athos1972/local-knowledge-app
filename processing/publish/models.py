"""Datenmodelle für den Confluence-Publish-Schritt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StagingDocument:
    """Repräsentiert eine stagingbasierte Markdown-Datei mit Frontmatter."""

    input_file: Path
    metadata: dict[str, Any]
    body: str
    raw_text: str

    @property
    def space_key(self) -> str:
        """Liefert den Space-Key aus dem Frontmatter oder einen leeren String."""
        return str(self.metadata.get("space_key", "")).strip()

    @property
    def page_id(self) -> str:
        """Liefert die Seiten-ID aus dem Frontmatter oder einen leeren String."""
        return str(self.metadata.get("page_id", "")).strip()

    @property
    def title(self) -> str:
        """Liefert den Seitentitel aus dem Frontmatter oder Dateinamen."""
        value = str(self.metadata.get("title", "")).strip()
        if value:
            return value
        return self.input_file.stem


@dataclass(slots=True)
class ResolvedPublishTarget:
    """Beschreibt den aufgelösten Zielpfad und den Mapping-Status."""

    output_file: Path
    domain_path: str
    mapping_status: str


@dataclass(slots=True)
class PublishResult:
    """Ergebnis der Verarbeitung einer einzelnen Staging-Datei."""

    status: str
    warning_count: int
    input_file: Path
    output_file: Path | None
    page_id: str
    title: str
    space_key: str
    source_checksum: str
    output_checksum: str
