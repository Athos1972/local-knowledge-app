"""Renderer für finalen Markdown-Output mit YAML-Frontmatter."""

from __future__ import annotations

from processing.confluence.models import ConfluenceTransformedPage
from processing.documents.reference_resolver import resolve_attachment_document_ids
from processing.frontmatter_schema import build_frontmatter, render_frontmatter


class MarkdownRenderer:
    """Rendert transformierte Seiten in ingestierbares Markdown."""

    def render(self, page: ConfluenceTransformedPage) -> str:
        image_refs = [ref for ref in page.image_analysis_refs if isinstance(ref, dict)]
        attachment_document_ids = resolve_attachment_document_ids(
            [
                str(item.get("local_path"))
                for item in page.attachments
                if isinstance(item, dict) and item.get("local_path")
            ]
        )
        frontmatter = build_frontmatter(
            title=page.title,
            source_type="confluence",
            source_system="confluence_export",
            source_key=page.space_key.lower(),
            source_url=page.source_url or "",
            original_id=page.page_id,
            original_path=page.source_ref,
            created_at=page.created_at,
            updated_at=page.updated_at,
            tags=page.labels,
            authors=[page.author] if page.author else [],
            content_hash=page.content_hash,
            attachments=[a.get("name") for a in page.attachments if isinstance(a, dict) and a.get("name")],
            image_analysis_status="complete" if image_refs else "not_applicable",
            image_attachment_count=len(image_refs),
            image_analysis=image_refs,
            parent_title=page.parent_title or "",
            ancestors=page.ancestors,
            page_properties=page.page_properties,
            unsupported_macros=page.unsupported_macros,
            doc_type="confluence_page",
            **page.promoted_properties,
            source_meta={
                "space_key": page.space_key,
                "page_id": page.page_id,
                "attachment_document_ids": attachment_document_ids,
                "transform_warnings": page.warning_messages(),
                "image_analysis_refs": image_refs,
            },
        )
        return render_frontmatter(frontmatter, page.body_markdown)
