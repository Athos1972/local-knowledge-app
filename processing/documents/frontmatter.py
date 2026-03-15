"""Frontmatter builder for transformed local documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_document_frontmatter(
    *,
    title: str,
    source_origin: str,
    source_system: str,
    source_collection: str,
    source_path: str,
    logical_path: str,
    domain: str,
    document_id: str,
    aliases: list[str] | None,
    parent_metadata: dict[str, Any] | None,
    metadata: dict[str, Any],
    transformer_name: str,
    transformer_version: str | None,
) -> dict[str, Any]:
    """Build YAML frontmatter fields for a transformed file."""
    extension = str(metadata.get("extension", "")).lstrip(".").lower() or Path(source_path).suffix.lstrip(".").lower()
    source_modified_raw = metadata.get("source_modified_at")
    source_modified_at = str(source_modified_raw) if source_modified_raw is not None else ""
    merged_source_meta = {
        "source_origin": source_origin,
        "logical_path": logical_path,
    }
    if parent_metadata:
        merged_source_meta.update(parent_metadata)

    return {
        "title": title,
        "source_type": "documents",
        "source_system": source_system,
        "source_key": document_id,
        "source_collection": source_collection,
        "source_path": source_path,
        "original_path": logical_path,
        "domain": domain,
        "file_type": extension,
        "mime_type": str(metadata.get("mime_type", "application/octet-stream")),
        "document_id": document_id,
        "source_modified_at": source_modified_at,
        "source_size_bytes": int(metadata.get("source_size_bytes", 0) or 0),
        "transformer": transformer_name,
        "transformer_version": transformer_version or "unknown",
        "tags": ["documents", source_system, domain],
        "aliases": aliases or [],
        "source_meta": merged_source_meta,
    }
