"""Hilfsfunktionen für die Behandlung von Confluence-Seiteneigenschaften.

Das Modul kapselt:
- Normalisierung von Property-Keys für den Vergleich.
- Konfigurationsgetriebenes Mapping für Frontmatter-Promotion.
- Aufbereitung spezieller Value-Typen (z. B. Listenfelder).
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from common.config import AppConfig


@dataclass(frozen=True, slots=True)
class PropertyPromotionRule:
    """Regel für ein Seiteneigenschafts-Frontmatter-Feld."""

    aliases: tuple[str, ...]
    list_value: bool = False


DEFAULT_PROPERTY_PROMOTION: dict[str, PropertyPromotionRule] = {
    "auftraggeber": PropertyPromotionRule(aliases=("auftraggeber",)),
    "auftragnehmer": PropertyPromotionRule(aliases=("auftragnehmer",)),
    "aufwand": PropertyPromotionRule(aliases=("aufwand",)),
    "auslöser": PropertyPromotionRule(aliases=("auslöser", "ausloeser")),
    "betroffene einheiten": PropertyPromotionRule(
        aliases=("betroffene einheiten",),
        list_value=True,
    ),
    "jira": PropertyPromotionRule(aliases=("jira",)),
    "komponente": PropertyPromotionRule(aliases=("komponente",)),
    "komplexität": PropertyPromotionRule(aliases=("komplexität", "komplexitaet")),
    "modul/oft": PropertyPromotionRule(aliases=("modul/oft", "modul oft")),
    "priorität": PropertyPromotionRule(aliases=("priorität", "prioritaet", "prio")),
    "sponsoring": PropertyPromotionRule(aliases=("sponsoring",)),
    "status": PropertyPromotionRule(aliases=("status",)),
    "streamlead": PropertyPromotionRule(aliases=("streamlead",)),
    "type": PropertyPromotionRule(aliases=("type",)),
}


def normalize_property_key(value: str) -> str:
    """Normalisiert Schlüssel robust für case-/format-insensitiven Vergleich."""
    normalized = value.strip().lower()
    normalized = normalized.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r"[^a-z0-9\s_-]", "", normalized)
    normalized = re.sub(r"[_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def load_property_promotion_rules() -> dict[str, PropertyPromotionRule]:
    """Lädt die zu promotenden Seiteneigenschafts-Keys aus der TOML-Konfiguration.

    Wenn keine Konfiguration hinterlegt ist, wird auf ein sinnvolles Default-Set
    zurückgefallen.
    """
    configured_keys = AppConfig.get("confluence_transform", "page_properties_frontmatter_keys", default=None)
    if not isinstance(configured_keys, list) or not configured_keys:
        return DEFAULT_PROPERTY_PROMOTION

    normalized_requested = {normalize_property_key(str(key)) for key in configured_keys if str(key).strip()}
    if not normalized_requested:
        return DEFAULT_PROPERTY_PROMOTION

    selected_rules: dict[str, PropertyPromotionRule] = {}
    for canonical_key, rule in DEFAULT_PROPERTY_PROMOTION.items():
        alias_keys = {normalize_property_key(alias) for alias in rule.aliases}
        alias_keys.add(normalize_property_key(canonical_key))
        if alias_keys & normalized_requested:
            selected_rules[canonical_key] = rule
    return selected_rules or DEFAULT_PROPERTY_PROMOTION


def normalize_property_value(value: str, *, list_value: bool) -> str | list[str] | None:
    """Bereinigt Values für Frontmatter-Felder."""
    compact = re.sub(r"\s+", " ", value).strip()
    if not compact:
        return None
    if not list_value:
        return compact
    parts = [part.strip() for part in re.split(r"[,;]", compact) if part.strip()]
    return parts if parts else None


def match_promoted_key(
    key: str,
    rules: dict[str, PropertyPromotionRule],
) -> tuple[str, PropertyPromotionRule] | None:
    """Findet den kanonischen Frontmatter-Key für ein beliebiges Label."""
    normalized = normalize_property_key(key)
    if not normalized:
        return None
    for canonical_key, rule in rules.items():
        valid = {normalize_property_key(alias) for alias in rule.aliases}
        valid.add(normalize_property_key(canonical_key))
        if normalized in valid:
            return canonical_key, rule
    return None


def build_frontmatter_promoted_properties(
    page_properties: dict[str, object],
    rules: dict[str, PropertyPromotionRule],
) -> dict[str, object]:
    """Erstellt die Top-Level-Frontmatter-Einträge aus Seiteneigenschaften."""
    promoted: dict[str, object] = {}
    for key, raw_value in page_properties.items():
        key_match = match_promoted_key(str(key), rules)
        if not key_match:
            continue
        canonical_key, rule = key_match
        value = normalize_property_value(str(raw_value), list_value=rule.list_value)
        if value is None or canonical_key in promoted:
            continue
        promoted[canonical_key] = value
    return promoted


def filtered_renderable_property_keys(
    pairs: Iterable[tuple[str, str]],
    rules: dict[str, PropertyPromotionRule],
) -> set[str]:
    """Liefert die Key-Labels, die im Text *nicht* mehr gerendert werden sollen."""
    hidden_keys: set[str] = set()
    for key, value in pairs:
        key_match = match_promoted_key(key, rules)
        if not key_match:
            continue
        _, rule = key_match
        if normalize_property_value(value, list_value=rule.list_value) is None:
            continue
        hidden_keys.add(key)
    return hidden_keys

