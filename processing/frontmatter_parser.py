"""Robuster, bewusst einfacher Frontmatter-Parser für Markdown.

Das Modul erkennt Frontmatter nur am Dateianfang zwischen `---` und `---`,
parst Metadaten bevorzugt über PyYAML (falls vorhanden) und fällt ansonsten
auf eine kleine key/value-Logik zurück.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common.logging_setup import AppLogger

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

logger = AppLogger.get_logger()


@dataclass(slots=True)
class ParsedFrontmatter:
    """Kapselt geparste Frontmatter-Metadaten und den bereinigten Markdown-Body."""

    metadata: dict[str, Any] = field(default_factory=dict)
    body: str = ""


class FrontmatterParser:
    """Extrahiert und parst optionales Frontmatter am Beginn eines Markdown-Textes."""

    @classmethod
    def parse(cls, text: str) -> ParsedFrontmatter:
        """Parst Frontmatter und liefert immer ein valides `ParsedFrontmatter`-Objekt."""
        if not text.startswith("---"):
            return ParsedFrontmatter(metadata={}, body=text)

        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return ParsedFrontmatter(metadata={}, body=text)

        end_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                end_index = index
                break

        if end_index is None:
            logger.debug("Frontmatter start detected but no closing delimiter found.")
            return ParsedFrontmatter(metadata={}, body=text)

        metadata_block = "\n".join(lines[1:end_index])
        body = "\n".join(lines[end_index + 1 :])

        metadata = cls._parse_metadata(metadata_block)
        metadata["tags"] = cls._normalize_tags(metadata.get("tags"))
        return ParsedFrontmatter(metadata=metadata, body=body)

    @staticmethod
    def _parse_metadata(block: str) -> dict[str, Any]:
        """Parst einen Frontmatter-Block zu einem Dictionary."""
        if not block.strip():
            return {}

        if yaml is not None:
            try:
                parsed = yaml.safe_load(block)
            except Exception as exc:
                logger.warning("YAML frontmatter parsing failed, falling back to key/value parser: %s", exc)
                parsed = None
            if isinstance(parsed, dict):
                return parsed

        metadata: dict[str, Any] = {}
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")

        logger.debug("Parsed frontmatter with fallback parser. Keys=%s", list(metadata.keys()))
        return metadata

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        """Normalisiert `tags` auf eine bereinigte Liste von Strings."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []
