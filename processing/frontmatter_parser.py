"""Parser für YAML-ähnliches Frontmatter ohne externe Abhängigkeiten."""

from __future__ import annotations

import re


class FrontmatterParser:
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

    @classmethod
    def parse(cls, text: str) -> tuple[dict, str]:
        """Extrahiert Frontmatter und gibt Metadaten + Body zurück."""
        match = cls.FRONTMATTER_PATTERN.match(text)
        if not match:
            return {}, text

        metadata_block = match.group(1)
        body = match.group(2)
        return cls._parse_simple_yaml(metadata_block), body

    @staticmethod
    def _parse_simple_yaml(block: str) -> dict:
        """Parst einfache `key: value`-Paare für MVP-Zwecke."""
        metadata: dict[str, str] = {}
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue

            key, value = stripped.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"').strip("'")
        return metadata
