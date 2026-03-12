"""Renderer für JIRA-Markdown inkl. Frontmatter."""

from __future__ import annotations

from processing.frontmatter_schema import build_frontmatter, render_frontmatter
from processing.jira.models import JiraTransformedIssue


class JiraMarkdownRenderer:
    def render(self, issue: JiraTransformedIssue) -> str:
        frontmatter = build_frontmatter(
            title=f"{issue.issue_key}: {issue.summary}",
            source_type="jira",
            source_system="jira_export",
            source_key=issue.project_key.lower(),
            source_url=issue.source_url or "",
            original_id=issue.issue_id,
            original_path=issue.source_ref,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            tags=issue.labels,
            authors=[item for item in [issue.reporter, issue.assignee] if item],
            content_hash=issue.content_hash,
            attachments=[a.get("name") for a in issue.attachments if isinstance(a, dict) and a.get("name")],
            source_meta={
                "jira_key": issue.issue_key,
                "issue_type": issue.issue_type or "",
                "status": issue.status or "",
                "priority": issue.priority or "",
                "components": issue.components,
                "fix_versions": issue.fix_versions,
                "transform_warnings": issue.warning_messages(),
            },
        )
        return render_frontmatter(frontmatter, issue.body_markdown)
