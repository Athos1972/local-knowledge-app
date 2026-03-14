"""Writers for staged and published document markdown artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from processing.frontmatter_schema import render_frontmatter


@dataclass(slots=True)
class RenderedDocument:
    """Represents output paths for a transformed document."""

    staging_path: Path
    publish_path: Path


class DocumentsTransformWriter:
    """Writes transformed markdown to staging and publish targets."""

    def __init__(self, output_root: Path, publish_root: Path):
        self.output_root = output_root.expanduser().resolve()
        self.publish_root = publish_root.expanduser().resolve()

    def build_paths(self, *, relative_source_path: Path, domain: str, document_id: str, title: str) -> RenderedDocument:
        """Build stable and collision-resistant output paths for one source file."""
        relative_parent = relative_source_path.parent
        slug = self._slugify(title)
        suffix = document_id[:10]
        file_name = f"{slug}__{suffix}.md"
        staging_path = self.output_root / relative_parent / file_name
        publish_path = self.publish_root / domain / relative_parent / file_name
        return RenderedDocument(staging_path=staging_path, publish_path=publish_path)

    def write_document(self, *, paths: RenderedDocument, frontmatter: dict[str, object], markdown_body: str) -> None:
        """Write markdown with frontmatter to staging and publish roots."""
        content = render_frontmatter(frontmatter, markdown_body)
        self._write_text(paths.staging_path, content)
        self._write_text(paths.publish_path, content)

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _slugify(value: str) -> str:
        lower = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9äöüß\-\s]", "", lower)
        compact = re.sub(r"\s+", "-", normalized)
        return compact.strip("-") or "document"
