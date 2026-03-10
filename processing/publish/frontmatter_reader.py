"""Frontmatter-I/O für den Publish-Schritt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from processing.frontmatter_parser import FrontmatterParser
from processing.publish.models import StagingDocument


class FrontmatterReadError(ValueError):
    """Signalisiert ungültige oder fehlende Frontmatter-Daten."""


class FrontmatterReader:
    """Liest Markdown-Dateien und rendert Markdown mit Frontmatter."""

    def read(self, file_path: Path) -> StagingDocument:
        """Liest eine Datei und validiert minimales Confluence-Frontmatter."""
        text = file_path.read_text(encoding="utf-8")
        parsed = FrontmatterParser.parse(text)
        metadata = parsed.metadata

        if not metadata:
            raise FrontmatterReadError("Frontmatter fehlt oder ist nicht lesbar")

        missing = [
            field
            for field in ("title", "source_type", "space_key", "page_id", "labels", "source_url")
            if field not in metadata
        ]
        if missing:
            raise FrontmatterReadError(f"Pflichtfelder fehlen: {', '.join(missing)}")

        return StagingDocument(input_file=file_path, metadata=metadata, body=parsed.body, raw_text=text)

    def render(self, metadata: dict[str, Any], body: str) -> str:
        """Rendert Frontmatter plus Body ohne inhaltliche Markdown-Transformation."""
        lines = ["---"]
        for key, value in metadata.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        lines.append("---")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
        return "\n".join(lines)
