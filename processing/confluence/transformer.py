"""Haupttransformer für Confluence-Rohseiten."""

from __future__ import annotations

import html
import logging
import re

from processing.confluence.link_transformer import LinkTransformer
from processing.confluence.macro_transformer import MacroTransformer
from processing.confluence.models import ConfluenceRawPage, ConfluenceTransformedPage, TransformWarning
from processing.confluence.page_properties import (
    build_frontmatter_promoted_properties,
    load_property_promotion_rules,
)
from processing.confluence.table_transformer import TableTransformer
from processing.confluence.writer import ConfluenceTransformWriter
from sources.document import stable_hash
from processing.terminology import TerminologyService


logger = logging.getLogger(__name__)


class ConfluenceTransformer:
    """Transformiert Rohseiten in ingestierbares Markdown."""

    def __init__(self) -> None:
        self.macro_transformer = MacroTransformer()
        self.property_promotion_rules = load_property_promotion_rules()
        self.table_transformer = TableTransformer(self.property_promotion_rules)
        self.link_transformer = LinkTransformer()
        self.terminology_service = TerminologyService()

    def transform(self, page: ConfluenceRawPage) -> ConfluenceTransformedPage:
        warnings: list[TransformWarning] = []

        source_content_hash = stable_hash(
            "|".join([page.title, page.body, page.updated_at or "", ",".join(page.labels)])
        )

        text = page.body
        text, macro_warnings, unsupported = self.macro_transformer.transform(text)
        warnings.extend(macro_warnings)

        page_slug = ConfluenceTransformWriter._slugify(page.title)
        text, extracted_properties, key_value_count, extra_documents = self.table_transformer.transform(
            text,
            page_id=page.page_id,
            page_title=page.title,
            page_slug=page_slug,
            source_url=page.source_url,
            labels=page.labels,
            parent_title=page.parent_title,
            content_hash=source_content_hash,
            warnings=warnings,
        )
        merged_page_properties = self._merge_page_properties(page.page_properties, extracted_properties)
        promoted_properties = build_frontmatter_promoted_properties(merged_page_properties, self.property_promotion_rules)

        if key_value_count:
            logger.debug("Seite %s: %s Key-Value-Tabellen erkannt.", page.page_id, key_value_count)

        text = self.link_transformer.transform(text, source_url=page.source_url)
        text = self._convert_structure(text)
        text = self._cleanup_whitespace(text)

        title_prefix = f"# {page.title}\n\n"
        body = title_prefix + text.strip()
        body += self.link_transformer.render_attachments(page.attachments)

        terminology_result = self.terminology_service.apply_to_text(
            body,
            source_type="confluence",
            source_ref=page.source_ref,
        )

        return ConfluenceTransformedPage(
            page_id=page.page_id,
            space_key=page.space_key,
            title=page.title,
            body_markdown=terminology_result.text,
            source_ref=page.source_ref,
            source_url=page.source_url,
            created_at=page.created_at,
            updated_at=page.updated_at,
            author=page.author,
            labels=page.labels,
            parent_title=page.parent_title,
            ancestors=page.ancestors,
            page_properties=merged_page_properties,
            promoted_properties=promoted_properties,
            attachments=page.attachments,
            transform_warnings=warnings,
            unsupported_macros=unsupported,
            extra_documents=extra_documents,
            content_hash=source_content_hash,
        )

    def _merge_page_properties(self, existing: dict[str, object], extracted: dict[str, str]) -> dict[str, object]:
        """Ergänzt erkannte Seiteneigenschaften ohne vorhandene Werte zu überschreiben."""
        merged: dict[str, object] = dict(existing)
        for key, value in extracted.items():
            if key not in merged:
                merged[key] = value
        return merged

    def _convert_structure(self, text: str) -> str:
        conversions = [
            (r"<h1[^>]*>(.*?)</h1>", r"# \1\n"),
            (r"<h2[^>]*>(.*?)</h2>", r"## \1\n"),
            (r"<h3[^>]*>(.*?)</h3>", r"### \1\n"),
            (r"<h4[^>]*>(.*?)</h4>", r"#### \1\n"),
            (r"<h5[^>]*>(.*?)</h5>", r"##### \1\n"),
            (r"<h6[^>]*>(.*?)</h6>", r"###### \1\n"),
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
            (r"<ol[^>]*>", "\n"),
            (r"</ol>", "\n"),
            (r"<li[^>]*>", "- "),
            (r"</li>", "\n"),
            (r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", r"\n```\n\1\n```\n"),
            (r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n"),
        ]

        output = text
        for pattern, replacement in conversions:
            output = re.sub(pattern, replacement, output, flags=re.DOTALL | re.IGNORECASE)

        output = re.sub(r"<ri:user[^>]*ri:display-name=\"([^\"]+)\"[^>]*/>", r"\1", output)
        output = re.sub(r"<ri:user[^>]*/>", "Benutzer", output)
        output = re.sub(r"<[^>]+>", "", output)
        return html.unescape(output)

    def _cleanup_whitespace(self, text: str) -> str:
        cleaned = re.sub(r"\r\n?", "\n", text)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
