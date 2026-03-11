from __future__ import annotations

"""Einheitliches Frontmatter-Schema für Markdown-Dokumente.

Das Schema ist bewusst pragmatisch gehalten:
- klarer, quellenübergreifender Kern
- optionale Struktur-/Prozessfelder
- quellspezifische Informationen unter `source_meta`
"""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import yaml

CORE_REQUIRED_FIELDS: tuple[str, ...] = (
    "title",
    "source_type",
    "source_system",
    "source_key",
)

CORE_RECOMMENDED_FIELDS: tuple[str, ...] = (
    "status",
    "visibility",
    "updated_at",
    "imported_at",
)

LIST_FIELDS: tuple[str, ...] = ("tags", "authors", "attachments", "aliases")

DICT_FIELDS: tuple[str, ...] = ("source_meta",)

ALLOWED_STATUS: set[str] = {"raw", "draft", "reviewed", "curated"}
ALLOWED_VISIBILITY: set[str] = {"internal", "restricted", "public"}

FIELD_ORDER: tuple[str, ...] = (
    "title",
    "source_type",
    "source_system",
    "source_key",
    "source_url",
    "original_id",
    "original_path",
    "created_at",
    "updated_at",
    "imported_at",
    "status",
    "tags",
    "language",
    "authors",
    "visibility",
    "content_hash",
    "domain",
    "scope",
    "category",
    "subcategory",
    "customer",
    "project",
    "ingestion_source",
    "ingestion_job",
    "version",
    "attachments",
    "aliases",
    "source_meta",
)


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_frontmatter(**values: Any) -> dict[str, Any]:
    """Erzeugt ein normalisiertes Frontmatter-Dict aus übergebenen Werten."""
    data = normalize_frontmatter(values)
    if "imported_at" not in data:
        data["imported_at"] = utc_now_iso()
    return data


def normalize_frontmatter(data: dict[str, Any]) -> dict[str, Any]:
    """Normalisiert Datentypen, entfernt leere Werte und stabilisiert Schlüsselreihenfolge."""
    normalized = deepcopy(data)

    for field in LIST_FIELDS:
        normalized[field] = _as_string_list(normalized.get(field))

    for field in DICT_FIELDS:
        value = normalized.get(field)
        if value is None:
            normalized[field] = {}
        elif not isinstance(value, dict):
            normalized[field] = {"value": str(value)}

    for key in ("title", "source_type", "source_system", "source_key", "source_url", "original_id", "original_path"):
        if key in normalized and normalized[key] is not None:
            normalized[key] = str(normalized[key]).strip()

    if "status" in normalized and normalized["status"] is not None:
        normalized["status"] = str(normalized["status"]).strip().lower()

    if "visibility" in normalized and normalized["visibility"] is not None:
        normalized["visibility"] = str(normalized["visibility"]).strip().lower()

    compact = {k: v for k, v in normalized.items() if v not in (None, "", [], {})}
    return _ordered_frontmatter(compact)


def validate_frontmatter(data: dict[str, Any]) -> list[str]:
    """Liefert Validierungsfehler zurück, ohne Imports hart zu blockieren."""
    errors: list[str] = []

    for field in CORE_REQUIRED_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"'{field}' is required and must be a non-empty string")

    status = data.get("status")
    if isinstance(status, str) and status and status not in ALLOWED_STATUS:
        errors.append(f"'status' should be one of {sorted(ALLOWED_STATUS)}")

    visibility = data.get("visibility")
    if isinstance(visibility, str) and visibility and visibility not in ALLOWED_VISIBILITY:
        errors.append(f"'visibility' should be one of {sorted(ALLOWED_VISIBILITY)}")

    for field in LIST_FIELDS:
        if field in data and not isinstance(data[field], list):
            errors.append(f"'{field}' must be a list")

    if "source_meta" in data and not isinstance(data["source_meta"], dict):
        errors.append("'source_meta' must be a dictionary")

    return errors


def merge_frontmatter(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Merged bestehende Metadaten mit Updates; `source_meta` wird flach zusammengeführt."""
    merged = deepcopy(existing)

    for key, value in updates.items():
        if key == "source_meta" and isinstance(value, dict):
            source_meta = dict(merged.get("source_meta") or {})
            source_meta.update(value)
            merged["source_meta"] = source_meta
        else:
            merged[key] = value

    return normalize_frontmatter(merged)


def parse_frontmatter(markdown_text: str) -> tuple[dict[str, Any], str]:
    """Parst optionales YAML-Frontmatter am Dokumentanfang."""
    if not markdown_text.startswith("---"):
        return {}, markdown_text

    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown_text

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return {}, markdown_text

    raw_frontmatter = "\n".join(lines[1:end_index])
    body_text = "\n".join(lines[end_index + 1 :])

    parsed = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(parsed, dict):
        parsed = {}

    return normalize_frontmatter(parsed), body_text


def render_frontmatter(frontmatter: dict[str, Any], body_text: str) -> str:
    """Serialisiert Frontmatter zurück in Markdown mit stabilem Layout."""
    normalized = normalize_frontmatter(frontmatter)
    serialized = yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True).strip()
    body = body_text.lstrip("\n")
    return f"---\n{serialized}\n---\n\n{body}\n"


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _ordered_frontmatter(data: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in FIELD_ORDER:
        if key in data:
            ordered[key] = data[key]

    for key in sorted(k for k in data.keys() if k not in ordered):
        ordered[key] = data[key]

    return ordered
