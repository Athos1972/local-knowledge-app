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

        self.assertNotIn("- **Status:** In Arbeit", result.body_markdown)
        self.assertIn("- **Stream:** Abrechnung", result.body_markdown)
        self.assertIn("- **Owner:** Max Mustermann", result.body_markdown)
        self.assertEqual("In Arbeit", result.page_properties["status"])
        self.assertEqual("In Arbeit", result.promoted_properties["status"])
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
        self.assertEqual("Done", result.promoted_properties["status"])
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
        self.assertEqual([], result.extra_documents)

    def test_complex_table_creates_extra_document_and_reference(self) -> None:
        rows = "".join(f"<tr><td>R{i}</td><td>{i}</td><td>{i+1}</td><td>{i+2}</td><td>{i+3}</td><td>{i+4}</td><td>{i+5}</td></tr>" for i in range(1, 5))
        page = ConfluenceRawPage(
            page_id="123456",
            space_key="DOC",
            title="Marktkommunikation",
            body="<table><tr><th>A</th><th>B</th><th>C</th><th>D</th><th>E</th><th>F</th><th>G</th></tr>" + rows + "</table>",
            source_ref="dummy",
            source_url="https://example.local/page",
            labels=["alpha"],
        )

        result = ConfluenceTransformer().transform(page)

        self.assertEqual(1, len(result.extra_documents))
        extra = result.extra_documents[0]
        self.assertEqual("123456__marktkommunikation__table_01.md", extra.file_name)
        self.assertIn("[Komplexe Tabelle ausgelagert: 123456__marktkommunikation__table_01.md]", result.body_markdown)
        self.assertEqual("confluence_table", extra.doc_type)
        self.assertTrue(extra.metadata.get("table_complexity"))
        self.assertEqual(1, extra.metadata.get("table_index"))
        self.assertFalse(any(w.code == "complex_table" for w in result.transform_warnings))

    def test_promoted_properties_cover_aliases_and_lists(self) -> None:
        page = ConfluenceRawPage(
            page_id="4",
            space_key="DOC",
            title="Seiteneigenschaften",
            body=(
                "<table>"
                "<tr><td>Prio</td><td>Hoch</td></tr>"
                "<tr><td>Betroffene Einheiten</td><td>Sales, Billing; Ops</td></tr>"
                "<tr><td>Status</td><td><ac:structured-macro ac:name=\"status\"><ac:parameter ac:name=\"title\">In Arbeit</ac:parameter></ac:structured-macro></td></tr>"
                "</table>"
            ),
            source_ref="dummy",
        )

        result = ConfluenceTransformer().transform(page)

        self.assertEqual("Hoch", result.promoted_properties["priorität"])
        self.assertEqual(["Sales", "Billing", "Ops"], result.promoted_properties["betroffene einheiten"])
        self.assertEqual("In Arbeit", result.promoted_properties["status"])
        self.assertNotIn("- **Prio:**", result.body_markdown)
        self.assertNotIn("- **Status:**", result.body_markdown)

    def test_details_table_with_header_column_uses_only_first_data_column(self) -> None:
        page = ConfluenceRawPage(
            page_id="5",
            space_key="DOC",
            title="Seiteneigenschaften mit Header-Spalte",
            body=(
                '<ac:structured-macro ac:name="details">'
                '<ac:rich-text-body>'
                "<table>"
                "<tr><th>Status</th><td>Inhalt</td><td>blablabla</td></tr>"
                "<tr><th>Owner</th><td>Max Mustermann</td><td>ignorieren</td></tr>"
                "</table>"
                "</ac:rich-text-body>"
                "</ac:structured-macro>"
            ),
            source_ref="dummy",
        )

        result = ConfluenceTransformer().transform(page)

        self.assertIn("- **Owner:** Max Mustermann", result.body_markdown)
        self.assertNotIn("blablabla", result.body_markdown)
        self.assertNotIn("ignorieren", result.body_markdown)
        self.assertEqual("Inhalt", result.page_properties["status"])

    def test_single_row_details_table_ignores_third_column_and_keeps_status_value(self) -> None:
        page = ConfluenceRawPage(
            page_id="6",
            space_key="DOC",
            title="Priorität",
            body=(
                '<ac:structured-macro ac:name="details">'
                '<ac:rich-text-body>'
                "<table>"
                "<tr>"
                "<th>Priorität</th>"
                '<td><ac:structured-macro ac:name="status"><ac:parameter ac:name="title">SOLL</ac:parameter></ac:structured-macro></td>'
                "<td>Bitte aus der 3. Spalte das passende Widget in die 2. Spalte kopieren.</td>"
                "</tr>"
                "</table>"
                "</ac:rich-text-body>"
                "</ac:structured-macro>"
            ),
            source_ref="dummy",
        )

        result = ConfluenceTransformer().transform(page)

        self.assertNotIn("| Priorität |", result.body_markdown)
        self.assertNotIn("Bitte aus der 3. Spalte", result.body_markdown)
        self.assertEqual("SOLL", result.page_properties["priorität"])


if __name__ == "__main__":
    unittest.main()
