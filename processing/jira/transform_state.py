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
class JiraTransformState:
    issues: dict[str, JiraTransformStateRecord] = field(default_factory=dict)

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
        return cls(issues=issues)

    def save(self, path: Path) -> None:
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {"issues": {issue_key: asdict(record) for issue_key, record in self.issues.items()}}
