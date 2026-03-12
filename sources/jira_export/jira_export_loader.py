"""Loader für lokal exportierte JIRA-Issues."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from common.logging_setup import AppLogger
from processing.jira.models import JiraRawIssue

logger = AppLogger.get_logger()


class JiraExportLoader:
    """Lädt JIRA-Issues robust aus einer lokalen Exportstruktur."""

    def __init__(self, input_root: Path):
        self.input_root = input_root.expanduser().resolve()

    def load_issues(self, project_filter: str | None = None) -> Iterable[JiraRawIssue]:
        if not self.input_root.exists():
            logger.warning("JIRA input root existiert nicht: %s", self.input_root)
            return

        for issue_dir, metadata_path in self._iter_issue_roots():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                issue = self._build_raw_issue(payload, metadata_path, issue_dir)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Issue konnte nicht geladen werden: %s (%s)", metadata_path, exc)
                continue

            if project_filter and issue.project_key.lower() != project_filter.lower():
                continue
            yield issue

    def _iter_issue_roots(self) -> Iterable[tuple[Path, Path]]:
        for metadata_path in self.input_root.rglob("metadata.json"):
            issue_dir = metadata_path.parent
            parent_name = issue_dir.parent.name.lower()
            if parent_name not in {"issues", "by-key", "by-id"}:
                continue
            yield issue_dir, metadata_path

    def _build_raw_issue(self, payload: dict[str, Any], source_file: Path, issue_dir: Path) -> JiraRawIssue:
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        key = str(payload.get("key") or payload.get("issue_key") or issue_dir.name).strip()
        issue_id = str(payload.get("id") or payload.get("issue_id") or key).strip()
        project_key = str(
            self._pick(payload, ["project_key", "project.key", "fields.project.key"], default="")
            or key.split("-", 1)[0]
            or "unknown"
        ).strip()
        summary = str(self._pick(payload, ["summary", "title", "fields.summary"], default="Ohne Titel")).strip()

        description = self._extract_description(payload, fields, issue_dir)
        attachments = self._normalize_attachments(self._pick(payload, ["attachments", "fields.attachment"], default=[]))
        attachment_paths = self._resolve_attachment_paths(attachments, issue_dir)

        issue_type = self._optional_str(self._pick(payload, ["issue_type", "fields.issuetype.name"]))
        status = self._optional_str(self._pick(payload, ["status", "fields.status.name"]))
        priority = self._optional_str(self._pick(payload, ["priority", "fields.priority.name"]))

        labels = self._normalize_labels(self._pick(payload, ["labels", "fields.labels"], default=[]))
        components = self._normalize_named_list(self._pick(payload, ["components", "fields.components"], default=[]))
        fix_versions = self._normalize_named_list(self._pick(payload, ["fix_versions", "fields.fixVersions"], default=[]))

        assignee = self._optional_str(self._pick(payload, ["assignee", "fields.assignee.displayName", "fields.assignee.name"]))
        reporter = self._optional_str(self._pick(payload, ["reporter", "fields.reporter.displayName", "fields.reporter.name"]))

        source_url = self._optional_str(self._pick(payload, ["source_url", "url", "self", "browse_url"]))

        return JiraRawIssue(
            issue_id=issue_id or key,
            issue_key=key or issue_id,
            project_key=project_key or "unknown",
            summary=summary or "Ohne Titel",
            description=description,
            source_ref=str(source_file),
            source_url=source_url,
            created_at=self._optional_str(self._pick(payload, ["created_at", "created", "fields.created"])),
            updated_at=self._optional_str(self._pick(payload, ["updated_at", "updated", "fields.updated"])),
            issue_type=issue_type,
            status=status,
            priority=priority,
            assignee=assignee,
            reporter=reporter,
            labels=labels,
            components=components,
            fix_versions=fix_versions,
            attachments=attachments,
            attachment_paths=attachment_paths,
            raw_metadata=payload,
        )

    def _extract_description(self, payload: dict[str, Any], fields: dict[str, Any], issue_dir: Path) -> str:
        for filename in ("description.md", "description.txt", "description.html"):
            candidate = issue_dir / filename
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")

        value = self._pick(payload, ["description", "fields.description", "renderedFields.description"], default="")
        if isinstance(value, str):
            return value
        if isinstance(fields.get("description"), dict):
            return json.dumps(fields["description"], ensure_ascii=False)
        return ""

    def _pick(self, payload: dict[str, Any], paths: list[str], default: Any = None) -> Any:
        for path in paths:
            current: Any = payload
            success = True
            for part in path.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    success = False
                    break
            if success:
                return current
        return default

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _normalize_labels(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    @staticmethod
    def _normalize_named_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    result.append(name.strip())
        return result


    def _resolve_attachment_paths(self, attachments: list[dict[str, Any]], issue_dir: Path) -> list[str]:
        resolved: list[str] = []
        for item in attachments:
            candidates: list[Path] = []

            for key in ("local_path", "localPath", "path", "file_path", "filePath", "filepath", "export_path", "absolute_path"):
                raw = item.get(key)
                if isinstance(raw, str) and raw.strip():
                    candidates.append(Path(raw.strip()).expanduser())

            file_name = str(item.get("name") or item.get("filename") or item.get("title") or "").strip()
            if file_name:
                candidates.extend(
                    [
                        issue_dir / file_name,
                        issue_dir / "attachments" / file_name,
                        issue_dir / "attachment" / file_name,
                        issue_dir / "files" / file_name,
                        issue_dir.parent / "attachments" / file_name,
                    ]
                )

            found: Path | None = None
            for candidate in candidates:
                absolute = candidate if candidate.is_absolute() else (issue_dir / candidate).resolve()
                if absolute.exists() and absolute.is_file():
                    found = absolute
                    break

            if found is None:
                continue

            normalized = str(found.resolve())
            item.setdefault("local_path", normalized)
            if normalized not in resolved:
                resolved.append(normalized)
        return resolved

    @staticmethod
    def _normalize_attachments(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        result: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str) and item.strip():
                result.append({"name": item.strip()})
        return result
