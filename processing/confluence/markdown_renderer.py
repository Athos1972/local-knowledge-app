"""Renderer für finalen Markdown-Output mit YAML-Frontmatter."""

from __future__ import annotations

import json

from processing.confluence.models import ConfluenceTransformedPage


class MarkdownRenderer:
    """Rendert transformierte Seiten in ingestierbares Markdown."""

    def render(self, page: ConfluenceTransformedPage) -> str:
        frontmatter = self._render_frontmatter(page)
        body = page.body_markdown.strip()
        return f"---\n{frontmatter}\n---\n\n{body}\n"

    def _render_frontmatter(self, page: ConfluenceTransformedPage) -> str:
        payload = {
            "title": page.title,
            "source_type": "confluence",
            "space_key": page.space_key,
            "page_id": page.page_id,
            "source_url": page.source_url or "",
            "created_at": page.created_at or "",
            "updated_at": page.updated_at or "",
            "author": page.author or "",
            "labels": page.labels,
            "doc_type": "confluence_page",
            "tags": page.labels,
            "transform_warnings": page.warning_messages(),
            "unsupported_macros": page.unsupported_macros,
            "parent_title": page.parent_title or "",
            "ancestors": page.ancestors,
            "page_properties": page.page_properties,
            "content_hash": page.content_hash,
        }

        lines: list[str] = []
        for key, value in payload.items():
            lines.append(f"{key}: {self._yaml_value(value)}")
        return "\n".join(lines)

    def _yaml_value(self, value: object) -> str:
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)
