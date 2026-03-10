"""Manifest-Modelle für Confluence-Transform-Läufe."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import uuid
from typing import Any


def generate_transform_run_id() -> str:
    """Erzeugt eine Run-ID für einen Transform-Lauf."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"transform-{timestamp}-{uuid.uuid4().hex[:8]}"


@dataclass(slots=True)
class TransformRecord:
    """Statusrecord pro Seite im Lauf."""

    page_id: str
    title: str
    source_ref: str
    output_file: str
    source_checksum: str
    output_checksum: str
    warning_count: int
    status: str


@dataclass(slots=True)
class TransformRunManifest:
    """Zusammenfassung eines Confluence-Transform-Laufs."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    mode: str = "incremental"
    pages_seen: int = 0
    pages_processed: int = 0
    pages_skipped: int = 0
    pages_failed: int = 0
    records: list[TransformRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
