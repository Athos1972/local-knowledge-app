from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


@dataclass(slots=True)
class ParsedFrontmatter:
    metadata: dict[str, Any] = field(default_factory=dict)
    body: str = ""


class FrontmatterParser:
    """Small parser for markdown frontmatter delimited by --- lines."""

    @classmethod
    def parse(cls, text: str) -> ParsedFrontmatter:
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
            return ParsedFrontmatter(metadata={}, body=text)

        metadata_block = "\n".join(lines[1:end_index])
        body = "\n".join(lines[end_index + 1 :])

        metadata = cls._parse_metadata(metadata_block)
        metadata["tags"] = cls._normalize_tags(metadata.get("tags"))

        return ParsedFrontmatter(metadata=metadata, body=body)

    @staticmethod
    def _parse_metadata(block: str) -> dict[str, Any]:
        if not block.strip():
            return {}

        if yaml is not None:
            try:
                parsed = yaml.safe_load(block)
            except Exception:
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
        return metadata

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []
