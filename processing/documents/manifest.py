"""Manifest models for local document transform runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import uuid
from typing import Any


def generate_transform_run_id() -> str:
    """Build a run id for document transform executions."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"documents-transform-{timestamp}-{uuid.uuid4().hex[:8]}"


@dataclass(slots=True)
class DocumentTransformRecord:
    """Per-document status record within one run."""

    document_id: str
    source_path: str
    domain: str
    staging_output_file: str
    publish_output_file: str
    source_checksum: str
    output_checksum: str
    warning_count: int
    status: str


@dataclass(slots=True)
class DocumentTransformRunManifest:
    """Summary and detail records for one documents transform run."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    run_duration: float = 0.0
    run_duration_human: str = "0s"
    mode: str = "incremental"
    documents_seen: int = 0
    documents_processed: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    records: list[DocumentTransformRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
