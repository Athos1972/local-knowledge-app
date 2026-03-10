from __future__ import annotations

import unittest

from processing.confluence.models import ConfluenceRawPage
from processing.confluence.transformer import ConfluenceTransformer


class ConfluenceTableTransformerTests(unittest.TestCase):
    def test_key_value_table_is_rendered_as_list_and_added_to_frontmatter_properties(self) -> None:
        page = ConfluenceRawPage(
            page_id="1",
            space_key="DOC",
            title="Eigenschaften",
            body=(
                "<p>Einleitung</p>"
                "<table>"
                "<tr><td>Status</td><td>In Arbeit</td></tr>"
                "<tr><td>Stream</td><td>Abrechnung</td></tr>"
                "<tr><td>Owner</td><td>Max Mustermann</td></tr>"
                "</table>"
            ),
            source_ref="dummy",
            page_properties={"existing_key": "existing_value"},
        )

        result = ConfluenceTransformer().transform(page)

        self.assertIn("- **Status:** In Arbeit", result.body_markdown)
        self.assertIn("- **Stream:** Abrechnung", result.body_markdown)
        self.assertIn("- **Owner:** Max Mustermann", result.body_markdown)
        self.assertEqual("In Arbeit", result.page_properties["status"])
        self.assertEqual("Abrechnung", result.page_properties["stream"])
        self.assertEqual("Max Mustermann", result.page_properties["owner"])
        self.assertEqual("existing_value", result.page_properties["existing_key"])
        self.assertFalse(any(w.code == "complex_table" for w in result.transform_warnings))

    def test_existing_page_property_is_not_overwritten(self) -> None:
        page = ConfluenceRawPage(
            page_id="2",
            space_key="DOC",
            title="Eigenschaften",
            body=(
                "<table>"
                "<tr><td>Status</td><td>In Arbeit</td></tr>"
                "<tr><td>Owner</td><td>Max Mustermann</td></tr>"
                "</table>"
            ),
            source_ref="dummy",
            page_properties={"status": "Done"},
        )

        result = ConfluenceTransformer().transform(page)

        self.assertEqual("Done", result.page_properties["status"])
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
