from __future__ import annotations

import re

from processing.frontmatter_schema import parse_frontmatter


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")


def has_meaningful_markdown_content(markdown_text: str) -> bool:
    """Prüft, ob Markdown mehr als Frontmatter/Überschriften enthält."""
    _, body = parse_frontmatter(markdown_text)

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _HEADING_RE.match(line):
            continue
        return True
    return False

