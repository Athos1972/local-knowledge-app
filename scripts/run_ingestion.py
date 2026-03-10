from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from processing.file_writer import FileWriter
from processing.manifest import ProcessedDocumentRecord, RunManifest, generate_run_id, now_iso
from processing.markdown_normalizer import MarkdownNormalizer
from processing.processing_state import DocumentState, ProcessingState
from processing.simple_chunker import SimpleChunker
from sources.filesystem.filesystem_loader import FilesystemLoader

logger = AppLogger.get_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local knowledge ingestion pipeline.")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Reprocess all documents regardless of checksums.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    data_root = Path("~/local-knowledge-data").expanduser()
    source_root = data_root / "domains"
    manifests_dir = data_root / "system" / "manifests"
    state_path = manifests_dir / "latest_processing_state.json"

    mode = "full" if args.full_refresh else "incremental"
    run_manifest = RunManifest(run_id=generate_run_id(), started_at=now_iso(), mode=mode)

    logger.info("Ingestion run started | run_id=%s | mode=%s", run_manifest.run_id, mode)

    loader = FilesystemLoader(source_root)
    writer = FileWriter(data_root)
    chunker = SimpleChunker()

    state = ProcessingState() if args.full_refresh else ProcessingState.load(state_path)

    docs = loader.load()
    run_manifest.documents_seen = len(docs)

    for source_doc in docs:
        source_checksum = source_doc.source_checksum
        previous_state = state.documents.get(source_doc.id)

        if not args.full_refresh and previous_state and previous_state.source_checksum == source_checksum:
            run_manifest.documents_skipped += 1
            run_manifest.records.append(
                ProcessedDocumentRecord(
                    doc_id=source_doc.id,
                    source_ref=source_doc.source_ref,
                    title=source_doc.title,
                    source_checksum=source_checksum,
                    normalized_checksum=previous_state.normalized_checksum,
                    chunk_count=0,
                    processed_at=now_iso(),
                    status="skipped",
                )
            )
            logger.info("Skipping unchanged document: %s", source_doc.path)
            continue

        try:
            normalized_doc = MarkdownNormalizer.normalize(source_doc)
            chunks = chunker.chunk(normalized_doc)

            writer.write_document(normalized_doc)
            writer.write_metadata(normalized_doc)
            writer.write_chunks(normalized_doc.doc_id, chunks)

            processed_at = now_iso()
            state.documents[source_doc.id] = DocumentState(
                source_checksum=source_checksum,
                normalized_checksum=normalized_doc.normalized_checksum,
                last_processed_at=processed_at,
                title=source_doc.title,
                source_ref=source_doc.source_ref,
            )

            run_manifest.documents_processed += 1
            run_manifest.records.append(
                ProcessedDocumentRecord(
                    doc_id=source_doc.id,
                    source_ref=source_doc.source_ref,
                    title=source_doc.title,
                    source_checksum=source_checksum,
                    normalized_checksum=normalized_doc.normalized_checksum,
                    chunk_count=len(chunks),
                    processed_at=processed_at,
                    status="processed",
                )
            )
            logger.info("Processed document: %s", source_doc.path)
        except Exception as exc:  # noqa: BLE001
            run_manifest.documents_failed += 1
            run_manifest.records.append(
                ProcessedDocumentRecord(
                    doc_id=source_doc.id,
                    source_ref=source_doc.source_ref,
                    title=source_doc.title,
                    source_checksum=source_checksum,
                    normalized_checksum="",
                    chunk_count=0,
                    processed_at=now_iso(),
                    status="error",
                )
            )
            logger.exception("Failed processing document '%s': %s", source_doc.path, exc)

    run_manifest.finished_at = now_iso()

    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"run_manifest_{run_manifest.run_id}.json"
    manifest_path.write_text(run_manifest.to_json(), encoding="utf-8")
    state.save(state_path)

    logger.info(
        "Run summary | seen=%s processed=%s skipped=%s failed=%s mode=%s manifest=%s",
        run_manifest.documents_seen,
        run_manifest.documents_processed,
        run_manifest.documents_skipped,
        run_manifest.documents_failed,
        run_manifest.mode,
        manifest_path,
    )

    return 0 if run_manifest.documents_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
