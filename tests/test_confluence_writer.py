from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from processing.confluence.models import ConfluenceExtraDocument, ConfluenceTransformedPage
from processing.confluence.writer import ConfluenceTransformWriter


class ConfluenceWriterTests(unittest.TestCase):
    def test_write_transformed_page_writes_main_and_extra_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            writer = ConfluenceTransformWriter(Path(tmp))
            main_path = writer.build_output_path("DOC", "42", "Beispielseite")
            page = ConfluenceTransformedPage(
                page_id="42",
                space_key="DOC",
                title="Beispielseite",
                body_markdown="# Beispielseite\n\nInhalt",
                source_ref="dummy",
                extra_documents=[
                    ConfluenceExtraDocument(
                        file_name="42__beispielseite__table_01.md",
                        title="Tabelle 01",
                        doc_type="confluence_table",
                        body_markdown="# Tabelle",
                        metadata={"title": "Tabelle 01", "doc_type": "confluence_table"},
                    )
                ],
            )

            written = writer.write_transformed_page(main_path, "---\ntitle: \"x\"\n---\n\n# Beispielseite", page)

            self.assertEqual(2, len(written))
            self.assertTrue(main_path.exists())
            extra_path = main_path.parent / "42__beispielseite__table_01.md"
            self.assertTrue(extra_path.exists())
            self.assertIn("doc_type", extra_path.read_text(encoding="utf-8"))

    def test_build_output_path_truncates_long_slug(self) -> None:
        writer = ConfluenceTransformWriter(Path("/tmp/out"))

        path = writer.build_output_path("DOC", "157624513", "a" * 400)

        self.assertEqual("157624513__" + ("a" * 120) + ".md", path.name)
        self.assertLess(len(path.name), 255)

    def test_write_transformed_page_removes_previous_artifacts_for_same_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            writer = ConfluenceTransformWriter(Path(tmp))
            space_dir = Path(tmp) / "doc"
            space_dir.mkdir(parents=True, exist_ok=True)
            stale_main = space_dir / "42__alte-seite.md"
            stale_extra = space_dir / "42__alte-seite__table_01.md"
            stale_main.write_text("old", encoding="utf-8")
            stale_extra.write_text("old-extra", encoding="utf-8")

            main_path = writer.build_output_path("DOC", "42", "Neue Seite")
            page = ConfluenceTransformedPage(
                page_id="42",
                space_key="DOC",
                title="Neue Seite",
                body_markdown="# Neue Seite",
                source_ref="dummy",
                extra_documents=[],
            )

            writer.write_transformed_page(main_path, "---\ntitle: \"x\"\n---\n\n# Neue Seite", page)

            self.assertTrue(main_path.exists())
            self.assertFalse(stale_main.exists())
            self.assertFalse(stale_extra.exists())


if __name__ == "__main__":
    unittest.main()
