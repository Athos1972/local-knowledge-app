"""Regelwerk für Confluence-Page-Properties, die ins Frontmatter gemappt werden."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(slots=True)
class PagePropertyRules:
    """Kapselt konfigurierbare Regeln zur Key-Normalisierung und Wertverarbeitung."""

    configured_keys: set[str]
    aliases: dict[str, str]
    value_lists: dict[str, list[str]]

    @classmethod
    def load_default(cls, path: Path | None = None) -> "PagePropertyRules":
        """Lädt die Default-Regeln aus TOML-Datei."""
        target = path or Path("config/confluence_page_property_rules.toml")
        if not target.exists():
            return cls(configured_keys=set(), aliases={}, value_lists={})

        with target.open("rb") as handle:
            payload = tomllib.load(handle)

        frontmatter: dict[str, Any] = payload.get("frontmatter", {}) if isinstance(payload, dict) else {}
        keys = frontmatter.get("keys", []) if isinstance(frontmatter, dict) else []
        aliases = frontmatter.get("aliases", {}) if isinstance(frontmatter, dict) else {}
        value_lists = frontmatter.get("value_lists", {}) if isinstance(frontmatter, dict) else {}

        normalized_keys = {cls.normalize_key(str(key)) for key in keys if str(key).strip()}
        normalized_aliases = {
            cls.normalize_key(str(alias)): cls.normalize_key(str(target_key))
            for alias, target_key in aliases.items()
            if str(alias).strip() and str(target_key).strip()
        }
        normalized_lists = {
            cls.normalize_key(str(key)): [str(separator) for separator in separators if str(separator)]
            for key, separators in value_lists.items()
            if isinstance(separators, list)
        }
        return cls(configured_keys=normalized_keys, aliases=normalized_aliases, value_lists=normalized_lists)

    @staticmethod
    def normalize_key(value: str) -> str:
        """Normalisiert Label-Text robust und lowercase-fähig für Frontmatter-Keys."""
        lowered = value.strip().lower()
        cleaned = re.sub(r"\s+", " ", lowered)
        return cleaned.strip()

    def canonical_key(self, key: str) -> str:
        """Löst Aliase auf und liefert den kanonischen Key zurück."""
        normalized = self.normalize_key(key)
        return self.aliases.get(normalized, normalized)

    def split_value_if_list(self, key: str, value: str) -> str | list[str]:
        """Teilt Werte für definierte Listen-Keys anhand konfigurierter Trenner."""
        separators = self.value_lists.get(key, [])
        if not separators:
            return value

        parts = [value]
        for separator in separators:
            next_parts: list[str] = []
            for part in parts:
                next_parts.extend(part.split(separator))
            parts = next_parts

        cleaned = [part.strip() for part in parts if part.strip()]
        return cleaned if cleaned else value

    def is_frontmatter_key(self, key: str) -> bool:
        """Prüft, ob ein Key direkt ins Frontmatter verschoben werden soll."""
        return key in self.configured_keys
