from __future__ import annotations

from pathlib import Path
from typing import Iterator

from common.logging_setup import AppLogger
from sources.document import SourceDocument, SourceInfo, build_filesystem_doc_id

logger = AppLogger.get_logger()


class FilesystemLoader:
    IGNORE_FILES = {"README.md", "readme.md", "_index.md"}

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def load(self) -> Iterator[SourceDocument]:
        """Yield markdown documents from the configured root recursively."""
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

            metadata = {
                "relative_path": relative_path,
                "filename": file_path.name,
                "extension": file_path.suffix.lower(),
                "size_bytes": stat.st_size,
            }

            yield SourceDocument(
                doc_id=build_filesystem_doc_id(self.root, file_path),
                title=file_path.stem,
                content=content,
                content_type="text/markdown",
                source=source,
                metadata=metadata,
            )

        logger.info("FilesystemLoader finished. Root: %s", self.root)
