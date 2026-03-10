"""Datei-Writer für transformierte Confluence-Markdown-Dokumente."""

from __future__ import annotations

from pathlib import Path
import re


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

    @staticmethod
    def _slugify(value: str) -> str:
        lower = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9äöüß\-\s]", "", lower)
        compact = re.sub(r"\s+", "-", normalized)
        return compact.strip("-") or "untitled"
