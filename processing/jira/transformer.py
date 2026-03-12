"""Transformer für JIRA-Exportdaten."""

from __future__ import annotations

import html
import re

from processing.confluence.link_transformer import LinkTransformer
from processing.jira.models import JiraRawIssue, JiraTransformedIssue
from sources.document import stable_hash


class JiraTransformer:
    """Transformiert rohe JIRA-Issues in ingestierbares Markdown."""

    def __init__(self) -> None:
        self._link_transformer = LinkTransformer()

    def transform(self, issue: JiraRawIssue) -> JiraTransformedIssue:
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

        body = "\n".join(lines).rstrip() + self._link_transformer.render_attachments(issue.attachments)
        content_hash = stable_hash(
            "|".join([issue.issue_key, issue.summary, issue.description, issue.updated_at or "", ",".join(issue.labels)])
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
            content_hash=content_hash,
        )

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
