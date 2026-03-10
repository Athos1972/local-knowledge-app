"""Kleines manuelles Testscript für Loader, Normalizer und Chunking.

Das Script lädt Markdown-Dateien aus `~/local-knowledge-data/domains`, zeigt
Basisinformationen der ersten Dokumente und ergänzt einen Mini-Selftest für den
MarkdownChunker (Header-Fall + Fallback ohne Header).
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from processing.markdown_chunker import MarkdownChunker
from processing.markdown_normalizer import MarkdownNormalizer
from sources.document import NormalizedDocument, SourceInfo
from sources.filesystem.filesystem_loader import FilesystemLoader


def main() -> int:
    """Führt einen lokalen Smoke-Test für Loader + Normalizer + Chunker aus."""
    logger = AppLogger.get_logger()

    domains_root = Path.home() / "local-knowledge-data" / "domains"
    loader = FilesystemLoader(domains_root)
    normalizer = MarkdownNormalizer()

    documents = list(loader.load())
    logger.info("Dokumente geladen: %s", len(documents))

    for source_doc in documents[:5]:
        normalized = normalizer.normalize(source_doc)
        print(f"doc_id: {source_doc.doc_id}")
        print(f"title: {normalized.title}")
        print(f"relative_path: {source_doc.metadata.get('relative_path')}")
        print(f"tags: {normalized.tags}")
        print(f"body_preview: {normalized.body[:100]!r}")
        print("-" * 80)

    _run_chunker_smoke_tests()
    return 0


def _run_chunker_smoke_tests() -> None:
    """Prüft markdown-aware Chunking mit und ohne Header ohne großes Framework."""
    source = SourceInfo(
        source_type="filesystem",
        source_name="local-knowledge-data",
        source_ref="smoke-test.md",
    )

    chunker = MarkdownChunker(max_chunk_size=120, min_chunk_size=30, overlap=20)

    markdown_doc = NormalizedDocument(
        doc_id="smoke-header",
        title="Header Test",
        body=(
            "# Event Mesh Architektur\n"
            "Einleitung mit Kontext.\n\n"
            "## Komponenten\n"
            "Kyma, Topics und Event Mesh Services.\n\n"
            "### Nachrichtenfluss\n"
            "Producer -> Broker -> Consumer mit stabilen Konventionen."
        ),
        doc_type="note",
        mime_type="text/markdown",
        source=source,
        tags=["architektur", "event-mesh"],
        checksum="checksum-header",
    )
    markdown_chunks = chunker.chunk_document(markdown_doc)
    assert len(markdown_chunks) >= 2, "Markdown-Dokument sollte mehrere Chunks erzeugen"
    assert markdown_chunks[0].metadata.get("section_level") in {1, 2, 3}

    plain_doc = NormalizedDocument(
        doc_id="smoke-plain",
        title="Plain Test",
        body=" ".join(["Plaintext ohne Header."] * 40),
        doc_type="note",
        mime_type="text/markdown",
        source=source,
        tags=["plain"],
        checksum="checksum-plain",
    )
    plain_chunks = chunker.chunk_document(plain_doc)
    assert len(plain_chunks) >= 1, "Fallback sollte weiterhin Chunks erzeugen"
    assert "section_level" not in plain_chunks[0].metadata, "Fallback bleibt beim SimpleChunker-Metadatenformat"

    print(f"chunker_smoke: markdown_chunks={len(markdown_chunks)} plain_chunks={len(plain_chunks)}")


if __name__ == "__main__":
    raise SystemExit(main())
