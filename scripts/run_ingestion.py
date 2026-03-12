#!/usr/bin/env python3
"""Ausführbares Ingestion-Script für lokale Markdown-Quellen.

Ablauf pro Dokument:
1) Laden über FilesystemLoader
2) Optionaler Incremental-Check über Source-Checksumme
3) Normalisieren (inkl. Frontmatter)
4) Schreiben von Dokument + Metadaten
5) Chunking + Schreiben der Chunks
6) Manifest und Processing-State persistieren
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from common.time_utils import format_duration_human
from processing.audit import AuditStage, ReasonCode, build_audit_components
from processing.file_writer import FileWriter
from processing.manifest import ProcessedDocumentRecord, RunManifest, generate_run_id
from processing.markdown_normalizer import MarkdownNormalizer
from processing.processing_state import ProcessingState
from processing.markdown_chunker import MarkdownChunker
from sources.document import stable_hash, utc_now_iso
from sources.filesystem.filesystem_loader import FilesystemLoader


def parse_args() -> argparse.Namespace:
    """Liest CLI-Parameter für Ausführungsmodus ein."""
    parser = argparse.ArgumentParser(description="Local knowledge ingestion")
    parser.add_argument(
        "--full-refresh",
        "--full",
        dest="full_refresh",
        action="store_true",
        help="Erzwingt komplette Neuverarbeitung aller Dokumente.",
    )
    parser.add_argument("--run-id", dest="run_id", default=None, help="Optionale externe Run-ID für Audit/Logs")
    parser.add_argument("--source-instance", dest="source_instance", default="local-filesystem")
    return parser.parse_args()


def main() -> int:
    """Führt die lokale Markdown-Ingestion inkl. Manifest/Incremental-Logik aus."""
    args = parse_args()
    logger = AppLogger.get_logger()
    started_perf = perf_counter()

    data_root = Path.home() / "local-knowledge-data"
    domains_root = data_root / "domains"
    manifests_dir = data_root / "system" / "manifests"
    state_path = manifests_dir / "latest_processing_state.json"

    mode = "full" if args.full_refresh else "incremental"
    effective_run_id = args.run_id or generate_run_id()
    run_manifest = RunManifest(
        run_id=effective_run_id,
        started_at=utc_now_iso(),
        mode=mode,
    )

    loader = FilesystemLoader(domains_root)
    normalizer = MarkdownNormalizer()
    chunker = MarkdownChunker()
    writer = FileWriter(data_root)
    state = ProcessingState.load(state_path)
    run_context, audit = build_audit_components(
        data_root=data_root,
        source_type="filesystem",
        source_instance=args.source_instance,
        mode=mode,
        run_id=effective_run_id,
    )

    logger.info("Ingestion started. mode=%s run_id=%s", mode, run_manifest.run_id)

    for source_doc in loader.load():
        run_manifest.documents_seen += 1
        with audit.stage(
            run_id=run_context.run_id,
            source_type="filesystem",
            source_instance=args.source_instance,
            stage=AuditStage.DISCOVER,
            document_id=source_doc.doc_id,
            document_uri=source_doc.source.source_ref,
            document_title=source_doc.title,
        ) as discover_evt:
            discover_evt.event.output_count = 1

        with audit.stage(
            run_id=run_context.run_id,
            source_type="filesystem",
            source_instance=args.source_instance,
            stage=AuditStage.LOAD,
            document_id=source_doc.doc_id,
            document_uri=source_doc.source.source_ref,
            document_title=source_doc.title,
        ) as load_evt:
            load_evt.event.output_count = len(source_doc.content)

        source_checksum = stable_hash(source_doc.content)
        existing_state = state.documents.get(source_doc.doc_id)

        if (
            not args.full_refresh
            and existing_state is not None
            and existing_state.source_checksum == source_checksum
        ):
            with audit.stage(
                run_id=run_context.run_id,
                source_type="filesystem",
                source_instance=args.source_instance,
                stage=AuditStage.FILTER,
                document_id=source_doc.doc_id,
                document_uri=source_doc.source.source_ref,
                document_title=source_doc.title,
            ) as filter_evt:
                filter_evt.skipped(ReasonCode.FILTERED_BY_RULE, "Dokument unverändert (Checksumme identisch)")

            run_manifest.documents_skipped += 1
            processed_at = utc_now_iso()
            run_manifest.records.append(
                ProcessedDocumentRecord(
                    doc_id=source_doc.doc_id,
                    source_ref=source_doc.source.source_ref,
                    title=source_doc.title,
                    source_checksum=source_checksum,
                    normalized_checksum=existing_state.normalized_checksum,
                    chunk_count=0,
                    processed_at=processed_at,
                    status="skipped",
                )
            )
            logger.info(
                "Skipped unchanged doc_id=%s source_ref=%s",
                source_doc.doc_id,
                source_doc.source.source_ref,
            )
            continue

        try:
            with audit.stage(
                run_id=run_context.run_id,
                source_type="filesystem",
                source_instance=args.source_instance,
                stage=AuditStage.TRANSFORM,
                document_id=source_doc.doc_id,
                document_uri=source_doc.source.source_ref,
                document_title=source_doc.title,
            ) as transform_evt:
                transform_evt.event.input_count = len(source_doc.content)
                normalized = normalizer.normalize(source_doc)
                transform_evt.event.output_count = len(normalized.body)
                if not normalized.body.strip():
                    transform_evt.warning(ReasonCode.NO_TEXT_AFTER_CLEANUP, "Nach Normalisierung ist kein Text mehr vorhanden")

            writer.write_document(normalized)

            with audit.stage(
                run_id=run_context.run_id,
                source_type="filesystem",
                source_instance=args.source_instance,
                stage=AuditStage.CHUNK,
                document_id=normalized.doc_id,
                document_uri=normalized.source.source_ref,
                document_title=normalized.title,
            ) as chunk_evt:
                chunk_evt.event.input_count = len(normalized.body)
                chunks = chunker.chunk_document(normalized)
                chunk_evt.event.chunk_count = len(chunks)
                chunk_evt.event.output_count = len(chunks)
                if not chunks:
                    chunk_evt.skipped(ReasonCode.NO_CHUNKS_CREATED, "Chunking ergab keine Chunks")

            writer.write_chunks(normalized.doc_id, chunks)

            processed_at = utc_now_iso()
            state.update_document(
                doc_id=normalized.doc_id,
                source_checksum=source_checksum,
                normalized_checksum=normalized.checksum,
                last_processed_at=processed_at,
                title=normalized.title,
                source_ref=normalized.source.source_ref,
            )

            run_manifest.documents_processed += 1
            run_manifest.records.append(
                ProcessedDocumentRecord(
                    doc_id=normalized.doc_id,
                    source_ref=normalized.source.source_ref,
                    title=normalized.title,
                    source_checksum=source_checksum,
                    normalized_checksum=normalized.checksum,
                    chunk_count=len(chunks),
                    processed_at=processed_at,
                    status="processed",
                )
            )
            logger.info(
                "Ingested doc_id=%s title=%s chunks=%s",
                normalized.doc_id,
                normalized.title,
                len(chunks),
            )
        except Exception as exc:  # noqa: BLE001 - Pipeline soll robust weiterlaufen.
            with audit.stage(
                run_id=run_context.run_id,
                source_type="filesystem",
                source_instance=args.source_instance,
                stage=AuditStage.TRANSFORM,
                document_id=source_doc.doc_id,
                document_uri=source_doc.source.source_ref,
                document_title=source_doc.title,
            ) as error_evt:
                error_evt.error(ReasonCode.UNKNOWN_EXCEPTION, str(exc))

            processed_at = utc_now_iso()
            run_manifest.documents_failed += 1
            run_manifest.records.append(
                ProcessedDocumentRecord(
                    doc_id=source_doc.doc_id,
                    source_ref=source_doc.source.source_ref,
                    title=source_doc.title,
                    source_checksum=source_checksum,
                    normalized_checksum="",
                    chunk_count=0,
                    processed_at=processed_at,
                    status="error",
                )
            )
            logger.exception(
                "Failed processing doc_id=%s source_ref=%s: %s",
                source_doc.doc_id,
                source_doc.source.source_ref,
                exc,
            )

    run_manifest.finished_at = utc_now_iso()
    run_manifest.run_duration = perf_counter() - started_perf
    run_manifest.run_duration_human = format_duration_human(run_manifest.run_duration)

    manifests_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path = manifests_dir / f"run_{run_manifest.run_id}.json"
    latest_manifest_path = manifests_dir / "latest_run_manifest.json"

    run_manifest_path.write_text(run_manifest.to_json(), encoding="utf-8")
    latest_manifest_path.write_text(run_manifest.to_json(), encoding="utf-8")
    state.save(state_path)

    logger.info(
        "Ingestion completed. run_id=%s mode=%s seen=%s processed=%s skipped=%s failed=%s duration=%.2fs (%s)",
        run_manifest.run_id,
        run_manifest.mode,
        run_manifest.documents_seen,
        run_manifest.documents_processed,
        run_manifest.documents_skipped,
        run_manifest.documents_failed,
        run_manifest.run_duration,
        run_manifest.run_duration_human,
    )
    logger.info("Manifest written: %s", run_manifest_path)
    logger.info("Processing state written: %s", state_path)
    run_context.finish(status="finished" if run_manifest.documents_failed == 0 else "finished_with_errors")
    return 0 if run_manifest.documents_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
