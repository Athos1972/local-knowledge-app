from processing.markdown_quality import has_meaningful_markdown_content


def test_only_headings_are_not_meaningful() -> None:
    assert not has_meaningful_markdown_content("# H1\n\n## H2\n")


def test_frontmatter_and_heading_only_are_not_meaningful() -> None:
    markdown = """---
title: Beispiel
---

# Intro
"""
    assert not has_meaningful_markdown_content(markdown)


def test_regular_body_text_is_meaningful() -> None:
    assert has_meaningful_markdown_content("# Titel\n\nDas ist Inhalt.")
