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

        for issue_dir, source_path in self._iter_issue_sources():
            try:
                payload = json.loads(source_path.read_text(encoding="utf-8"))
                issue = self._build_raw_issue(payload, source_path, issue_dir)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Issue konnte nicht geladen werden: %s (%s)", source_path, exc)
                continue

            if project_filter and issue.project_key.lower() != project_filter.lower():
                continue
            yield issue

    def _iter_issue_sources(self) -> Iterable[tuple[Path, Path]]:
        candidates: list[tuple[int, Path, Path]] = []

        for content_path in self.input_root.rglob("content.storage.json"):
            issue_dir = content_path.parent
            if not self._looks_like_issue_dir(issue_dir):
                logger.debug("Ignoriere content.storage.json außerhalb Issue-Layout: %s", content_path)
                continue
            candidates.append((0, issue_dir, content_path))

        for metadata_path in self.input_root.rglob("metadata.json"):
            issue_dir = metadata_path.parent
            if not self._looks_like_issue_dir(issue_dir):
                logger.debug("Ignoriere metadata.json außerhalb Issue-Layout: %s", metadata_path)
                continue
            candidates.append((1, issue_dir, metadata_path))

        seen_issue_dirs: set[Path] = set()
        for _priority, issue_dir, source_path in sorted(candidates, key=lambda item: (item[0], str(item[2]))):
            normalized_issue_dir = issue_dir.resolve()
            if normalized_issue_dir in seen_issue_dirs:
                logger.debug("Mehrfache Quelle für Issue-Verzeichnis ignoriert: %s", source_path)
                continue

            seen_issue_dirs.add(normalized_issue_dir)
            logger.debug("Issue-Quelle erkannt: %s", source_path)
            yield issue_dir, source_path

    @staticmethod
    def _looks_like_issue_dir(issue_dir: Path) -> bool:
        if issue_dir.name.startswith("."):
            return False
        parent_name = issue_dir.parent.name.lower()
        return parent_name in {"issues", "by-key", "by-id"}

    def _build_raw_issue(self, payload: dict[str, Any], source_file: Path, issue_dir: Path) -> JiraRawIssue:
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        key = str(self._pick(payload, ["key", "issue_key", "issue.key", "issueKey"], default="") or "").strip()
        if not key and issue_dir.parent.name.lower() == "by-key":
            key = issue_dir.name

        issue_id = str(self._pick(payload, ["id", "issue_id", "issue.id", "issueId"], default="") or "").strip()
        if not issue_id and issue_dir.parent.name.lower() == "by-id":
            issue_id = issue_dir.name

        if not key and issue_id:
            key = issue_id

        path_project_key = self._project_key_from_path(issue_dir)
        fallback_project_key = key.split("-", 1)[0] if "-" in key else ""
        project_key = str(
            self._pick(payload, ["project_key", "project.key", "fields.project.key"], default="")
            or path_project_key
            or fallback_project_key
            or "unknown"
        ).strip()
        summary = str(self._pick(payload, ["summary", "title", "fields.summary", "issue.summary"], default="Ohne Titel")).strip()

        description = self._extract_description(payload, fields, issue_dir)
        attachments = self._normalize_attachments(self._pick(payload, ["attachments", "fields.attachment"], default=[]))
        attachments = self._merge_attachments_from_export(issue_dir, key, attachments)
        attachment_paths = self._resolve_attachment_paths(attachments, issue_dir, key)

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

        value = self._pick(
            payload,
            [
                "description",
                "fields.description",
                "renderedFields.description",
                "content",
                "storage",
                "body.storage.value",
                "issue.content",
                "issue.description",
            ],
            default="",
        )
        if isinstance(value, str):
            return value
        if isinstance(fields.get("description"), dict):
            return json.dumps(fields["description"], ensure_ascii=False)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return ""

    @staticmethod
    def _project_key_from_path(issue_dir: Path) -> str:
        parts = issue_dir.parts
        for idx, part in enumerate(parts):
            if part.lower() != "projects" or idx + 1 >= len(parts):
                continue
            candidate = parts[idx + 1].strip()
            if candidate and candidate.lower() not in {"issues", "by-id", "by-key", "attachments"}:
                return candidate
        return ""

    def _merge_attachments_from_export(self, issue_dir: Path, issue_key: str, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not issue_key:
            return attachments

        projects_root = self._find_projects_root(issue_dir)
        if projects_root is None:
            return attachments

        attachment_dir = projects_root / "attachments" / issue_key
        if not attachment_dir.exists() or not attachment_dir.is_dir():
            return attachments

        existing_by_name: dict[str, dict[str, Any]] = {}
        for item in attachments:
            name = str(item.get("name") or item.get("filename") or item.get("title") or "").strip()
            if name:
                existing_by_name[name] = item

        for path in sorted(attachment_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                logger.debug("Ignoriere Nicht-Datei in Attachment-Ordner: %s", path)
                continue
            if path.name in existing_by_name:
                existing_by_name[path.name].setdefault("local_path", str(path.resolve()))
                continue
            attachments.append({"name": path.name, "local_path": str(path.resolve())})

        return attachments

    @staticmethod
    def _find_projects_root(issue_dir: Path) -> Path | None:
        for parent in [issue_dir, *issue_dir.parents]:
            if parent.name.lower() == "projects":
                return parent
        return None

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


    def _resolve_attachment_paths(self, attachments: list[dict[str, Any]], issue_dir: Path, issue_key: str) -> list[str]:
        resolved: list[str] = []
        projects_root = self._find_projects_root(issue_dir)
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
                if projects_root is not None and issue_key:
                    candidates.append(projects_root / "attachments" / issue_key / file_name)

            found: Path | None = None
            for candidate in candidates:
                absolute = candidate if candidate.is_absolute() else (issue_dir / candidate).resolve()
                if absolute.exists() and absolute.is_file():
                    found = absolute
                    break

            if found is None:
                logger.debug("Attachment nicht gefunden: issue_dir=%s datei=%s", issue_dir, file_name or "<unknown>")
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
