from __future__ import annotations

import unittest

from processing.confluence.models import ConfluenceRawPage
from processing.confluence.transformer import ConfluenceTransformer


class ConfluenceMacroTransformerTests(unittest.TestCase):
    def _transform(self, body: str):
        page = ConfluenceRawPage(
            page_id="1",
            space_key="DOC",
            title="Makros",
            body=body,
            source_ref="dummy",
        )
        return ConfluenceTransformer().transform(page)

    def test_details_macro_is_rendered_without_unsupported_marker(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="details">'
            '<ac:parameter ac:name="title">Wichtige Hinweise</ac:parameter>'
            '<ac:rich-text-body><p>Inhalt im Details-Block</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("## Wichtige Hinweise", result.body_markdown)
        self.assertIn("Inhalt im Details-Block", result.body_markdown)
        self.assertNotIn("[UNSUPPORTED_MACRO: details]", result.body_markdown)
        self.assertNotIn("details", result.unsupported_macros)

    def test_toc_is_ignored_without_unsupported_marker(self) -> None:
        result = self._transform(
            '<p>Start</p>'
            '<ac:structured-macro ac:name="toc"></ac:structured-macro>'
            '<p>Ende</p>'
        )

        self.assertIn("Start", result.body_markdown)
        self.assertIn("Ende", result.body_markdown)
        self.assertNotIn("toc", result.unsupported_macros)
        self.assertNotIn("UNSUPPORTED_MACRO", result.body_markdown)

    def test_plantuml_is_rendered_as_code_block(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="plantuml">'
            '<ac:plain-text-body><![CDATA[@startuml\nAlice -> Bob: Hallo\n@enduml]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("```plantuml", result.body_markdown)
        self.assertIn("Alice -> Bob: Hallo", result.body_markdown)
        self.assertNotIn("plantuml", result.unsupported_macros)

    def test_table_filter_unwraps_table_content(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="table-filter">'
            '<ac:rich-text-body>'
            '<table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("| A | B | C |", result.body_markdown)
        self.assertNotIn("table-filter", result.unsupported_macros)

    def test_jira_and_view_file_have_basic_rendering(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="jira">'
            '<ac:parameter ac:name="key">ABC-123</ac:parameter>'
            '</ac:structured-macro>'
            '<ac:structured-macro ac:name="view-file">'
            '<ac:rich-text-body><ri:attachment ri:filename="Architektur.pdf" /></ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("**Jira-Vorgang:** ABC-123", result.body_markdown)
        self.assertIn("**Datei:** Architektur.pdf", result.body_markdown)
        self.assertNotIn("jira", result.unsupported_macros)
        self.assertNotIn("view-file", result.unsupported_macros)

    def test_invalid_macro_name_is_normalized_to_unknown_macro(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="Das ist ein sehr langer deutscher Fließtext als Makroname">'
            '<ac:rich-text-body><p>Text</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("unknown_macro", result.unsupported_macros)
        self.assertNotIn("Fließtext als Makroname", " ".join(result.unsupported_macros))
        self.assertTrue(any(w.code == "macro_name_parse_error" for w in result.transform_warnings))

    def test_unsupported_macro_unwraps_inner_text(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="unsupported">'
            '<ac:rich-text-body><p>Geretteter Text</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("Geretteter Text", result.body_markdown)
        self.assertIn("unsupported", result.unsupported_macros)

    def test_nested_unsupported_macros_are_processed_recursively(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="outer">'
            '<ac:rich-text-body>'
            '<ac:structured-macro ac:name="inner">'
            '<ac:rich-text-body><p>Tiefes Element</p></ac:rich-text-body>'
            '</ac:structured-macro>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("Tiefes Element", result.body_markdown)
        self.assertIn("outer", result.unsupported_macros)
        self.assertIn("inner", result.unsupported_macros)

    def test_unsupported_macro_with_table_keeps_table_transform(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="outer">'
            '<ac:rich-text-body>'
            '<table><tr><th>Spalte</th><th>Wert</th></tr><tr><td>A</td><td>B</td></tr></table>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertTrue("| Spalte | Wert |" in result.body_markdown or "- **Spalte:** Wert" in result.body_markdown)
        self.assertIn("outer", result.unsupported_macros)


if __name__ == "__main__":
    unittest.main()
