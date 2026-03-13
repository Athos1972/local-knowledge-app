"""Datenmodelle für den Confluence-Transform-Schritt.

Die Modelle kapseln Rohdaten, transformierte Ergebnisse und Warnungen,
damit die Pipeline schrittweise und testbar bleibt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TransformWarning:
    """Strukturierte Warnung aus der Transformationspipeline."""

    code: str
    message: str
    context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Warnung als Dictionary."""
        return asdict(self)


@dataclass(slots=True)
class ConfluenceRawPage:
    """Rohdarstellung einer exportierten Confluence-Seite."""

    page_id: str
    space_key: str
    title: str
    body: str
    source_ref: str
    source_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    author: str | None = None
    labels: list[str] = field(default_factory=list)
    parent_title: str | None = None
    ancestors: list[str] = field(default_factory=list)
    page_properties: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConfluenceTransformedPage:
    """Transformiertes Dokument mit Frontmatter-fähigen Metadaten."""

    page_id: str
    space_key: str
    title: str
    body_markdown: str
    source_ref: str
    source_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    author: str | None = None
    labels: list[str] = field(default_factory=list)
    parent_title: str | None = None
    ancestors: list[str] = field(default_factory=list)
    page_properties: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    transform_warnings: list[TransformWarning] = field(default_factory=list)
    unsupported_macros: list[str] = field(default_factory=list)
    extra_documents: list[ConfluenceExtraDocument] = field(default_factory=list)
    content_hash: str = ""

    def warning_messages(self) -> list[str]:
        """Liefert die Warnungen als Liste kurzer Texte."""
        return [warning.message for warning in self.transform_warnings]


@dataclass(slots=True)
class ConfluenceExtraDocument:
    """Zusätzliches, aus einer Seite extrahiertes Markdown-Artefakt."""

    file_name: str
    title: str
    doc_type: str
    body_markdown: str
    metadata: dict[str, Any] = field(default_factory=dict)
