"""Writer für transformierte JIRA-Issues."""

from __future__ import annotations

from pathlib import Path
import re

from processing.jira.models import JiraTransformedIssue


class JiraTransformWriter:
    def __init__(self, output_root: Path):
        self.output_root = output_root.expanduser().resolve()

    def build_output_path(self, project_key: str, issue_key: str, summary: str) -> Path:
        slug = self._slugify(summary)
        file_name = f"{issue_key}__{slug}.md"
        return self.output_root / project_key.lower() / file_name

    def write_markdown(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_transformed_issue(self, issue_path: Path, markdown: str, issue: JiraTransformedIssue) -> list[Path]:
        self._remove_previous_artifacts(issue_path, issue.issue_key)
        self.write_markdown(issue_path, markdown)
        written_paths: list[Path] = [issue_path]
        for artifact in issue.derived_artifacts:
            artifact_path = issue_path.parent / artifact.file_name
            if artifact.media_type.startswith("text/") or artifact.media_type == "application/json":
                artifact_path.write_text(artifact.content, encoding="utf-8")
            else:
                artifact_path.write_bytes(artifact.content.encode("utf-8"))
            written_paths.append(artifact_path)
        return written_paths

    @staticmethod
    def _slugify(value: str) -> str:
        lower = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9äöüß\-\s]", "", lower)
        compact = re.sub(r"\s+", "-", normalized)
        return compact.strip("-") or "untitled"

    @staticmethod
    def _remove_previous_artifacts(issue_path: Path, issue_key: str) -> None:
        for pattern in (f"{issue_key}__*.md", f"{issue_key}__*.json"):
            for candidate in issue_path.parent.glob(pattern):
                if candidate != issue_path and candidate.is_file():
                    candidate.unlink()
