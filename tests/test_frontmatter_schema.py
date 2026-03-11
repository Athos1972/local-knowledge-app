from __future__ import annotations

import unittest

from processing.frontmatter_schema import (
    build_frontmatter,
    merge_frontmatter,
    parse_frontmatter,
    render_frontmatter,
    validate_frontmatter,
)


class FrontmatterSchemaTests(unittest.TestCase):
    def test_parse_and_render_roundtrip(self) -> None:
        markdown = """---
title: Test Doc
source_type: confluence
source_system: confluence_dc
source_key: confluence-wstw
tags:
  - alpha
  - beta
---

# Content
"""

        frontmatter, body = parse_frontmatter(markdown)

        self.assertEqual("Test Doc", frontmatter["title"])
        self.assertEqual(["alpha", "beta"], frontmatter["tags"])
        self.assertEqual("# Content", body.strip())

        rendered = render_frontmatter(frontmatter, body)
        self.assertTrue(rendered.startswith("---\n"))
        self.assertIn("source_system: confluence_dc", rendered)

    def test_merge_updates_and_source_meta(self) -> None:
        existing = {
            "title": "Alt",
            "source_type": "jira",
            "source_system": "jira_dc",
            "source_key": "jira-prews",
            "source_meta": {"jira_key": "ABC-1"},
        }
        updates = {
            "title": "Neu",
            "source_meta": {"issue_type": "Story"},
            "tags": "one, two",
        }

        merged = merge_frontmatter(existing, updates)

        self.assertEqual("Neu", merged["title"])
        self.assertEqual("ABC-1", merged["source_meta"]["jira_key"])
        self.assertEqual("Story", merged["source_meta"]["issue_type"])
        self.assertEqual(["one", "two"], merged["tags"])

    def test_parse_without_frontmatter_keeps_body(self) -> None:
        markdown = "# Heading\n\nBody"
        frontmatter, body = parse_frontmatter(markdown)

        self.assertEqual({}, frontmatter)
        self.assertEqual(markdown, body)

    def test_validation_reports_missing_required_fields(self) -> None:
        errors = validate_frontmatter({"title": "x"})
        self.assertGreaterEqual(len(errors), 1)

    def test_build_frontmatter_sets_defaults(self) -> None:
        fm = build_frontmatter(
            title="Doc",
            source_type="file",
            source_system="filesystem",
            source_key="local-files",
            tags="a,b",
            source_meta=None,
        )
        self.assertIn("imported_at", fm)
        self.assertEqual(["a", "b"], fm["tags"])


if __name__ == "__main__":
    unittest.main()
