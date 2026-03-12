"""Transformer für JIRA-Exportdaten."""

from __future__ import annotations

import html
from pathlib import Path
import re

from processing.confluence.link_transformer import LinkTransformer
from processing.confluence.models import TransformWarning
from processing.jira.models import JiraRawIssue, JiraTransformedIssue
from sources.document import stable_hash
from transformers.router import TransformRouter


class JiraTransformer:
    """Transformiert rohe JIRA-Issues in ingestierbares Markdown."""

    def __init__(self) -> None:
        self._link_transformer = LinkTransformer()
        self._transform_router = TransformRouter()

    def transform(self, issue: JiraRawIssue) -> JiraTransformedIssue:
        warnings: list[TransformWarning] = []

        text = issue.description or ""
        text = self._link_transformer.transform(text, source_url=issue.source_url)
        text = self._convert_structure(text)
        text = self._cleanup_whitespace(text)

        lines = [f"# {issue.issue_key}: {issue.summary}", ""]
        if issue.status:
            lines.append(f"- Status: {issue.status}")
        if issue.issue_type:
            lines.append(f"- Typ: {issue.issue_type}")
        if issue.priority:
            lines.append(f"- Priorität: {issue.priority}")
        if issue.assignee:
            lines.append(f"- Assignee: {issue.assignee}")
        if issue.reporter:
            lines.append(f"- Reporter: {issue.reporter}")
        if len(lines) > 2:
            lines.extend(["", "## Beschreibung", ""])
        lines.append(text or "_Keine Beschreibung im Export gefunden._")

        attachment_sections = self._render_attachment_content(issue, warnings)
        if attachment_sections:
            lines.extend(["", "## Anhang-Inhalte (extrahiert)", "", *attachment_sections])

        body = "\n".join(lines).rstrip() + self._link_transformer.render_attachments(issue.attachments)

        attachment_signature = ",".join(sorted(f"{a.get('name','')}|{a.get('local_path','')}" for a in issue.attachments if isinstance(a, dict)))
        content_hash = stable_hash(
            "|".join(
                [
                    issue.issue_key,
                    issue.summary,
                    issue.description,
                    issue.updated_at or "",
                    ",".join(issue.labels),
                    attachment_signature,
                ]
            )
        )

        return JiraTransformedIssue(
            issue_id=issue.issue_id,
            issue_key=issue.issue_key,
            project_key=issue.project_key,
            summary=issue.summary,
            body_markdown=body,
            source_ref=issue.source_ref,
            source_url=issue.source_url,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            issue_type=issue.issue_type,
            status=issue.status,
            priority=issue.priority,
            assignee=issue.assignee,
            reporter=issue.reporter,
            labels=issue.labels,
            components=issue.components,
            fix_versions=issue.fix_versions,
            attachments=issue.attachments,
            transform_warnings=warnings,
            content_hash=content_hash,
        )

    def _render_attachment_content(self, issue: JiraRawIssue, warnings: list[TransformWarning]) -> list[str]:
        sections: list[str] = []
        indexed = {Path(path).name: path for path in issue.attachment_paths}

        for attachment in issue.attachments:
            if not isinstance(attachment, dict):
                continue

            name = str(attachment.get("name") or attachment.get("filename") or attachment.get("title") or "Anhang")
            local_path_raw = attachment.get("local_path")
            if isinstance(local_path_raw, str) and local_path_raw.strip():
                path = Path(local_path_raw.strip()).expanduser()
            elif name in indexed:
                path = Path(indexed[name])
                attachment.setdefault("local_path", str(path))
            else:
                warnings.append(
                    TransformWarning(
                        code="attachment_missing_local_path",
                        message=f"Anhang '{name}' hat keinen auflösbaren lokalen Pfad.",
                        context=name,
                    )
                )
                continue

            if not path.exists() or not path.is_file():
                warnings.append(
                    TransformWarning(
                        code="attachment_file_not_found",
                        message=f"Anhang-Datei nicht gefunden: {path}",
                        context=name,
                    )
                )
                continue

            transformer = self._transform_router.resolve(path)
            if transformer is None:
                warnings.append(
                    TransformWarning(
                        code="attachment_unsupported_extension",
                        message=f"Anhang '{name}' hat nicht unterstützte Endung '{path.suffix.lower()}'.",
                        context=name,
                    )
                )
                continue

            result = transformer.transform(path)
            if not result.success:
                warnings.append(
                    TransformWarning(
                        code="attachment_transform_failed",
                        message=f"Anhang '{name}' konnte nicht transformiert werden: {result.error or 'unbekannter Fehler'}",
                        context=name,
                    )
                )
                continue

            markdown = result.markdown.strip()
            if not markdown:
                warnings.append(
                    TransformWarning(
                        code="attachment_empty_markdown",
                        message=f"Anhang '{name}' lieferte leeres Markdown.",
                        context=name,
                    )
                )
                continue

            for warn in result.warnings:
                warnings.append(
                    TransformWarning(
                        code="attachment_transform_warning",
                        message=f"Anhang '{name}': {warn}",
                        context=name,
                    )
                )

            sections.extend([f"### {name}", "", markdown, ""])

        return sections

    def _convert_structure(self, text: str) -> str:
        conversions = [
            (r"<h1[^>]*>(.*?)</h1>", r"# \1\n"),
            (r"<h2[^>]*>(.*?)</h2>", r"## \1\n"),
            (r"<h3[^>]*>(.*?)</h3>", r"### \1\n"),
            (r"<strong[^>]*>(.*?)</strong>", r"**\1**"),
            (r"<b[^>]*>(.*?)</b>", r"**\1**"),
            (r"<em[^>]*>(.*?)</em>", r"*\1*"),
            (r"<i[^>]*>(.*?)</i>", r"*\1*"),
            (r"<code[^>]*>(.*?)</code>", r"`\1`"),
            (r"<br\s*/?>", "\n"),
            (r"</p>", "\n\n"),
            (r"<p[^>]*>", ""),
            (r"<ul[^>]*>", "\n"),
            (r"</ul>", "\n"),
            (r"<li[^>]*>", "- "),
            (r"</li>", "\n"),
        ]

        output = text
        for pattern, replacement in conversions:
            output = re.sub(pattern, replacement, output, flags=re.DOTALL | re.IGNORECASE)

        output = re.sub(r"<[^>]+>", "", output)
        return html.unescape(output)

    def _cleanup_whitespace(self, text: str) -> str:
        cleaned = re.sub(r"\r\n?", "\n", text)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
