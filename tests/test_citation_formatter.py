from __future__ import annotations

import unittest

from retrieval.citation_formatter import CitationFormatter


class CitationFormatterTests(unittest.TestCase):
    def test_format_answer_normalizes_source_markers_and_appends_sources_block(self) -> None:
        formatter = CitationFormatter()
        sources = [
            {"source_number": 1, "chunk_id": "c1", "title": "Event Mesh Architektur", "section_header": "Kyma Services"},
            {"source_number": 2, "chunk_id": "c2", "title": "Event Mesh Architektur", "section_header": "Event Topics"},
        ]

        answer, citation_map = formatter.format_answer(
            "Event Mesh verbindet Producer und Consumer [SOURCE 1] und nutzt Topics [source 2].",
            sources,
        )

        self.assertEqual({"c1": 1, "c2": 2}, citation_map)
        self.assertIn("ANSWER", answer)
        self.assertIn("[1]", answer)
        self.assertIn("[2]", answer)
        self.assertIn("Sources", answer)
        self.assertIn("[1] Event Mesh Architektur – Kyma Services", answer)
        self.assertIn("[2] Event Mesh Architektur – Event Topics", answer)

    def test_format_answer_adds_citations_when_missing_in_text(self) -> None:
        formatter = CitationFormatter()
        sources = [{"source_number": 3, "chunk_id": "c3", "title": "Doc"}]

        answer, _ = formatter.format_answer("Kurze Antwort ohne Marker.", sources)

        self.assertIn("Kurze Antwort ohne Marker. [3]", answer)


if __name__ == "__main__":
    unittest.main()
