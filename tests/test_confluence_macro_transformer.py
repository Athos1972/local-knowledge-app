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


    def test_table_chart_and_table_transformer_unwrap_table_content(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="table-transformer">'
            '<ac:rich-text-body>'
            '<ac:structured-macro ac:name="table-chart">'
            '<ac:rich-text-body>'
            '<table><tr><th>X</th><th>Y</th></tr><tr><td>1</td><td>2</td></tr></table>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertTrue("| X | Y |" in result.body_markdown or "- **X:** Y" in result.body_markdown)
        self.assertNotIn("table-chart", result.unsupported_macros)
        self.assertNotIn("table-transformer", result.unsupported_macros)

    def test_page_properties_report_is_ignored_without_warning(self) -> None:
        result = self._transform(
            '<p>Intro</p>'
            '<ac:structured-macro ac:name="page-properties-report"></ac:structured-macro>'
            '<p>Outro</p>'
        )

        self.assertIn("Intro", result.body_markdown)
        self.assertIn("Outro", result.body_markdown)
        self.assertNotIn("page-properties-report", result.unsupported_macros)
        self.assertFalse(any(w.code == "unsupported_macro" for w in result.transform_warnings))

    def test_placeholder_macro_is_removed_completely(self) -> None:
        result = self._transform(
            '<p>Vorher</p>'
            '<ac:placeholder ac:type="mention">Formulartext</ac:placeholder>'
            '<p>Nachher</p>'
        )

        self.assertIn("Vorher", result.body_markdown)
        self.assertIn("Nachher", result.body_markdown)
        self.assertNotIn("Formulartext", result.body_markdown)

    def test_empty_nested_headings_are_removed_bottom_up(self) -> None:
        result = self._transform(
            '<h1>Top 1</h1>'
            '<h2>Top 1.1</h2>'
            '<h3>Leer</h3>'
            '<p> </p>'
            '<h2>Mit Inhalt</h2>'
            '<p>Text</p>'
            '<h1>Top 2</h1>'
            '<p> </p>'
            '<h1>Top 3</h1>'
            '<h2>Leer 2</h2>'
        )

        self.assertNotIn("### Leer", result.body_markdown)
        self.assertNotIn("## Top 1.1", result.body_markdown)
        self.assertIn("## Mit Inhalt", result.body_markdown)
        self.assertIn("Text", result.body_markdown)
        self.assertNotIn("# Top 2", result.body_markdown)
        self.assertNotIn("## Leer 2", result.body_markdown)
        self.assertNotIn("# Top 3", result.body_markdown)



    def test_task_extraction_helpers(self) -> None:
        transformer = ConfluenceTransformer().macro_transformer
        body = '<ri:user ri:display-name="Franzi" /> Architektur bestätigt 2026-02-14 <a href="https://example.org">Doc</a>'

        mentions = transformer._extract_mentions(body)
        links = transformer._extract_links(body)
        due_date = transformer._extract_due_date(body)
        cleaned = transformer._clean_task_text(transformer._html_to_text(body), mentions)

        self.assertEqual(mentions, ['Franzi'])
        self.assertEqual(links, ['https://example.org'])
        self.assertEqual(due_date, '2026-02-14')
        self.assertEqual(cleaned, 'Architektur bestätigt 2026-02-14 Doc')

    def test_task_classification_decision_and_triviality(self) -> None:
        transformer = ConfluenceTransformer().macro_transformer
        decision_task = transformer._parse_task_item(
            '<ac:task-status>complete</ac:task-status><ac:task-body>CR freigegeben</ac:task-body>'
        )
        trivial_task = transformer._parse_task_item(
            '<ac:task-status>incomplete</ac:task-status><ac:task-body><ri:user ri:display-name="Peter" /> FYI</ac:task-body>'
        )

        self.assertTrue(decision_task.contains_decision_signal)
        self.assertEqual(decision_task.keep_reason, 'decision_signal')
        self.assertEqual(decision_task.drop_reason, '')
        self.assertEqual(trivial_task.keep_reason, '')
        self.assertEqual(trivial_task.drop_reason, 'trivial_communication')

    def test_task_mentions_links_due_dates_and_status_rendering(self) -> None:
        result = self._transform(
            '<ac:task-list>'
            '<ac:task>'
            '<ac:task-status>incomplete</ac:task-status>'
            '<ac:task-body><ri:user ri:display-name="Peter" /> Prüfen ob EMMA im S/4 Utilities anders heißt</ac:task-body>'
            '</ac:task>'
            '<ac:task>'
            '<ac:task-status>complete</ac:task-status>'
            '<ac:task-body><ri:user ri:display-name="Franzi" /> Architektur bestätigt 2026-02-14</ac:task-body>'
            '</ac:task>'
            '<ac:task>'
            '<ac:task-status>complete</ac:task-status>'
            '<ac:task-body>CR freigegeben <a href="https://example.org/cr/123">Link</a></ac:task-body>'
            '</ac:task>'
            '</ac:task-list>'
        )

        self.assertIn('## Open Tasks', result.body_markdown)
        self.assertIn('## Completed Tasks', result.body_markdown)
        self.assertIn('Prüfen ob EMMA im S/4 Utilities anders heißt.', result.body_markdown)
        self.assertIn('Mentions: Peter.', result.body_markdown)
        self.assertIn('Status: open.', result.body_markdown)
        self.assertIn('Architektur bestätigt 2026-02-14.', result.body_markdown)
        self.assertIn('Mentions: Franzi.', result.body_markdown)
        self.assertIn('Status: completed.', result.body_markdown)
        self.assertIn('Date: 2026-02-14.', result.body_markdown)
        self.assertIn('CR freigegeben Link.', result.body_markdown)
        self.assertIn('Links: https://example.org/cr/123.', result.body_markdown)

        self.assertEqual(result.promoted_properties.get('open_task_count'), 1)
        self.assertEqual(result.promoted_properties.get('completed_task_count'), 2)
        self.assertEqual(result.promoted_properties.get('open_task_mentions'), ['Peter'])
        self.assertEqual(result.promoted_properties.get('completed_task_mentions'), ['Franzi'])

    def test_trivial_tasks_are_dropped_without_length_cutoff(self) -> None:
        result = self._transform(
            '<ac:task-list>'
            '<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body><ri:user ri:display-name="Peter" /> FYI</ac:task-body></ac:task>'
            '<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>ok</ac:task-body></ac:task>'
            '<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body><ri:user ri:display-name="Anna" /> bitte prüfen</ac:task-body></ac:task>'
            '</ac:task-list>'
        )

        self.assertNotIn('## Open Tasks', result.body_markdown)
        self.assertNotIn('FYI', result.body_markdown)
        self.assertNotIn('bitte prüfen', result.body_markdown)
        self.assertNotIn('open_task_count', result.promoted_properties)

    def test_short_but_informative_completed_task_is_kept(self) -> None:
        result = self._transform(
            '<ac:task-list>'
            '<ac:task><ac:task-status>complete</ac:task-status><ac:task-body>CR freigegeben</ac:task-body></ac:task>'
            '</ac:task-list>'
        )

        self.assertIn('## Completed Tasks', result.body_markdown)
        self.assertIn('CR freigegeben.', result.body_markdown)
        self.assertIn('Status: completed.', result.body_markdown)
        self.assertEqual(result.promoted_properties.get('completed_task_count'), 1)

    def test_log_title_pattern_is_ignored_case_insensitive(self) -> None:
        transformer = ConfluenceTransformer()

        self.assertTrue(transformer.should_ignore_title("Log 2024"))
        self.assertTrue(transformer.should_ignore_title("log 1999 Projektnotizen"))
        self.assertTrue(transformer.should_ignore_title("  LOG 2030 Extra"))
        self.assertFalse(transformer.should_ignore_title("Logbuch 2024"))
        self.assertFalse(transformer.should_ignore_title("Log 24"))
        self.assertFalse(transformer.should_ignore_title("Status Log 2024"))


    def test_ignored_macros_are_removed_without_warning(self) -> None:
        result = self._transform(
            '<p>Vorher</p>'
            '<ac:structured-macro ac:name="contentbylabel"></ac:structured-macro>'
            '<ac:structured-macro ac:name="anchor"></ac:structured-macro>'
            '<ac:structured-macro ac:name="create-from-template"></ac:structured-macro>'
            '<ac:structured-macro ac:name="livesearch"></ac:structured-macro>'
            '<ac:structured-macro ac:name="profile"></ac:structured-macro>'
            '<ac:structured-macro ac:name="tasks-report-macro"></ac:structured-macro>'
            '<ac:structured-macro ac:name="children"></ac:structured-macro>'
            '<ac:structured-macro ac:name="classifications-status"></ac:structured-macro>'
            '<ac:structured-macro ac:name="detailssummary"></ac:structured-macro>'
            '<p>Nachher</p>'
        )

        self.assertIn("Vorher", result.body_markdown)
        self.assertIn("Nachher", result.body_markdown)
        self.assertNotIn("contentbylabel", result.unsupported_macros)
        self.assertNotIn("anchor", result.unsupported_macros)
        self.assertNotIn("create-from-template", result.unsupported_macros)
        self.assertNotIn("livesearch", result.unsupported_macros)
        self.assertNotIn("profile", result.unsupported_macros)
        self.assertNotIn("tasks-report-macro", result.unsupported_macros)
        self.assertNotIn("children", result.unsupported_macros)
        self.assertNotIn("classifications-status", result.unsupported_macros)
        self.assertNotIn("detailssummary", result.unsupported_macros)
        self.assertFalse(any(w.code == "unsupported_macro" for w in result.transform_warnings))

    def test_unwrapped_container_macros_keep_inner_content_without_warning(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="section">'
            '<ac:rich-text-body>'
            '<ac:structured-macro ac:name="column">'
            '<ac:rich-text-body>'
            '<ac:structured-macro ac:name="multiexcerpt">'
            '<ac:rich-text-body><p>Innerer Inhalt</p></ac:rich-text-body>'
            '</ac:structured-macro>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
            '</ac:rich-text-body>'
            '</ac:structured-macro>'
            '<ac:structured-macro ac:name="macrosuite-panel">'
            '<ac:rich-text-body><p>Panel-Inhalt</p></ac:rich-text-body>'
            '</ac:structured-macro>'
            '<ac:structured-macro ac:name="macrosuite-cards">'
            '<ac:rich-text-body><p>Cards-Inhalt</p></ac:rich-text-body>'
            '</ac:structured-macro>'
            '<ac:structured-macro ac:name="classifications-combined-taxonomy">'
            '<ac:rich-text-body><p>Taxonomie-Inhalt</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("Innerer Inhalt", result.body_markdown)
        self.assertIn("Panel-Inhalt", result.body_markdown)
        self.assertIn("Cards-Inhalt", result.body_markdown)
        self.assertIn("Taxonomie-Inhalt", result.body_markdown)
        self.assertNotIn("section", result.unsupported_macros)
        self.assertNotIn("column", result.unsupported_macros)
        self.assertNotIn("multiexcerpt", result.unsupported_macros)
        self.assertNotIn("macrosuite-panel", result.unsupported_macros)
        self.assertNotIn("macrosuite-cards", result.unsupported_macros)
        self.assertNotIn("classifications-combined-taxonomy", result.unsupported_macros)

    def test_drawio_direct_xml_extracts_elements_and_relationships(self) -> None:
        drawio_xml = (
            '<mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="2" value="API Gateway" vertex="1" parent="1"/>'
            '<mxCell id="3" value="Billing Service" vertex="1" parent="1"/>'
            '<mxCell id="4" value="Event Mesh" vertex="1" parent="1"/>'
            '<mxCell id="5" edge="1" source="2" target="3" value="sync" parent="1"/>'
            '<mxCell id="6" edge="1" source="3" target="4" parent="1"/>'
            '</root></mxGraphModel>'
        )
        result = self._transform(
            '<ac:structured-macro ac:name="drawio">'
            f'<ac:plain-text-body><![CDATA[{drawio_xml}]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("## Diagramm: Unbenannt", result.body_markdown)
        self.assertIn("### Diagramm-Elemente", result.body_markdown)
        self.assertIn("- API Gateway", result.body_markdown)
        self.assertIn("### Beziehungen", result.body_markdown)
        self.assertIn("- API Gateway -> Billing Service (sync)", result.body_markdown)
        self.assertIn("- Billing Service -> Event Mesh", result.body_markdown)
        self.assertTrue(any(w.code == "drawio_macro_detected" for w in result.transform_warnings))

    def test_drawio_without_edges_keeps_texts(self) -> None:
        drawio_xml = (
            '<mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="2" value="Nur Text A" vertex="1" parent="1"/>'
            '<mxCell id="3" value="Nur Text B" vertex="1" parent="1"/>'
            '</root></mxGraphModel>'
        )
        result = self._transform(
            '<ac:structured-macro ac:name="diagrams.net">'
            f'<ac:plain-text-body><![CDATA[{drawio_xml}]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("Nur Text A", result.body_markdown)
        self.assertIn("Nur Text B", result.body_markdown)
        self.assertNotIn("### Beziehungen", result.body_markdown)

    def test_drawio_html_labels_are_cleaned(self) -> None:
        drawio_xml = (
            '<mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="2" value="&lt;div&gt;API &amp;amp; Gateway&lt;br&gt;Prod&lt;/div&gt;" vertex="1" parent="1"/>'
            '</root></mxGraphModel>'
        )
        result = self._transform(
            '<ac:structured-macro ac:name="inc-drawio">'
            f'<ac:plain-text-body><![CDATA[{drawio_xml}]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("API & Gateway", result.body_markdown)
        self.assertIn("Prod", result.body_markdown)

    def test_drawio_broken_payload_emits_warning_and_fallback(self) -> None:
        result = self._transform(
            '<ac:structured-macro ac:name="draw.io">'
            '<ac:plain-text-body><![CDATA[not-a-valid-drawio-content]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("Draw.io-Diagramm erkannt, aber nicht extrahierbar.", result.body_markdown)
        self.assertTrue(any(w.code == "drawio_decode_failed" for w in result.transform_warnings))

    def test_drawio_deduplicates_identical_texts(self) -> None:
        drawio_xml = (
            '<mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="2" value="Billing Service" vertex="1" parent="1"/>'
            '<mxCell id="3" value="Billing Service" vertex="1" parent="1"/>'
            '</root></mxGraphModel>'
        )
        result = self._transform(
            '<ac:structured-macro ac:name="drawio">'
            f'<ac:plain-text-body><![CDATA[{drawio_xml}]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertEqual(result.body_markdown.count("- Billing Service"), 1)

    def test_drawio_ignores_technical_cells_without_value(self) -> None:
        drawio_xml = (
            '<mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="2" vertex="1" parent="1"/>'
            '<mxCell id="3" edge="1" parent="1" source="2" target="1"/>'
            '</root></mxGraphModel>'
        )
        result = self._transform(
            '<ac:structured-macro ac:name="drawio">'
            f'<ac:plain-text-body><![CDATA[{drawio_xml}]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )

        self.assertIn("Draw.io-Diagramm erkannt, aber kein extrahierbarer semantischer Inhalt gefunden.", result.body_markdown)
        self.assertTrue(any(w.code == "drawio_no_semantic_content" for w in result.transform_warnings))


if __name__ == "__main__":
    unittest.main()
