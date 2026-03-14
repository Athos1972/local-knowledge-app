from __future__ import annotations

import unittest

from processing.confluence.models import ConfluenceRawPage
from processing.confluence.transformer import ConfluenceTransformer


class ConfluenceTableTransformerTests(unittest.TestCase):
    def test_key_value_table_moves_configured_keys_to_frontmatter_and_hides_them_in_text(self) -> None:
        page = ConfluenceRawPage(
            page_id="1",
            space_key="DOC",
            title="Eigenschaften",
            body=(
                "<p>Einleitung</p>"
                "<table>"
                "<tr><td>Status</td><td>In Arbeit</td></tr>"
                "<tr><td>Prio</td><td>Hoch</td></tr>"
                "<tr><td>betroffene Einheiten</td><td>A, B; C</td></tr>"
                "<tr><td>Owner</td><td>Max Mustermann</td></tr>"
                "</table>"
            ),
            source_ref="dummy",
            page_properties={"existing_key": "existing_value"},
        )

        result = ConfluenceTransformer().transform(page)

        self.assertNotIn("- **Status:**", result.body_markdown)
        self.assertNotIn("- **Prio:**", result.body_markdown)
        self.assertNotIn("- **betroffene Einheiten:**", result.body_markdown)
        self.assertIn("- **Owner:** Max Mustermann", result.body_markdown)
        self.assertEqual("In Arbeit", result.page_properties["status"])
        self.assertEqual("Hoch", result.page_properties["priorität"])
        self.assertEqual(["A", "B", "C"], result.page_properties["betroffene einheiten"])
        self.assertEqual("Max Mustermann", result.page_properties["owner"])
        self.assertEqual("existing_value", result.page_properties["existing_key"])
        self.assertFalse(any(w.code == "complex_table" for w in result.transform_warnings))

    def test_empty_values_are_not_written_to_properties(self) -> None:
        page = ConfluenceRawPage(
            page_id="2",
            space_key="DOC",
            title="Eigenschaften",
            body=(
                "<table>"
                "<tr><td>Status</td><td></td></tr>"
                "<tr><td>Owner</td><td>Max Mustermann</td></tr>"
                "</table>"
            ),
            source_ref="dummy",
        )

        result = ConfluenceTransformer().transform(page)

        self.assertNotIn("status", result.page_properties)
        self.assertEqual("Max Mustermann", result.page_properties["owner"])

    def test_regular_table_remains_markdown_table(self) -> None:
        page = ConfluenceRawPage(
            page_id="3",
            space_key="DOC",
            title="Fachliche Tabelle",
            body=(
                "<table>"
                "<tr><th>Produkt</th><th>Q1</th><th>Q2</th></tr>"
                "<tr><td>A</td><td>10</td><td>15</td></tr>"
                "<tr><td>B</td><td>7</td><td>8</td></tr>"
                "</table>"
            ),
            source_ref="dummy",
        )

        result = ConfluenceTransformer().transform(page)

        self.assertIn("| Produkt | Q1 | Q2 |", result.body_markdown)
        self.assertNotIn("- **Produkt:**", result.body_markdown)


if __name__ == "__main__":
    unittest.main()
