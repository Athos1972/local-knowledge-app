from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sources.confluence_export.confluence_export_loader import ConfluenceExportLoader


class ConfluenceExportLoaderTests(unittest.TestCase):
    def test_loads_pages_from_instance_space_by_id_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports" / "confluence"
            page_dir = root / "inst-a" / "spaces" / "ABC" / "by-id" / "12345"
            page_dir.mkdir(parents=True)

            (page_dir / "metadata.json").write_text(
                '{"id": "12345", "title": "My Page", "space": {"key": "ABC"}}',
                encoding="utf-8",
            )
            (page_dir / "content.storage.xml").write_text("<p>Hello from xml</p>", encoding="utf-8")

            pages = list(ConfluenceExportLoader(root).load_pages())
            self.assertEqual(1, len(pages))
            self.assertEqual("12345", pages[0].page_id)
            self.assertEqual("ABC", pages[0].space_key)
            self.assertEqual("My Page", pages[0].title)
            self.assertEqual("<p>Hello from xml</p>", pages[0].body)

    def test_filters_out_non_by_id_metadata_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports" / "confluence"
            invalid_dir = root / "inst-a" / "spaces" / "ABC" / "pages" / "12345"
            invalid_dir.mkdir(parents=True)
            (invalid_dir / "metadata.json").write_text('{"id":"12345"}', encoding="utf-8")

            pages = list(ConfluenceExportLoader(root).load_pages())
            self.assertEqual([], pages)

    def test_loads_pages_from_sharded_by_id_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports" / "confluence"
            page_dir = root / "inst-a" / "spaces" / "ABC" / "by-id" / "12" / "12345"
            page_dir.mkdir(parents=True)

            (page_dir / "metadata.json").write_text(
                '{"id": "12345", "title": "Sharded Page", "space": {"key": "ABC"}}',
                encoding="utf-8",
            )
            (page_dir / "content.storage.xml").write_text("<p>Hello from shard</p>", encoding="utf-8")

            pages = list(ConfluenceExportLoader(root).load_pages())
            self.assertEqual(1, len(pages))
            self.assertEqual("12345", pages[0].page_id)
            self.assertEqual("ABC", pages[0].space_key)
            self.assertEqual("Sharded Page", pages[0].title)
            self.assertEqual("<p>Hello from shard</p>", pages[0].body)


if __name__ == "__main__":
    unittest.main()
