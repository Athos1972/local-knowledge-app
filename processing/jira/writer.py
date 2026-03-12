"""Writer für transformierte JIRA-Issues."""

from __future__ import annotations

from pathlib import Path
import re


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

    @staticmethod
    def _slugify(value: str) -> str:
        lower = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9äöüß\-\s]", "", lower)
        compact = re.sub(r"\s+", "-", normalized)
        return compact.strip("-") or "untitled"
