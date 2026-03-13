"""Datei-Writer für transformierte Confluence-Markdown-Dokumente."""

from __future__ import annotations

import json
from pathlib import Path
import re

from processing.confluence.models import ConfluenceExtraDocument, ConfluenceTransformedPage


class ConfluenceTransformWriter:
    """Schreibt transformierte Markdown-Dateien in Zielstruktur."""

    def __init__(self, output_root: Path):
        self.output_root = output_root.expanduser().resolve()

    def build_output_path(self, space_key: str, page_id: str, title: str) -> Path:
        slug = self._slugify(title)
        file_name = f"{page_id}__{slug}.md"
        return self.output_root / space_key.lower() / file_name

    def write_markdown(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_transformed_page(self, page_path: Path, markdown: str, page: ConfluenceTransformedPage) -> list[Path]:
        self.write_markdown(page_path, markdown)
        written_paths: list[Path] = [page_path]
        for document in page.extra_documents:
            doc_path = page_path.parent / document.file_name
            self.write_markdown(doc_path, self.render_extra_document(document))
            written_paths.append(doc_path)
        return written_paths

    def render_extra_document(self, document: ConfluenceExtraDocument) -> str:
        frontmatter = "\n".join(f"{key}: {self._yaml_value(value)}" for key, value in document.metadata.items())
        body = document.body_markdown.strip()
        return f"---\n{frontmatter}\n---\n\n{body}\n"

    @staticmethod
    def _yaml_value(value: object) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _slugify(value: str) -> str:
        lower = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9äöüß\-\s]", "", lower)
        compact = re.sub(r"\s+", "-", normalized)
        return compact.strip("-") or "untitled"
