"""Manifest-Modelle für JIRA-Transform-Läufe."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import uuid
from typing import Any


def generate_transform_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"jira-transform-{timestamp}-{uuid.uuid4().hex[:8]}"


@dataclass(slots=True)
class JiraTransformRecord:
    issue_key: str
    title: str
    source_ref: str
    output_file: str
    source_checksum: str
    output_checksum: str
    warning_count: int
    status: str


@dataclass(slots=True)
class JiraTransformRunManifest:
    run_id: str
    started_at: str
    finished_at: str | None = None
    run_duration: float = 0.0
    run_duration_human: str = "0s"
    mode: str = "incremental"
    issues_seen: int = 0
    issues_processed: int = 0
    issues_skipped: int = 0
    issues_failed: int = 0
    issues_changed: int = 0
    records: list[JiraTransformRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
