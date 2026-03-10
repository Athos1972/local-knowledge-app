"""Manifest-Modelle für Confluence-Publish-Läufe."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import uuid
from typing import Any


def generate_publish_run_id() -> str:
    """Erzeugt eine eindeutige Run-ID."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"publish-{timestamp}-{uuid.uuid4().hex[:8]}"


@dataclass(slots=True)
class PublishRecord:
    """Status-Record pro verarbeiteter Input-Datei."""

    input_file: str
    output_file: str
    page_id: str
    title: str
    space_key: str
    source_checksum: str
    output_checksum: str
    status: str
    warning_count: int = 0


@dataclass(slots=True)
class PublishRunManifest:
    """Zusammenfassung eines Publish-Laufs inklusive Dateirecords."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    mode: str = "incremental"
    files_seen: int = 0
    files_published: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    files_unmapped: int = 0
    records: list[PublishRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Manifest als Dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialisiert das Manifest als formatierten JSON-String."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
