from __future__ import annotations

import re

from sources.document import NormalizedDocument, SourceDocument


class MarkdownNormalizer:
    """Normalisiert Markdown minimal und erzeugt ein NormalizedDocument."""

    _multi_newline_pattern = re.compile(r"\n{3,}")

    @classmethod
    def normalize(cls, source_doc: SourceDocument) -> NormalizedDocument:
        content = source_doc.text.replace("\r\n", "\n").strip()
        content = cls._multi_newline_pattern.sub("\n\n", content)

        metadata = dict(source_doc.metadata)
        metadata["source"] = source_doc.source

        return NormalizedDocument(
            doc_id=source_doc.id,
            title=source_doc.title,
            content=content,
            source_ref=source_doc.source_ref,
            metadata=metadata,
        )
