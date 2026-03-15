"""Renderer für JIRA-Markdown inkl. Frontmatter."""

from __future__ import annotations

from processing.documents.reference_resolver import resolve_attachment_document_ids
from processing.frontmatter_schema import build_frontmatter, render_frontmatter
from processing.jira.models import JiraTransformedIssue


class JiraMarkdownRenderer:
    def render(self, issue: JiraTransformedIssue) -> str:
        image_refs = [ref for ref in issue.image_analysis_refs if isinstance(ref, dict)]
        attachment_document_ids = resolve_attachment_document_ids(
            [
                str(item.get("local_path"))
                for item in issue.attachments
                if isinstance(item, dict) and item.get("local_path")
            ]
        )
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
            image_analysis_status="complete" if image_refs else "not_applicable",
            image_attachment_count=len(image_refs),
            image_analysis=image_refs,
            source_meta={
                "jira_key": issue.issue_key,
                "issue_type": issue.issue_type or "",
                "status": issue.status or "",
                "priority": issue.priority or "",
                "components": issue.components,
                "fix_versions": issue.fix_versions,
                "attachment_document_ids": attachment_document_ids,
                "transform_warnings": issue.warning_messages(),
                "image_analysis_refs": image_refs,
            },
        )
        return render_frontmatter(frontmatter, issue.body_markdown)
