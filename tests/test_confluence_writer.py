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


if __name__ == "__main__":
    unittest.main()
