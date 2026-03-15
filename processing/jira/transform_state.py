"""Persistenter Zustand für inkrementelle JIRA-Transformation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JiraTransformStateRecord:
    source_checksum: str
    output_checksum: str
    output_file: str
    updated_at: str


@dataclass(slots=True)
class JiraTransformStateSummary:
    last_run_id: str = ""
    last_mode: str = "incremental"
    last_saved_at: str = ""
    issues_seen: int = 0
    issues_processed: int = 0
    issues_skipped: int = 0
    issues_failed: int = 0
    issues_changed: int = 0


@dataclass(slots=True)
class JiraTransformState:
    issues: dict[str, JiraTransformStateRecord] = field(default_factory=dict)
    summary: JiraTransformStateSummary = field(default_factory=JiraTransformStateSummary)

    @classmethod
    def load(cls, path: Path) -> JiraTransformState:
        target = path.expanduser().resolve()
        if not target.exists():
            return cls()

        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_issues: dict[str, Any] = payload.get("issues", {})
        issues: dict[str, JiraTransformStateRecord] = {}
        for issue_key, record in raw_issues.items():
            issues[issue_key] = JiraTransformStateRecord(
                source_checksum=str(record.get("source_checksum", "")),
                output_checksum=str(record.get("output_checksum", "")),
                output_file=str(record.get("output_file", "")),
                updated_at=str(record.get("updated_at", "")),
            )
        raw_summary: dict[str, Any] = payload.get("summary", {})
        summary = JiraTransformStateSummary(
            last_run_id=str(raw_summary.get("last_run_id", "")),
            last_mode=str(raw_summary.get("last_mode", "incremental")),
            last_saved_at=str(raw_summary.get("last_saved_at", "")),
            issues_seen=int(raw_summary.get("issues_seen", 0) or 0),
            issues_processed=int(raw_summary.get("issues_processed", 0) or 0),
            issues_skipped=int(raw_summary.get("issues_skipped", 0) or 0),
            issues_failed=int(raw_summary.get("issues_failed", 0) or 0),
            issues_changed=int(raw_summary.get("issues_changed", 0) or 0),
        )
        return cls(issues=issues, summary=summary)

    def save(self, path: Path) -> None:
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": asdict(self.summary),
            "issues": {issue_key: asdict(record) for issue_key, record in self.issues.items()},
        }
