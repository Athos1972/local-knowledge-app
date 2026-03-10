from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def stable_hash(value: str) -> str:
    """Return a stable SHA-256 hash for a string value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_filesystem_doc_id(root: Path, file_path: Path) -> str:
    """Build a deterministic doc id from a file path relative to the loader root."""
    relative = file_path.resolve().relative_to(root.resolve())
    normalized = relative.as_posix().lower()
    return stable_hash(normalized)


@dataclass(slots=True)
class SourceInfo:
    source_type: str
    source_name: str
    source_ref: str
    original_uri: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(slots=True)
class SourceDocument:
    doc_id: str
    title: str
    content: str
    content_type: str
    source: SourceInfo
    created_at: str | None = None
    updated_at: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(slots=True)
class NormalizedDocument:
    doc_id: str
    title: str
    body: str
    doc_type: str
    mime_type: str
    source: SourceInfo
    created_at: str | None = None
    updated_at: str | None = None
    language: str | None = None
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    normalized_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(slots=True)
class ChunkDocument:
    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    title: str
    doc_type: str
    source_type: str
    source_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
