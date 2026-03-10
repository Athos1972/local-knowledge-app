"""Publisher für Confluence-Staging-Markdown in den Domains-Bereich."""

from __future__ import annotations

import logging
from pathlib import Path

from processing.publish.frontmatter_reader import FrontmatterReadError, FrontmatterReader
from processing.publish.mapping_config import ConfluencePublishConfig
from processing.publish.models import PublishResult, StagingDocument
from processing.publish.path_resolver import PublishPathResolver
from sources.document import stable_hash, utc_now_iso


class ConfluencePublisher:
    """Orchestriert Frontmatter-Lesen, Mapping, Schreiben und Metadaten-Anreicherung."""

    def __init__(self, config: ConfluencePublishConfig, logger: logging.Logger):
        self._config = config
        self._logger = logger
        self._reader = FrontmatterReader()
        self._resolver = PublishPathResolver(config)

    def discover_files(self, space_filter: str | None = None) -> list[Path]:
        """Findet alle Staging-Markdown-Dateien optional gefiltert nach Space-Key."""
        root = self._config.input_root
        files = sorted(root.rglob("*.md"))
        if not space_filter:
            return files
        return [path for path in files if f"/{space_filter}/" in path.as_posix()]

    def publish_file(self, file_path: Path) -> PublishResult:
        """Publiziert genau eine Datei inklusive Frontmatter-Metadaten."""
        try:
            document = self._reader.read(file_path)
        except FrontmatterReadError as exc:
            self._logger.warning("Datei übersprungen (Frontmatter-Fehler): file=%s reason=%s", file_path, exc)
            return PublishResult(
                status="error",
                warning_count=1,
                input_file=file_path,
                output_file=None,
                page_id="",
                title=file_path.stem,
                space_key="",
                source_checksum=stable_hash(file_path.read_text(encoding="utf-8")),
                output_checksum="",
            )

        source_checksum = stable_hash(document.raw_text)
        target = self._resolver.resolve(document)

        if target.mapping_status == "unmapped" and not self._config.publish_unmapped:
            self._logger.warning("Space nicht gemappt und publish_unmapped=false: space=%s file=%s", document.space_key, file_path)
            return PublishResult(
                status="unmapped",
                warning_count=1,
                input_file=file_path,
                output_file=None,
                page_id=document.page_id,
                title=document.title,
                space_key=document.space_key,
                source_checksum=source_checksum,
                output_checksum="",
            )

        output_markdown = self._build_publish_markdown(document=document, output_file=target.output_file, domain_path=target.domain_path)
        self._write_output(output_file=target.output_file, markdown=output_markdown)
        output_checksum = stable_hash(output_markdown)

        status = "published" if target.mapping_status == "mapped" else "unmapped"
        warning_count = 1 if status == "unmapped" else 0
        return PublishResult(
            status=status,
            warning_count=warning_count,
            input_file=file_path,
            output_file=target.output_file,
            page_id=document.page_id,
            title=document.title,
            space_key=document.space_key,
            source_checksum=source_checksum,
            output_checksum=output_checksum,
        )

    def _build_publish_markdown(self, document: StagingDocument, output_file: Path, domain_path: str) -> str:
        """Ergänzt Publish-Metadaten und rendert die finale Markdown-Datei."""
        metadata = dict(document.metadata)
        metadata["published_from"] = str(document.input_file)
        metadata["publish_source_root"] = str(self._config.input_root)
        metadata["publish_target_path"] = str(output_file)
        metadata["content_origin"] = "confluence"
        metadata["domain_path"] = domain_path
        metadata["published_at"] = utc_now_iso()
        return self._reader.render(metadata, document.body)

    def _write_output(self, output_file: Path, markdown: str) -> None:
        """Schreibt im Modus `copy` die materialisierte Zieldatei."""
        if self._config.mode != "copy":
            raise ValueError(f"Nicht unterstützter Publish-Mode: {self._config.mode}")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(markdown, encoding="utf-8")

