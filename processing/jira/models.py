"""Datenmodelle für den JIRA-Transform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from processing.confluence.models import TransformWarning


@dataclass(slots=True)
class JiraRawIssue:
    issue_id: str
    issue_key: str
    project_key: str
    summary: str
    description: str
    source_ref: str
    source_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    fix_versions: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    attachment_paths: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JiraTransformedIssue:
    issue_id: str
    issue_key: str
    project_key: str
    summary: str
    body_markdown: str
    source_ref: str
    source_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    fix_versions: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    transform_warnings: list[TransformWarning] = field(default_factory=list)
    content_hash: str = ""

    def warning_messages(self) -> list[str]:
        return [warning.message for warning in self.transform_warnings]
