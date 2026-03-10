"""Normalisierungsschritt für Markdown-Quellen.

Dieses Modul transformiert ein `SourceDocument` in ein fachlich angereichertes
`NormalizedDocument`, entfernt Frontmatter aus dem Body und führt Metadaten
konsistent zusammen.
"""

from __future__ import annotations

from typing import Any

from common.logging_setup import AppLogger
from processing.frontmatter_parser import FrontmatterParser
from sources.document import NormalizedDocument, SourceDocument, stable_hash

logger = AppLogger.get_logger()


class MarkdownNormalizer:
    """Normalisiert Markdown-Quelldokumente für nachgelagerte Verarbeitungsschritte."""

    def normalize(self, source_doc: SourceDocument) -> NormalizedDocument:
        """Erzeugt aus einem `SourceDocument` ein konsistentes `NormalizedDocument`."""
        parsed = FrontmatterParser.parse(source_doc.content)
        frontmatter = parsed.metadata

        title = self._pick_title(frontmatter.get("title"), source_doc)
        body = parsed.body.strip()
        metadata = self._merge_metadata(source_doc.metadata, frontmatter)

        normalized = NormalizedDocument(
            doc_id=source_doc.doc_id,
            title=title,
            body=body,
            doc_type=str(frontmatter.get("doc_type", "document")),
            mime_type="text/markdown",
            source=source_doc.source,
            created_at=source_doc.created_at,
            updated_at=source_doc.updated_at,
            language=self._optional_str(frontmatter.get("language")) or source_doc.language,
            author=self._optional_str(frontmatter.get("author")),
            tags=frontmatter.get("tags", []),
            metadata=metadata,
        )
        normalized.checksum = stable_hash(normalized.body)

        logger.debug(
            "Normalized doc_id=%s title=%s tags=%s metadata_keys=%s",
            normalized.doc_id,
            normalized.title,
            len(normalized.tags),
            len(normalized.metadata),
        )
        return normalized

    @staticmethod
    def _pick_title(frontmatter_title: Any, source_doc: SourceDocument) -> str:
        """Ermittelt den Dokumenttitel über definierte Fallback-Reihenfolge."""
        if isinstance(frontmatter_title, str) and frontmatter_title.strip():
            return frontmatter_title.strip()
        if source_doc.title.strip():
            return source_doc.title.strip()
        return source_doc.source.source_ref

    @staticmethod
    def _merge_metadata(base: dict[str, Any], frontmatter: dict[str, Any]) -> dict[str, Any]:
        """Führt Source-Metadaten und Frontmatter-Metadaten zusammen."""
        merged = dict(base)
        merged.update(frontmatter)
        return merged

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        """Normalisiert optionale String-Felder auf `str | None`."""
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
