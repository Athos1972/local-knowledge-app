"""Filesystem-Quelle für die Ingestion-Pipeline.

Dieses Modul scannt rekursiv eine Root-Struktur nach Markdown-Dateien,
überspringt definierte Dateinamen und liefert jede Datei als `SourceDocument`
inklusive technischer Dateimetadaten und Source-Referenz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from common.logging_setup import AppLogger
from sources.document import SourceDocument, SourceInfo, build_filesystem_doc_id

logger = AppLogger.get_logger()


class FilesystemLoader:
    """Lädt Markdown-Dokumente aus einer lokalen Verzeichnisstruktur."""

    IGNORE_FILES = {"README.md", "readme.md", "_index.md"}

    def __init__(self, root: Path):
        """Initialisiert den Loader mit einer Root, relativ zu der `source_ref` gebaut wird."""
        self.root = root.expanduser().resolve()

    def load(self) -> Iterator[SourceDocument]:
        """Liefert rekursiv alle gültigen Markdown-Dateien als `SourceDocument`."""
        logger.info("FilesystemLoader started. Root: %s", self.root)

        for file_path in sorted(self.root.rglob("*.md")):
            if file_path.name in self.IGNORE_FILES:
                logger.debug("Skipping ignored file: %s", file_path)
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                stat = file_path.stat()
            except OSError as exc:
                logger.warning("Failed reading file '%s': %s", file_path, exc)
                continue

            relative_path = file_path.relative_to(self.root).as_posix()
            source = SourceInfo(
                source_type="filesystem",
                source_name="local-knowledge-data",
                source_ref=relative_path,
                original_uri=file_path.resolve().as_uri(),
            )
            metadata = self._build_metadata(file_path, relative_path, stat.st_size)

            document = SourceDocument(
                doc_id=build_filesystem_doc_id(self.root, file_path),
                title=file_path.stem,
                content=content,
                content_type="text/markdown",
                source=source,
                metadata=metadata,
            )
            logger.debug("Loaded document '%s' as doc_id=%s", relative_path, document.doc_id)
            yield document

        logger.info("FilesystemLoader finished. Root: %s", self.root)

    @staticmethod
    def _build_metadata(file_path: Path, relative_path: str, size_bytes: int) -> dict[str, str | int]:
        """Erzeugt standardisierte Dateimetadaten für ein Source-Dokument."""
        return {
            "relative_path": relative_path,
            "filename": file_path.name,
            "extension": file_path.suffix.lower(),
            "size_bytes": size_bytes,
        }
