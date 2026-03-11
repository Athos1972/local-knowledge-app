from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from processing.scrape2md_importer import (
    BehaviorConfig,
    FrontmatterConfig,
    ImportConfig,
    SourceConfig,
    TargetConfig,
    run_import,
)


class Scrape2mdImporterTests(unittest.TestCase):
    def test_import_writes_markdown_with_frontmatter_and_path_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            export_root = root / "exports" / "docs.example.com"
            pages_dir = export_root / "pages" / "guide"
            pages_dir.mkdir(parents=True, exist_ok=True)

            markdown_file = pages_dir / "intro.md"
            markdown_file.write_text("# Intro\n\nContent", encoding="utf-8")

            manifest = {
                "domain": "docs.example.com",
                "crawl_timestamp": "2026-01-01T10:00:00Z",
                "pages": [
                    {
                        "path": "guide/intro.md",
                        "title": "Getting Started",
                        "url": "https://docs.example.com/guide/intro",
                        "content_type": "documentation",
                    }
                ],
            }
            (export_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            knowledge_root = root / "knowledge"
            config = ImportConfig(
                source=SourceConfig(export_root=export_root, source_key="docs-example-com"),
                target=TargetConfig(
                    knowledge_root=knowledge_root,
                    target_subpath=Path("domains/external/docs-example-com"),
                ),
                frontmatter=FrontmatterConfig(enabled=True, title_from_first_heading=True),
                behavior=BehaviorConfig(copy_assets=False, overwrite=True, dry_run=False),
            )

            stats = run_import(config)

            self.assertEqual(1, stats.imported)
            target_file = knowledge_root / "domains/external/docs-example-com/guide/intro.md"
            self.assertTrue(target_file.exists())

            written = target_file.read_text(encoding="utf-8")
            self.assertIn('title: Getting Started', written)
            self.assertIn('source_key: docs-example-com', written)
            self.assertIn('source_system: website', written)
            self.assertIn('source_meta:', written)
            self.assertIn('source_domain: docs.example.com', written)
            self.assertIn('status: raw', written)

    def test_overwrite_disabled_skips_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            export_root = root / "exports" / "docs.example.com"
            pages_dir = export_root / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)

            source_file = pages_dir / "index.md"
            source_file.write_text("# New", encoding="utf-8")
            (export_root / "manifest.json").write_text("{}", encoding="utf-8")

            knowledge_root = root / "knowledge"
            target_file = knowledge_root / "domains/external/docs-example-com/index.md"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("# Existing", encoding="utf-8")

            config = ImportConfig(
                source=SourceConfig(export_root=export_root, source_key="docs-example-com"),
                target=TargetConfig(
                    knowledge_root=knowledge_root,
                    target_subpath=Path("domains/external/docs-example-com"),
                ),
                frontmatter=FrontmatterConfig(enabled=False, title_from_first_heading=True),
                behavior=BehaviorConfig(copy_assets=False, overwrite=False, dry_run=False),
            )

            stats = run_import(config)

            self.assertEqual(1, stats.skipped)
            self.assertEqual("# Existing", target_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
