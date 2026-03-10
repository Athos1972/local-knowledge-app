"""Kleines manuelles Testscript für Loader und Markdown-Normalisierung.

Das Script lädt Markdown-Dateien aus `~/local-knowledge-data/domains`, zeigt
Basisinformationen der ersten Dokumente und erleichtert lokale Smoke-Tests ohne
zusätzliches Testframework.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from processing.markdown_normalizer import MarkdownNormalizer
from sources.filesystem.filesystem_loader import FilesystemLoader


def main() -> int:
    """Führt einen lokalen Smoke-Test für Loader + Normalizer aus."""
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
