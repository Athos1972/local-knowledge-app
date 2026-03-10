"""Konvertiert Confluence-Links in Markdown-Links."""

from __future__ import annotations

import re
from urllib.parse import urljoin


class LinkTransformer:
    """Wandelt externe und interne Links in Markdown-Syntax."""

    def transform(self, text: str, source_url: str | None = None) -> str:
        transformed = re.sub(
            r"<a\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
            self._replace_anchor,
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        transformed = re.sub(
            r"<ac:link>\s*<ri:page[^>]*ri:content-title=\"([^\"]+)\"[^>]*/>\s*<ac:plain-text-link-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-link-body>\s*</ac:link>",
            lambda m: f"[{m.group(2).strip() or m.group(1).strip()}]({self._safe_internal_url(m.group(1), source_url)})",
            transformed,
            flags=re.DOTALL,
        )
        transformed = re.sub(
            r"<ac:link>\s*<ri:page[^>]*ri:content-title=\"([^\"]+)\"[^>]*/>\s*</ac:link>",
            lambda m: f"[{m.group(1).strip()}]({self._safe_internal_url(m.group(1), source_url)})",
            transformed,
            flags=re.DOTALL,
        )
        return transformed

    def render_attachments(self, attachments: list[dict[str, object]]) -> str:
        if not attachments:
            return ""
        lines = ["", "## Anhänge", ""]
        for item in attachments:
            name = str(item.get("name") or item.get("title") or "Anhang")
            url = str(item.get("url") or item.get("downloadUrl") or "").strip()
            if url:
                lines.append(f"- [{name}]({url})")
            else:
                lines.append(f"- {name}")
        lines.append("")
        return "\n".join(lines)

    def _replace_anchor(self, match: re.Match[str]) -> str:
        href = match.group(1).strip()
        raw_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        text = raw_text or href
        return f"[{text}]({href})"

    @staticmethod
    def _safe_internal_url(page_title: str, source_url: str | None) -> str:
        slug = page_title.strip().lower().replace(" ", "-")
        if source_url:
            return urljoin(source_url, f"/wiki/{slug}")
        return f"confluence://page/{slug}"
